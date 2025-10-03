"""
Output generation module.
Reassembles reviewed chunks into final markdown document.
"""

from typing import List, Dict, Optional
from datetime import datetime
from pathlib import Path
import json
import re


class MarkdownGenerator:
    """Generates final markdown output from reviewed chunks."""

    def __init__(self, config: Dict):
        self.config = config
        self.output_config = config.get('output', {})
        self.output_dir = Path(self.output_config.get('output_dir', 'output'))
        self.include_toc = self.output_config.get('table_of_contents', True)
        self.change_tracking = self.output_config.get('change_tracking', {})

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_document(self, chunks: List[Dict], metadata: Dict,
                         cross_ref_report: Optional[Dict] = None) -> str:
        """
        Generate complete markdown document from chunks.

        Args:
            chunks: List of chunk dictionaries with content and metadata
            metadata: Document metadata
            cross_ref_report: Optional cross-reference validation report

        Returns:
            Path to generated markdown file
        """
        # Sort chunks by page and position
        sorted_chunks = sorted(chunks, key=lambda c: (
            c.get('page_start', 0),
            c.get('chunk_id', '')
        ))

        # Build markdown content
        markdown_parts = []

        # Add document header
        markdown_parts.append(self._generate_header(metadata))

        # Add table of contents if enabled
        if self.include_toc:
            toc = self._generate_toc(sorted_chunks)
            if toc:
                markdown_parts.append(toc)
                markdown_parts.append("\n---\n")

        # Add reviewed content
        current_section = None

        for chunk in sorted_chunks:
            # Add section header if changed
            section = chunk.get('section_hierarchy', '')
            if section and section != current_section:
                markdown_parts.append(f"\n## {section}\n")
                current_section = section

            # Add chunk content
            content = chunk.get('reviewed_content') or chunk.get('content', '')

            # Add page reference as comment
            page_start = chunk.get('page_start')
            if page_start:
                markdown_parts.append(f"<!-- Page {page_start} -->\n")

            markdown_parts.append(content)
            markdown_parts.append("\n\n")

        # Add cross-reference report if provided
        if cross_ref_report:
            markdown_parts.append("\n---\n")
            markdown_parts.append(self._generate_crossref_report(cross_ref_report))

        # Combine all parts
        full_markdown = "".join(markdown_parts)

        # Write to file
        output_path = self._write_output(full_markdown, metadata)

        return str(output_path)

    def _generate_header(self, metadata: Dict) -> str:
        """Generate document header with metadata."""
        title = metadata.get('title', 'Untitled Document')
        filename = metadata.get('filename', 'unknown.pdf')
        review_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        header = f"""# {title}

**Source:** {filename}
**Review Date:** {review_date}
**Total Pages:** {metadata.get('total_pages', 'N/A')}

---

"""
        return header

    def _generate_toc(self, chunks: List[Dict]) -> str:
        """Generate table of contents."""
        toc_lines = ["## Table of Contents\n"]

        sections_seen = set()

        # Patterns to exclude from ToC
        exclude_patterns = [
            r'^Figure\s+\d+$',  # "Figure 1", "Figure 2", etc.
            r'^Table\s+\d+$',   # "Table 1", "Table 2", etc.
            r'^Unknown Section$',
            r'^\[Figure\s+\d+\]$',
            r'^\[Table\s+\d+\]$'
        ]

        for chunk in chunks:
            section = chunk.get('section_hierarchy', '')

            # Skip if section matches any exclude pattern
            should_exclude = False
            for pattern in exclude_patterns:
                if re.match(pattern, section):
                    should_exclude = True
                    break

            # Only add unique, non-excluded sections with sufficient length
            if (section and
                section not in sections_seen and
                not should_exclude and
                len(section) >= 3):  # Minimum section name length
                sections_seen.add(section)

                # Create anchor link
                anchor = section.lower().replace(' ', '-').replace('.', '')
                toc_lines.append(f"- [{section}](#{anchor})")

        if len(toc_lines) <= 1:
            return ""

        return "\n".join(toc_lines) + "\n"

    def _generate_crossref_report(self, report: Dict) -> str:
        """Generate cross-reference validation report."""
        lines = ["# Cross-Reference Validation Report\n"]

        total = report.get('total_references', 0)
        valid = report.get('valid_references', 0)
        invalid = report.get('invalid_references', 0)

        lines.append(f"**Total References:** {total}  ")
        lines.append(f"**Valid:** {valid}  ")
        lines.append(f"**Invalid:** {invalid}  ")
        lines.append("")

        # Add broken references if any
        broken = report.get('broken_references', [])
        if broken:
            lines.append("## Broken References\n")
            lines.append("| Reference | Type | Target | Page | Chunk ID |")
            lines.append("|-----------|------|--------|------|----------|")

            for ref in broken:
                lines.append(
                    f"| {ref['text']} | {ref['type']} | {ref['target']} | "
                    f"{ref['page']} | {ref['chunk_id']} |"
                )

        # Add statistics by type
        by_type = report.get('by_type', {})
        if by_type:
            lines.append("\n## References by Type\n")
            lines.append("| Type | Total | Valid | Invalid |")
            lines.append("|------|-------|-------|---------|")

            for ref_type, stats in by_type.items():
                lines.append(
                    f"| {ref_type} | {stats['total']} | {stats['valid']} | "
                    f"{stats['invalid']} |"
                )

        return "\n".join(lines) + "\n"

    def _write_output(self, markdown: str, metadata: Dict) -> Path:
        """Write markdown to output file."""
        # Generate filename
        source_name = Path(metadata.get('filename', 'document')).stem
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_filename = f"{source_name}_reviewed_{timestamp}.md"

        output_path = self.output_dir / output_filename

        # Write file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(markdown)

        return output_path

    def generate_summary_report(self, stats: Dict, timing: Dict = None) -> str:
        """
        Generate summary report of the review process.

        Args:
            stats: Statistics dictionary
            timing: Timing data dictionary (optional)

        Returns:
            Path to summary report file
        """
        lines = ["# Review Summary Report\n"]

        lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n")

        # Document stats
        if 'document' in stats:
            doc = stats['document']
            lines.append("\n## Document Information\n")
            lines.append(f"**Filename:** {doc.get('filename', 'N/A')}  ")
            lines.append(f"**Total Pages:** {doc.get('total_pages', 'N/A')}  ")
            lines.append(f"**Total Chunks:** {doc.get('total_chunks', 'N/A')}  ")

        # Processing stats with timing
        if 'processing' in stats:
            proc = stats['processing']
            lines.append("\n## Processing Statistics\n")
            lines.append(f"**Total Chunks Processed:** {proc.get('total', 0)}  ")
            lines.append(f"**Completed:** {proc.get('completed', 0)}  ")
            lines.append(f"**Failed:** {proc.get('failed', 0)}  ")
            lines.append(f"**Average Confidence:** {proc.get('avg_confidence', 0):.2f}  ")

            # Add timing information if available
            if timing:
                lines.append(f"\n**Processing Time:** {timing.get('total_time', 0):.1f} seconds ({timing.get('total_time', 0)/60:.1f} minutes)  ")
                lines.append(f"**Speed:** {timing.get('pages_per_second', 0):.2f} pages/second  ")
                lines.append(f"**Extraction Time:** {timing.get('extraction_time', 0):.1f}s  ")
                lines.append(f"**Review Time:** {timing.get('review_time', 0):.1f}s  ")
                lines.append(f"**Cross-reference Time:** {timing.get('crossref_time', 0):.1f}s  ")
                lines.append(f"**Output Generation Time:** {timing.get('output_time', 0):.1f}s  ")

        # Language review stats
        if 'language_review' in stats:
            lang = stats['language_review']
            lines.append("\n## Language Review\n")
            lines.append(f"**Total Changes:** {lang.get('total_changes', 0)}  ")
            lines.append(f"**Spelling Corrections:** {lang.get('spelling', 0)}  ")
            lines.append(f"**Grammar Fixes:** {lang.get('grammar', 0)}  ")
            lines.append(f"**Style Improvements:** {lang.get('style', 0)}  ")

        # Cross-reference stats
        if 'crossref' in stats:
            xref = stats['crossref']
            lines.append("\n## Cross-Reference Validation\n")
            lines.append(f"**Total References:** {xref.get('total', 0)}  ")
            lines.append(f"**Valid:** {xref.get('valid', 0)}  ")
            lines.append(f"**Invalid:** {xref.get('invalid', 0)}  ")

        # Table/Figure stats
        if 'tables_figures' in stats:
            tf = stats['tables_figures']
            lines.append("\n## Tables and Figures\n")
            lines.append(f"**Tables Reviewed:** {tf.get('tables', 0)}  ")
            lines.append(f"**Figures Reviewed:** {tf.get('figures', 0)}  ")
            lines.append(f"**Issues Found:** {tf.get('issues', 0)}  ")

        markdown = "\n".join(lines)

        # Write summary
        output_path = self.output_dir / f"review_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(markdown)

        return str(output_path)

    def export_json_report(self, data: Dict) -> str:
        """
        Export detailed review data as JSON.

        Args:
            data: Complete review data

        Returns:
            Path to JSON file
        """
        output_path = self.output_dir / f"review_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)

        return str(output_path)
