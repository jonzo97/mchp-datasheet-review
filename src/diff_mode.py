"""
Diff mode for comparing document versions.
Generates intelligent changelogs between datasheet revisions.
"""

import difflib
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from extraction import PDFExtractor
from embeddings import EmbeddingGenerator


@dataclass
class DocumentChange:
    """Represents a change between document versions."""
    section: str
    change_type: str  # 'modified', 'added', 'removed'
    page_v1: int
    page_v2: int
    content_v1: str
    content_v2: str
    significance: str  # 'high', 'medium', 'low'
    details: str


class DocumentDiffer:
    """Compare two versions of a document and generate intelligent diff."""

    def __init__(self, config: Dict):
        self.config = config
        self.extractor = PDFExtractor(config)
        self.embedding_generator = EmbeddingGenerator(config)
        self.use_semantic = config.get('diff_mode', {}).get('use_semantic_alignment', True)

    def compare_documents(self, doc_v1_path: str, doc_v2_path: str, output_path: str = None) -> Dict:
        """
        Compare two document versions and generate changelog.

        Args:
            doc_v1_path: Path to version 1 PDF
            doc_v2_path: Path to version 2 PDF
            output_path: Optional output path for changelog

        Returns:
            Dictionary with comparison results
        """
        print(f"Comparing documents...")
        print(f"  V1: {Path(doc_v1_path).name}")
        print(f"  V2: {Path(doc_v2_path).name}")

        # Extract both documents
        print("\nExtracting V1...")
        chunks_v1 = self.extractor.extract_document(doc_v1_path, "doc_v1")

        print("Extracting V2...")
        chunks_v2 = self.extractor.extract_document(doc_v2_path, "doc_v2")

        print(f"\nAligning {len(chunks_v1)} chunks from V1 with {len(chunks_v2)} chunks from V2...")

        # Align chunks by similarity
        alignments = self._align_chunks(chunks_v1, chunks_v2)

        # Generate change list
        changes = self._generate_changes(alignments)

        # Classify changes by significance
        categorized = self._categorize_changes(changes)

        # Generate markdown changelog
        changelog = self._format_changelog(categorized, doc_v1_path, doc_v2_path)

        # Write to file if specified
        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(changelog)
            print(f"\nChangelog written to: {output_path}")

        return {
            'total_changes': len(changes),
            'high_priority': len(categorized['high']),
            'medium_priority': len(categorized['medium']),
            'low_priority': len(categorized['low']),
            'changelog': changelog,
            'changes': changes
        }

    def _align_chunks(self, chunks_v1: List, chunks_v2: List) -> List[Dict]:
        """
        Align chunks from both versions based on similarity.
        Uses semantic similarity if available, otherwise falls back to section hierarchy.
        """
        # Try semantic alignment if available
        if self.use_semantic and self.embedding_generator.is_available():
            return self._align_chunks_semantic(chunks_v1, chunks_v2)
        else:
            return self._align_chunks_simple(chunks_v1, chunks_v2)

    def _align_chunks_simple(self, chunks_v1: List, chunks_v2: List) -> List[Dict]:
        """Simple alignment by section hierarchy (fallback method)."""
        alignments = []

        # Simple alignment by section hierarchy
        sections_v1 = {c.section_hierarchy: c for c in chunks_v1 if c.chunk_type == 'text'}
        sections_v2 = {c.section_hierarchy: c for c in chunks_v2 if c.chunk_type == 'text'}

        all_sections = set(sections_v1.keys()) | set(sections_v2.keys())

        for section in sorted(all_sections):
            chunk_v1 = sections_v1.get(section)
            chunk_v2 = sections_v2.get(section)

            if chunk_v1 and chunk_v2:
                # Both versions have this section
                if chunk_v1.content != chunk_v2.content:
                    alignments.append({
                        'type': 'modified',
                        'section': section,
                        'chunk_v1': chunk_v1,
                        'chunk_v2': chunk_v2
                    })
            elif chunk_v1:
                # Section removed in V2
                alignments.append({
                    'type': 'removed',
                    'section': section,
                    'chunk_v1': chunk_v1,
                    'chunk_v2': None
                })
            else:
                # Section added in V2
                alignments.append({
                    'type': 'added',
                    'section': section,
                    'chunk_v1': None,
                    'chunk_v2': chunk_v2
                })

        return alignments

    def _align_chunks_semantic(self, chunks_v1: List, chunks_v2: List) -> List[Dict]:
        """
        Advanced alignment using semantic similarity.
        Better at detecting reorganized or paraphrased content.
        """
        import numpy as np

        alignments = []

        # Filter text chunks only
        text_chunks_v1 = [c for c in chunks_v1 if c.chunk_type == 'text']
        text_chunks_v2 = [c for c in chunks_v2 if c.chunk_type == 'text']

        if not text_chunks_v1 or not text_chunks_v2:
            return []

        print("Using semantic alignment (computing embeddings)...")

        # Generate embeddings for all chunks
        texts_v1 = [c.content for c in text_chunks_v1]
        texts_v2 = [c.content for c in text_chunks_v2]

        emb_v1 = self.embedding_generator.encode(texts_v1, show_progress=True)
        emb_v2 = self.embedding_generator.encode(texts_v2, show_progress=True)

        if emb_v1 is None or emb_v2 is None:
            print("⚠️ Failed to generate embeddings, falling back to simple alignment")
            return self._align_chunks_simple(chunks_v1, chunks_v2)

        # Track which v2 chunks have been matched
        matched_v2 = set()

        # For each v1 chunk, find best match in v2
        for i, chunk_v1 in enumerate(text_chunks_v1):
            best_similarity = -1
            best_match_idx = -1

            # Calculate similarity with all unmatched v2 chunks
            for j in range(len(text_chunks_v2)):
                if j in matched_v2:
                    continue

                # Cosine similarity
                similarity = np.dot(emb_v1[i], emb_v2[j]) / (
                    np.linalg.norm(emb_v1[i]) * np.linalg.norm(emb_v2[j])
                )

                if similarity > best_similarity:
                    best_similarity = float(similarity)
                    best_match_idx = j

            # If good match found (>0.7 similarity), mark as modified or unchanged
            if best_similarity >= 0.7 and best_match_idx >= 0:
                chunk_v2 = text_chunks_v2[best_match_idx]
                matched_v2.add(best_match_idx)

                # Only add if content actually changed
                if chunk_v1.content != chunk_v2.content:
                    alignments.append({
                        'type': 'modified',
                        'section': chunk_v1.section_hierarchy,
                        'chunk_v1': chunk_v1,
                        'chunk_v2': chunk_v2,
                        'semantic_similarity': best_similarity
                    })
            else:
                # No good match, likely removed
                alignments.append({
                    'type': 'removed',
                    'section': chunk_v1.section_hierarchy,
                    'chunk_v1': chunk_v1,
                    'chunk_v2': None
                })

        # Add unmatched v2 chunks as additions
        for j, chunk_v2 in enumerate(text_chunks_v2):
            if j not in matched_v2:
                alignments.append({
                    'type': 'added',
                    'section': chunk_v2.section_hierarchy,
                    'chunk_v1': None,
                    'chunk_v2': chunk_v2
                })

        print(f"✅ Semantic alignment complete: {len(alignments)} changes detected")
        return alignments

    def _generate_changes(self, alignments: List[Dict]) -> List[DocumentChange]:
        """Generate detailed change records from alignments."""
        changes = []

        for aligned in alignments:
            if aligned['type'] == 'modified':
                # Generate word-level diff
                diff_details = self._semantic_diff(
                    aligned['chunk_v1'].content,
                    aligned['chunk_v2'].content
                )

                significance = self._calculate_significance(
                    aligned['chunk_v1'].content,
                    aligned['chunk_v2'].content
                )

                changes.append(DocumentChange(
                    section=aligned['section'],
                    change_type='modified',
                    page_v1=aligned['chunk_v1'].page_start,
                    page_v2=aligned['chunk_v2'].page_start,
                    content_v1=aligned['chunk_v1'].content[:200],
                    content_v2=aligned['chunk_v2'].content[:200],
                    significance=significance,
                    details=diff_details
                ))

            elif aligned['type'] == 'added':
                changes.append(DocumentChange(
                    section=aligned['section'],
                    change_type='added',
                    page_v1=0,
                    page_v2=aligned['chunk_v2'].page_start,
                    content_v1="",
                    content_v2=aligned['chunk_v2'].content[:200],
                    significance='medium',
                    details=f"New section added: {aligned['section']}"
                ))

            elif aligned['type'] == 'removed':
                changes.append(DocumentChange(
                    section=aligned['section'],
                    change_type='removed',
                    page_v1=aligned['chunk_v1'].page_start,
                    page_v2=0,
                    content_v1=aligned['chunk_v1'].content[:200],
                    content_v2="",
                    significance='high',  # Removals are usually significant
                    details=f"Section removed: {aligned['section']}"
                ))

        return changes

    def _semantic_diff(self, text_v1: str, text_v2: str) -> str:
        """Generate semantic diff summary."""
        # Word-level diff
        words_v1 = text_v1.split()
        words_v2 = text_v2.split()

        matcher = difflib.SequenceMatcher(None, words_v1, words_v2)
        changes = []

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'replace':
                old = ' '.join(words_v1[i1:i2])
                new = ' '.join(words_v2[j1:j2])
                changes.append(f"'{old}' → '{new}'")
            elif tag == 'delete':
                deleted = ' '.join(words_v1[i1:i2])
                changes.append(f"Removed: '{deleted}'")
            elif tag == 'insert':
                inserted = ' '.join(words_v2[j1:j2])
                changes.append(f"Added: '{inserted}'")

        return "; ".join(changes[:5])  # Limit to top 5 changes

    def _calculate_significance(self, text_v1: str, text_v2: str) -> str:
        """Classify change importance."""
        # Technical spec keywords indicate high significance
        tech_keywords = [
            'voltage', 'current', 'frequency', 'temperature', 'max', 'min',
            'MHz', 'GHz', 'mA', 'µA', 'typical', 'maximum', 'minimum'
        ]

        text_lower = (text_v1 + text_v2).lower()

        if any(keyword in text_lower for keyword in tech_keywords):
            # Check if numerical values changed
            if self._has_numerical_change(text_v1, text_v2):
                return 'high'

        # Check change magnitude
        similarity = difflib.SequenceMatcher(None, text_v1, text_v2).ratio()

        if similarity < 0.5:
            return 'medium'  # Large change
        elif similarity < 0.9:
            return 'low'  # Small change
        else:
            return 'low'  # Trivial change

    def _has_numerical_change(self, text_v1: str, text_v2: str) -> bool:
        """Check if numerical values changed."""
        import re
        nums_v1 = set(re.findall(r'\d+\.?\d*', text_v1))
        nums_v2 = set(re.findall(r'\d+\.?\d*', text_v2))
        return nums_v1 != nums_v2

    def _categorize_changes(self, changes: List[DocumentChange]) -> Dict[str, List[DocumentChange]]:
        """Categorize changes by significance."""
        categorized = {
            'high': [],
            'medium': [],
            'low': []
        }

        for change in changes:
            categorized[change.significance].append(change)

        return categorized

    def _format_changelog(self, categorized: Dict, v1_path: str, v2_path: str) -> str:
        """Format changelog as markdown."""
        lines = []

        lines.append(f"# Document Changelog\n")
        lines.append(f"**Comparison:** {Path(v1_path).name} → {Path(v2_path).name}")
        lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        lines.append("---\n")

        # Summary
        total = sum(len(changes) for changes in categorized.values())
        lines.append(f"## Summary\n")
        lines.append(f"- **Total Changes:** {total}")
        lines.append(f"- **High Priority:** {len(categorized['high'])} ⚠️")
        lines.append(f"- **Medium Priority:** {len(categorized['medium'])}")
        lines.append(f"- **Low Priority:** {len(categorized['low'])}\n")
        lines.append("---\n")

        # High priority changes
        if categorized['high']:
            lines.append("## ⚠️ High Priority Changes\n")
            for change in categorized['high']:
                lines.append(f"### {change.section} (Page {change.page_v1} → {change.page_v2})\n")
                lines.append(f"**Type:** {change.change_type.upper()}\n")
                lines.append(f"**Details:** {change.details}\n")
                if change.change_type == 'modified':
                    lines.append(f"**Before:** {change.content_v1[:100]}...\n")
                    lines.append(f"**After:** {change.content_v2[:100]}...\n")
                lines.append("---\n")

        # Medium priority changes
        if categorized['medium']:
            lines.append("## Medium Priority Changes\n")
            for change in categorized['medium']:
                lines.append(f"- **{change.section}**: {change.details}\n")

        # Low priority changes
        if categorized['low']:
            lines.append("\n## Low Priority Changes\n")
            lines.append(f"*{len(categorized['low'])} minor changes (rewording, formatting)*\n")

        return "\n".join(lines)


def main():
    """CLI entry point for diff mode."""
    import sys
    import yaml

    if len(sys.argv) < 3:
        print("Usage: python diff_mode.py <v1.pdf> <v2.pdf> [output.md]")
        sys.exit(1)

    v1_path = sys.argv[1]
    v2_path = sys.argv[2]
    output_path = sys.argv[3] if len(sys.argv) > 3 else "changelog.md"

    # Load config
    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    # Run comparison
    differ = DocumentDiffer(config)
    results = differ.compare_documents(v1_path, v2_path, output_path)

    print(f"\n{'='*60}")
    print(f"Comparison complete!")
    print(f"Total changes: {results['total_changes']}")
    print(f"High priority: {results['high_priority']}")
    print(f"Output: {output_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
