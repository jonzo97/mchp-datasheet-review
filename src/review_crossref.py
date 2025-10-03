"""
Cross-reference validation module.
Extracts and validates references to sections, figures, tables, and equations.
"""

import re
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass
import hashlib


@dataclass
class Reference:
    """Represents a cross-reference."""
    ref_id: str
    chunk_id: str
    reference_text: str
    reference_type: str  # 'section', 'figure', 'table', 'equation'
    target_number: str
    page_number: int
    is_valid: bool = False
    target_id: Optional[str] = None


class CrossReferenceValidator:
    """Validates cross-references in the document."""

    def __init__(self, config: Dict):
        self.config = config
        self.enabled = config.get('crossref', {}).get('enabled', True)

        # Reference patterns from config
        self.patterns = {
            'section': [
                r'Section\s+(\d+(?:\.\d+)*)',
                r'section\s+(\d+(?:\.\d+)*)',
                r'\u00a7\s*(\d+(?:\.\d+)*)',  # § symbol
            ],
            'figure': [
                r'Figure\s+(\d+-\d+)',
                r'Figure\s+(\d+)',
                r'Fig\.\s+(\d+-\d+)',
                r'Fig\.\s+(\d+)',
            ],
            'table': [
                r'Table\s+(\d+-\d+)',
                r'Table\s+(\d+)',
                r'TABLE\s+(\d+-\d+)',
            ],
            'equation': [
                r'Equation\s+(\d+-\d+)',
                r'Equation\s+(\d+)',
                r'Eq\.\s+(\d+-\d+)',
            ]
        }

        # Track all targets found in document
        self.targets = {
            'section': set(),
            'figure': set(),
            'table': set(),
            'equation': set()
        }

    def extract_references(self, content: str, chunk_id: str,
                          page_number: int) -> List[Reference]:
        """
        Extract all cross-references from content.

        Args:
            content: Text content to analyze
            chunk_id: ID of the chunk being analyzed
            page_number: Page number for reference tracking

        Returns:
            List of extracted references
        """
        if not self.enabled:
            return []

        references = []

        for ref_type, patterns in self.patterns.items():
            for pattern in patterns:
                matches = re.finditer(pattern, content)

                for match in matches:
                    target_number = match.group(1)
                    reference_text = match.group(0)

                    ref_id = self._generate_ref_id(reference_text, chunk_id, match.start())

                    ref = Reference(
                        ref_id=ref_id,
                        chunk_id=chunk_id,
                        reference_text=reference_text,
                        reference_type=ref_type,
                        target_number=target_number,
                        page_number=page_number
                    )

                    references.append(ref)

        return references

    def extract_targets(self, content: str, chunk_type: str) -> Set[str]:
        """
        Extract reference targets (what can be referenced).

        Args:
            content: Text content
            chunk_type: Type of chunk (text, table, figure)

        Returns:
            Set of target identifiers
        """
        targets = set()

        if chunk_type == 'figure':
            # IMPROVED: Extract figure numbers from multiple formats
            figure_patterns = [
                r'\[Figure\s+(\d+(?:-\d+)?)\]',       # [Figure 3-3] or [Figure 1]
                r'Figure\s+(\d+(?:-\d+)?)[:\.]',      # Figure 3-3: caption
                r'(?:^|\n)Figure\s+(\d+(?:-\d+)?)',   # Figure 3-3 at line start
                r'Fig\.\s+(\d+(?:-\d+)?)',            # Fig. 3-3
            ]
            for pattern in figure_patterns:
                for match in re.finditer(pattern, content):
                    targets.add(match.group(1))

        elif chunk_type == 'table':
            # IMPROVED: Extract table numbers from multiple formats
            table_patterns = [
                r'\[Table\s+(\d+(?:-\d+)?)\]',        # [Table 3-3] or [Table 1]
                r'Table\s+(\d+(?:-\d+)?)[:\.]',       # Table 3-3: caption
                r'TABLE\s+(\d+(?:-\d+)?)[:\.]',       # TABLE 3-3: caption
                r'(?:^|\n)Table\s+(\d+(?:-\d+)?)',    # Table at line start
            ]
            for pattern in table_patterns:
                for match in re.finditer(pattern, content):
                    targets.add(match.group(1))

        else:
            # IMPROVED: Extract section numbers from multiple formats
            section_patterns = [
                r'^(\d+(?:\.\d+)*)\s+\w+',            # "1.2.3 word" (any word, not just caps)
                r'(?:^|\n)\s*(\d+(?:\.\d+)*)\s+[A-Z]', # Line start + capital
                r'Section\s+(\d+(?:\.\d+)*)',         # In "Section X.Y" text
                r'SECTION\s+(\d+(?:\.\d+)*)',         # SECTION X.Y
                r'^##+\s*(\d+(?:\.\d+)*)',            # Markdown headings
            ]

            for pattern in section_patterns:
                matches = re.finditer(pattern, content, re.MULTILINE)
                for match in matches:
                    targets.add(match.group(1))

        return targets

    def validate_references(self, references: List[Reference]) -> List[Reference]:
        """
        Validate references against known targets with fuzzy matching.

        Args:
            references: List of references to validate

        Returns:
            Updated list with validation status
        """
        for ref in references:
            targets = self.targets.get(ref.reference_type, set())

            # Exact match first
            if ref.target_number in targets:
                ref.is_valid = True
                ref.target_id = f"{ref.reference_type}_{ref.target_number}"
                continue

            # IMPROVED: Fuzzy matching strategies
            matched_target = self._fuzzy_match_target(ref.target_number, targets)

            if matched_target:
                ref.is_valid = True
                ref.target_id = f"{ref.reference_type}_{matched_target}"
            else:
                ref.is_valid = False

        return references

    def _fuzzy_match_target(self, ref_num: str, targets: Set[str]) -> Optional[str]:
        """
        Fuzzy match a reference to available targets.

        Args:
            ref_num: Reference number to match
            targets: Set of valid target numbers

        Returns:
            Matched target or None
        """
        # Strategy 1: Parent section match (3.1.5 → try 3.1, then 3)
        if '.' in ref_num:
            parts = ref_num.split('.')
            for i in range(len(parts)-1, 0, -1):
                parent = '.'.join(parts[:i])
                if parent in targets:
                    return parent

        # Strategy 2: Hyphen simplification (3-3 → try 3, or try 33)
        if '-' in ref_num:
            # Try first number
            simplified = ref_num.split('-')[0]
            if simplified in targets:
                return simplified

            # Try concatenation
            concat = ref_num.replace('-', '')
            if concat in targets:
                return concat

        # Strategy 3: Close numerical match (13 vs 13.0)
        ref_base = ref_num.rstrip('.0')
        for target in targets:
            target_base = target.rstrip('.0')
            if ref_base == target_base:
                return target

        return None

    def build_reference_graph(self, all_references: List[Reference]) -> Dict[str, List[str]]:
        """
        Build a graph of references for analysis.

        Args:
            all_references: All references in the document

        Returns:
            Dictionary mapping source chunks to target references
        """
        graph = {}

        for ref in all_references:
            if ref.chunk_id not in graph:
                graph[ref.chunk_id] = []

            graph[ref.chunk_id].append({
                'type': ref.reference_type,
                'target': ref.target_number,
                'valid': ref.is_valid,
                'text': ref.reference_text
            })

        return graph

    def get_broken_references(self, references: List[Reference]) -> List[Reference]:
        """Get all broken (invalid) references."""
        return [ref for ref in references if not ref.is_valid]

    def generate_reference_report(self, references: List[Reference]) -> Dict:
        """
        Generate a summary report of references.

        Args:
            references: List of all references

        Returns:
            Dictionary with reference statistics
        """
        total = len(references)
        valid = sum(1 for ref in references if ref.is_valid)
        invalid = total - valid

        by_type = {}
        for ref in references:
            if ref.reference_type not in by_type:
                by_type[ref.reference_type] = {'total': 0, 'valid': 0, 'invalid': 0}

            by_type[ref.reference_type]['total'] += 1
            if ref.is_valid:
                by_type[ref.reference_type]['valid'] += 1
            else:
                by_type[ref.reference_type]['invalid'] += 1

        return {
            'total_references': total,
            'valid_references': valid,
            'invalid_references': invalid,
            'by_type': by_type,
            'broken_references': [
                {
                    'text': ref.reference_text,
                    'type': ref.reference_type,
                    'target': ref.target_number,
                    'page': ref.page_number,
                    'chunk_id': ref.chunk_id
                }
                for ref in self.get_broken_references(references)
            ]
        }

    def update_targets(self, ref_type: str, targets: Set[str]):
        """
        Update the set of known targets for a reference type.

        Args:
            ref_type: Type of reference (section, figure, table, equation)
            targets: Set of target identifiers
        """
        if ref_type in self.targets:
            self.targets[ref_type].update(targets)

    def _generate_ref_id(self, reference_text: str, chunk_id: str, position: int) -> str:
        """Generate unique reference ID."""
        hash_input = f"{reference_text}{chunk_id}{position}".encode()
        hash_val = hashlib.md5(hash_input).hexdigest()[:12]
        return f"ref_{hash_val}"

    def suggest_corrections(self, broken_ref: Reference) -> List[str]:
        """
        Suggest possible corrections for broken references.

        Args:
            broken_ref: A broken reference

        Returns:
            List of suggested corrections
        """
        suggestions = []
        target_num = broken_ref.target_number

        # Get all valid targets of the same type
        valid_targets = self.targets.get(broken_ref.reference_type, set())

        # Look for similar targets (off by one, transposed digits, etc.)
        for valid_target in valid_targets:
            # Simple similarity check
            if self._are_similar(target_num, valid_target):
                suggestions.append(valid_target)

        return suggestions[:3]  # Return top 3 suggestions

    def _are_similar(self, num1: str, num2: str) -> bool:
        """Check if two reference numbers are similar."""
        # Check if they differ by just one digit
        if len(num1) == len(num2):
            diff_count = sum(c1 != c2 for c1, c2 in zip(num1, num2))
            if diff_count == 1:
                return True

        # Check for transposed digits
        if len(num1) == len(num2) and len(num1) > 1:
            for i in range(len(num1) - 1):
                if (num1[i] == num2[i + 1] and num1[i + 1] == num2[i] and
                    num1[:i] == num2[:i] and num1[i + 2:] == num2[i + 2:]):
                    return True

        return False
