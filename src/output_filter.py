"""
Output filtering and severity classification module.
Prioritizes changes by severity to surface actionable issues.
"""

from typing import List, Dict, Any
from dataclasses import dataclass
from enum import Enum


class Severity(Enum):
    """Severity levels for review findings."""
    CRITICAL = 0    # Technical errors, unsupported claims, broken refs
    HIGH = 1        # Missing sections, LLM suggestions, consistency issues
    MEDIUM = 2      # Terminology inconsistencies, style violations
    LOW = 3         # Minor formatting, suggestions
    IGNORE = 4      # Whitespace, trivial formatting (suppressed by default)


@dataclass
class FilteredChange:
    """A change with severity classification."""
    original: str
    corrected: str
    reason: str
    change_type: str
    severity: Severity
    position: int
    confidence: float
    metadata: Dict[str, Any] = None


class OutputFilter:
    """Filter and prioritize review output by severity."""

    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.verbosity = self.config.get('verbosity', 'normal')  # 'quiet', 'normal', 'verbose'

        # Severity thresholds
        self.min_severity = {
            'quiet': Severity.HIGH,      # Only critical and high
            'normal': Severity.MEDIUM,   # Critical, high, medium
            'verbose': Severity.IGNORE   # Everything
        }.get(self.verbosity, Severity.MEDIUM)

    def classify_change(self, change: Dict) -> Severity:
        """
        Classify a change by severity.

        Args:
            change: Change dictionary with 'type', 'reason', etc.

        Returns:
            Severity level
        """
        change_type = change.get('type', '').lower()
        reason = change.get('reason', '').lower()

        # CRITICAL: Technical accuracy errors
        if change_type == 'crossref' and not change.get('valid', True):
            return Severity.CRITICAL

        if 'unsupported claim' in reason or 'missing evidence' in reason:
            return Severity.CRITICAL

        if 'broken reference' in reason or 'section not found' in reason:
            return Severity.CRITICAL

        # HIGH: Important but not critical
        if change_type == 'llm_suggestion':
            return Severity.HIGH

        if 'missing section' in reason or 'incomplete' in reason:
            return Severity.HIGH

        if change.get('confidence', 1.0) < 0.8 and change_type != 'grammar':
            return Severity.HIGH

        # MEDIUM: Consistency and style
        if 'terminology' in reason or 'inconsistent' in reason:
            return Severity.MEDIUM

        if change_type == 'style':
            return Severity.MEDIUM

        if 'spelling' in change_type:
            return Severity.MEDIUM

        # LOW: Minor issues
        if 'formatting' in reason and 'space' not in reason:
            return Severity.LOW

        # IGNORE: Trivial whitespace
        if change_type == 'grammar' and ('double space' in reason or 'whitespace' in reason):
            return Severity.IGNORE

        if 'extra space' in reason or 'spacing' in reason:
            return Severity.IGNORE

        # Default to LOW for unknown types
        return Severity.LOW

    def filter_changes(self, changes: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Filter and categorize changes by severity.

        Args:
            changes: List of change dictionaries

        Returns:
            Dictionary grouped by severity level
        """
        categorized = {
            'critical': [],
            'high': [],
            'medium': [],
            'low': [],
            'suppressed': 0
        }

        for change in changes:
            severity = self.classify_change(change)

            # Apply verbosity filter
            if severity.value > self.min_severity.value:
                categorized['suppressed'] += 1
                continue

            # Add to appropriate category
            if severity == Severity.CRITICAL:
                categorized['critical'].append({**change, 'severity': 'critical'})
            elif severity == Severity.HIGH:
                categorized['high'].append({**change, 'severity': 'high'})
            elif severity == Severity.MEDIUM:
                categorized['medium'].append({**change, 'severity': 'medium'})
            elif severity == Severity.LOW:
                categorized['low'].append({**change, 'severity': 'low'})

        return categorized

    def format_summary(self, filtered_changes: Dict[str, List[Dict]]) -> str:
        """
        Format filtered changes as a readable summary.

        Args:
            filtered_changes: Output from filter_changes()

        Returns:
            Formatted summary string
        """
        lines = []

        # Critical issues
        if filtered_changes['critical']:
            lines.append(f"🔴 Critical Issues ({len(filtered_changes['critical'])}):")
            for i, change in enumerate(filtered_changes['critical'][:10], 1):  # Top 10
                lines.append(f"   {i}. {change.get('reason', 'Unknown issue')}")
                if change.get('original'):
                    lines.append(f"      Original: \"{change['original']}\"")
                if change.get('corrected'):
                    lines.append(f"      Corrected: \"{change['corrected']}\"")
            if len(filtered_changes['critical']) > 10:
                lines.append(f"   ... and {len(filtered_changes['critical']) - 10} more")
            lines.append("")

        # High priority
        if filtered_changes['high']:
            lines.append(f"🟠 High Priority ({len(filtered_changes['high'])}):")
            for i, change in enumerate(filtered_changes['high'][:5], 1):  # Top 5
                lines.append(f"   {i}. {change.get('reason', 'Unknown issue')}")
            if len(filtered_changes['high']) > 5:
                lines.append(f"   ... and {len(filtered_changes['high']) - 5} more")
            lines.append("")

        # Medium priority (summary only in normal mode)
        if filtered_changes['medium'] and self.verbosity != 'quiet':
            lines.append(f"🟡 Medium Priority ({len(filtered_changes['medium'])}):")
            if self.verbosity == 'verbose':
                for i, change in enumerate(filtered_changes['medium'][:10], 1):
                    lines.append(f"   {i}. {change.get('reason', 'Unknown issue')}")
            else:
                lines.append(f"   - {len([c for c in filtered_changes['medium'] if 'terminology' in c.get('reason', '')])} terminology inconsistencies")
                lines.append(f"   - {len([c for c in filtered_changes['medium'] if 'style' in c.get('type', '')])} style suggestions")
            lines.append("")

        # Low priority (count only)
        if filtered_changes['low'] and self.verbosity == 'verbose':
            lines.append(f"🟢 Low Priority ({len(filtered_changes['low'])}): Minor formatting suggestions")
            lines.append("")

        # Suppressed count
        if filtered_changes['suppressed'] > 0:
            lines.append(f"⚪ Suppressed: {filtered_changes['suppressed']} low-value changes (run with --verbose to see)")
            lines.append("")

        # Summary stats
        total_actionable = len(filtered_changes['critical']) + len(filtered_changes['high']) + len(filtered_changes['medium'])
        if total_actionable > 0:
            lines.append(f"📊 Actionable Items: {total_actionable}")
        else:
            lines.append("✅ No significant issues found!")

        return "\n".join(lines)

    def get_statistics(self, filtered_changes: Dict[str, List[Dict]]) -> Dict:
        """Get statistics about filtered changes."""
        return {
            'total_changes': (
                len(filtered_changes['critical']) +
                len(filtered_changes['high']) +
                len(filtered_changes['medium']) +
                len(filtered_changes['low']) +
                filtered_changes['suppressed']
            ),
            'actionable_changes': (
                len(filtered_changes['critical']) +
                len(filtered_changes['high'])
            ),
            'by_severity': {
                'critical': len(filtered_changes['critical']),
                'high': len(filtered_changes['high']),
                'medium': len(filtered_changes['medium']),
                'low': len(filtered_changes['low']),
                'suppressed': filtered_changes['suppressed']
            },
            'signal_to_noise_ratio': (
                (len(filtered_changes['critical']) + len(filtered_changes['high'])) /
                max(1, len(filtered_changes['critical']) + len(filtered_changes['high']) +
                    len(filtered_changes['medium']) + len(filtered_changes['low']) +
                    filtered_changes['suppressed'])
            )
        }


def prioritize_for_review(changes: List[Dict], max_items: int = 50) -> List[Dict]:
    """
    Prioritize changes for human review queue.

    Args:
        changes: List of all changes
        max_items: Maximum items to return

    Returns:
        Prioritized list of changes (critical first, then high, etc.)
    """
    filter_obj = OutputFilter()
    categorized = filter_obj.filter_changes(changes)

    prioritized = []

    # Add critical (all of them)
    prioritized.extend(categorized['critical'])

    # Add high (up to limit)
    remaining = max_items - len(prioritized)
    if remaining > 0:
        prioritized.extend(categorized['high'][:remaining])

    # Add medium (up to limit)
    remaining = max_items - len(prioritized)
    if remaining > 0:
        prioritized.extend(categorized['medium'][:remaining])

    # Add low (up to limit)
    remaining = max_items - len(prioritized)
    if remaining > 0:
        prioritized.extend(categorized['low'][:remaining])

    return prioritized


if __name__ == "__main__":
    # Test the filter
    test_changes = [
        {'type': 'grammar', 'original': '  ', 'corrected': ' ', 'reason': 'double space removed', 'confidence': 1.0},
        {'type': 'crossref', 'original': 'Section 7.3', 'corrected': '', 'reason': 'section not found', 'valid': False, 'confidence': 0.0},
        {'type': 'llm_suggestion', 'original': 'are', 'corrected': 'is', 'reason': 'subject-verb agreement', 'confidence': 0.95},
        {'type': 'style', 'original': 'WiFi', 'corrected': 'Wi-Fi®', 'reason': 'terminology standardization', 'confidence': 0.9},
        {'type': 'spelling', 'original': 'occured', 'corrected': 'occurred', 'reason': 'common typo', 'confidence': 0.98},
    ]

    filter_obj = OutputFilter({'verbosity': 'normal'})
    filtered = filter_obj.filter_changes(test_changes)

    print(filter_obj.format_summary(filtered))
    print("\nStatistics:", filter_obj.get_statistics(filtered))
