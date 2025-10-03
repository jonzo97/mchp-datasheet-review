"""
Table and figure review module.
Validates table structure, formatting, and figure metadata.
"""

import re
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass


@dataclass
class TableIssue:
    """Represents an issue found in a table."""
    issue_type: str  # 'formatting', 'missing_data', 'inconsistent_columns'
    description: str
    row: Optional[int] = None
    column: Optional[int] = None
    severity: str = 'medium'  # 'low', 'medium', 'high'


@dataclass
class FigureIssue:
    """Represents an issue found with a figure."""
    issue_type: str  # 'missing_caption', 'low_resolution', 'broken_reference'
    description: str
    severity: str = 'medium'


class TableFigureReviewer:
    """Reviews tables and figures for quality and consistency."""

    def __init__(self, config: Dict):
        self.config = config
        self.enabled = config.get('tables_figures', {}).get('enabled', True)
        self.min_table_rows = config.get('tables_figures', {}).get('min_table_rows', 2)

    def review_table(self, content: str, metadata: Dict) -> Tuple[str, List[TableIssue]]:
        """
        Review a table chunk for issues.

        Args:
            content: Markdown table content
            metadata: Table metadata

        Returns:
            Tuple of (reviewed_content, list_of_issues)
        """
        if not self.enabled:
            return content, []

        issues = []

        # Extract table from content
        table_lines = self._extract_table_lines(content)

        if not table_lines:
            issues.append(TableIssue(
                issue_type='formatting',
                description='No valid table found in content',
                severity='high'
            ))
            return content, issues

        # Check caption
        if not self._has_caption(content):
            issues.append(TableIssue(
                issue_type='missing_data',
                description='Table caption is missing',
                severity='medium'
            ))

        # Validate table structure
        structure_issues = self._validate_table_structure(table_lines)
        issues.extend(structure_issues)

        # Check for empty cells
        empty_cell_issues = self._check_empty_cells(table_lines)
        issues.extend(empty_cell_issues)

        # Check for formatting consistency
        format_issues = self._check_formatting(table_lines)
        issues.extend(format_issues)

        # Validate against metadata
        metadata_issues = self._validate_metadata(table_lines, metadata)
        issues.extend(metadata_issues)

        return content, issues

    def review_figure(self, content: str, metadata: Dict) -> Tuple[str, List[FigureIssue]]:
        """
        Review a figure chunk for issues.

        Args:
            content: Figure content with metadata
            metadata: Figure metadata

        Returns:
            Tuple of (reviewed_content, list_of_issues)
        """
        if not self.enabled:
            return content, []

        issues = []

        # Check for caption
        if not metadata.get('caption') and 'Caption:' not in content:
            issues.append(FigureIssue(
                issue_type='missing_caption',
                description='Figure caption is missing or not detected',
                severity='high'
            ))

        # Check image quality if metadata available
        if 'image_size' in metadata:
            if metadata['image_size'] < 10000:  # Less than 10KB
                issues.append(FigureIssue(
                    issue_type='low_resolution',
                    description='Figure may be low resolution (small file size)',
                    severity='medium'
                ))

        # Validate figure numbering
        numbering_issue = self._validate_figure_numbering(content, metadata)
        if numbering_issue:
            issues.append(numbering_issue)

        return content, issues

    def _extract_table_lines(self, content: str) -> List[str]:
        """Extract markdown table lines from content."""
        lines = content.split('\n')
        table_lines = []

        for line in lines:
            # Markdown table lines start with |
            if line.strip().startswith('|'):
                table_lines.append(line.strip())

        return table_lines

    def _has_caption(self, content: str) -> bool:
        """Check if table has a caption."""
        caption_pattern = r'(?:Table|TABLE)\s+\d+[:\.]?\s*(.+)'
        return bool(re.search(caption_pattern, content))

    def _validate_table_structure(self, table_lines: List[str]) -> List[TableIssue]:
        """Validate table structure."""
        issues = []

        if len(table_lines) < 3:  # Header + separator + at least one row
            issues.append(TableIssue(
                issue_type='formatting',
                description='Table has insufficient rows',
                severity='high'
            ))
            return issues

        # Check if second line is a separator
        if not re.match(r'\|\s*[-:]+\s*(\|\s*[-:]+\s*)*\|', table_lines[1]):
            issues.append(TableIssue(
                issue_type='formatting',
                description='Table separator row is malformed',
                row=1,
                severity='high'
            ))

        # Check column consistency
        num_columns = self._count_columns(table_lines[0])

        for i, line in enumerate(table_lines):
            line_columns = self._count_columns(line)
            if line_columns != num_columns:
                issues.append(TableIssue(
                    issue_type='inconsistent_columns',
                    description=f'Row has {line_columns} columns, expected {num_columns}',
                    row=i,
                    severity='high'
                ))

        return issues

    def _count_columns(self, table_line: str) -> int:
        """Count number of columns in a table line."""
        # Remove leading and trailing |
        line = table_line.strip()
        if line.startswith('|'):
            line = line[1:]
        if line.endswith('|'):
            line = line[:-1]

        # Count remaining |
        return line.count('|') + 1

    def _check_empty_cells(self, table_lines: List[str]) -> List[TableIssue]:
        """Check for empty cells in table."""
        issues = []

        # Skip header and separator
        for i, line in enumerate(table_lines[2:], start=2):
            cells = [cell.strip() for cell in line.split('|')[1:-1]]

            for j, cell in enumerate(cells):
                if not cell or cell == '':
                    issues.append(TableIssue(
                        issue_type='missing_data',
                        description='Empty cell detected',
                        row=i,
                        column=j,
                        severity='low'
                    ))

        return issues

    def _check_formatting(self, table_lines: List[str]) -> List[TableIssue]:
        """Check for formatting issues."""
        issues = []

        # Check for consistent spacing
        # This is a simple check - could be expanded
        for i, line in enumerate(table_lines):
            if '  ' in line:  # Double spaces
                issues.append(TableIssue(
                    issue_type='formatting',
                    description='Inconsistent spacing detected',
                    row=i,
                    severity='low'
                ))

        return issues

    def _validate_metadata(self, table_lines: List[str], metadata: Dict) -> List[TableIssue]:
        """Validate table against metadata."""
        issues = []

        actual_rows = len(table_lines) - 2  # Exclude header and separator
        expected_rows = metadata.get('rows', 0)

        if expected_rows > 0 and actual_rows != expected_rows:
            issues.append(TableIssue(
                issue_type='inconsistent_columns',
                description=f'Row count mismatch: found {actual_rows}, expected {expected_rows}',
                severity='medium'
            ))

        return issues

    def _validate_figure_numbering(self, content: str, metadata: Dict) -> Optional[FigureIssue]:
        """Validate figure numbering consistency."""
        # Extract figure number from content
        match = re.search(r'\[Figure\s+(\d+)\]', content)

        if not match:
            return FigureIssue(
                issue_type='formatting',
                description='Figure number not found in expected format',
                severity='medium'
            )

        content_number = int(match.group(1))
        metadata_index = metadata.get('image_index', -1)

        # Check if they're consistent (metadata index is 0-based)
        if metadata_index >= 0 and content_number != metadata_index + 1:
            return FigureIssue(
                issue_type='formatting',
                description=f'Figure numbering inconsistent: content says {content_number}, '
                           f'metadata indicates {metadata_index + 1}',
                severity='medium'
            )

        return None

    def generate_table_summary(self, issues: List[TableIssue]) -> Dict:
        """Generate summary of table issues."""
        if not issues:
            return {'status': 'pass', 'total_issues': 0}

        by_severity = {'low': 0, 'medium': 0, 'high': 0}
        by_type = {}

        for issue in issues:
            by_severity[issue.severity] += 1

            if issue.issue_type not in by_type:
                by_type[issue.issue_type] = 0
            by_type[issue.issue_type] += 1

        status = 'fail' if by_severity['high'] > 0 else 'warning'

        return {
            'status': status,
            'total_issues': len(issues),
            'by_severity': by_severity,
            'by_type': by_type,
            'issues': [
                {
                    'type': issue.issue_type,
                    'description': issue.description,
                    'row': issue.row,
                    'column': issue.column,
                    'severity': issue.severity
                }
                for issue in issues
            ]
        }

    def generate_figure_summary(self, issues: List[FigureIssue]) -> Dict:
        """Generate summary of figure issues."""
        if not issues:
            return {'status': 'pass', 'total_issues': 0}

        by_severity = {'low': 0, 'medium': 0, 'high': 0}
        by_type = {}

        for issue in issues:
            by_severity[issue.severity] += 1

            if issue.issue_type not in by_type:
                by_type[issue.issue_type] = 0
            by_type[issue.issue_type] += 1

        status = 'fail' if by_severity['high'] > 0 else 'warning'

        return {
            'status': status,
            'total_issues': len(issues),
            'by_severity': by_severity,
            'by_type': by_type,
            'issues': [
                {
                    'type': issue.issue_type,
                    'description': issue.description,
                    'severity': issue.severity
                }
                for issue in issues
            ]
        }
