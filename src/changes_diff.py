"""
Changes Diff Generator
Extracts and summarizes review changes in a readable format.
"""

import json
from typing import Dict, List, Tuple
from collections import defaultdict
from datetime import datetime
from pathlib import Path


class ChangesDiffGenerator:
    """Generates concise, readable diff summaries from review changes."""

    def __init__(self, config: Dict):
        self.config = config
        self.output_dir = Path(config.get('output', {}).get('output_dir', 'output'))
        self.manual_review_time = config.get('output', {}).get('roi_metrics', {}).get(
            'manual_review_time_per_page', 5  # minutes per page default
        )

    async def generate_diff_summary(self, db, document_id: str, stats: Dict,
                                   timing_data: Dict) -> str:
        """
        Generate a concise diff summary from database changes.

        Args:
            db: Database connection
            document_id: Document identifier
            stats: Statistics dictionary
            timing_data: Processing timing data

        Returns:
            Path to generated diff summary file
        """
        # Extract changes from database
        changes_by_type = await self._extract_changes(db, document_id)

        # Build the diff summary
        summary_parts = []

        # Header
        summary_parts.append(self._generate_header(stats, timing_data))

        # Sample changes by category
        if changes_by_type['spelling']:
            summary_parts.append(self._format_spelling_changes(changes_by_type['spelling']))

        if changes_by_type['grammar']:
            summary_parts.append(self._format_grammar_changes(changes_by_type['grammar']))

        if changes_by_type['style']:
            summary_parts.append(self._format_style_changes(changes_by_type['style']))

        if changes_by_type['table_issues']:
            summary_parts.append(self._format_table_issues(changes_by_type['table_issues']))

        # Cross-reference summary
        if stats.get('crossref'):
            summary_parts.append(self._format_crossref_summary(stats['crossref']))

        # ROI metrics
        summary_parts.append(self._format_roi_metrics(stats, timing_data))

        # Final recommendations
        summary_parts.append(self._generate_recommendations(stats))

        # Combine all parts
        full_summary = "\n".join(summary_parts)

        # Write to file
        output_path = self._write_output(full_summary, document_id)

        return str(output_path)

    async def _extract_changes(self, db, document_id: str) -> Dict[str, List]:
        """Extract changes from database, grouped by type."""
        changes_by_type = defaultdict(list)

        # Get all reviews for this document
        all_chunks = await db.get_all_chunks(document_id)

        for chunk in all_chunks:
            review = await db.get_review(chunk.chunk_id)
            if review and review.changes:
                changes = json.loads(review.changes) if isinstance(review.changes, str) else review.changes

                for change in changes:
                    change_type = change.get('type', 'unknown')
                    if change_type == 'spelling':
                        changes_by_type['spelling'].append(change)
                    elif change_type == 'grammar':
                        changes_by_type['grammar'].append(change)
                    elif change_type == 'style':
                        changes_by_type['style'].append(change)
                    elif change_type in ['table_issue', 'figure_issue']:
                        changes_by_type['table_issues'].append(change)

        return changes_by_type

    def _generate_header(self, stats: Dict, timing_data: Dict) -> str:
        """Generate document header."""
        doc_info = stats.get('document', {})
        proc_info = stats.get('processing', {})

        header = f"""# Review Changes Summary

**Document:** {doc_info.get('filename', 'N/A')}
**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Total Changes:** {stats.get('language_review', {}).get('total_changes', 0):,}

---

## Processing Summary

**Pages Processed:** {doc_info.get('total_pages', 0):,}
**Chunks Processed:** {proc_info.get('completed', 0):,}
**Total Time:** {timing_data.get('total_time', 0):.1f} seconds ({timing_data.get('total_time', 0)/60:.1f} minutes)
**Processing Speed:** {timing_data.get('pages_per_second', 0):.1f} pages/second
**Average Confidence:** {proc_info.get('avg_confidence', 0):.2f}

---

"""
        return header

    def _format_spelling_changes(self, changes: List[Dict]) -> str:
        """Format spelling corrections."""
        if not changes:
            return ""

        # Get unique examples
        examples = self._get_unique_examples(changes, max_examples=5)

        lines = ["## Spelling Corrections", ""]
        lines.append(f"**Total:** {len(changes)} corrections\n")

        if examples:
            lines.append("**Examples:**")
            lines.append("```diff")
            for ex in examples:
                lines.append(f"- {ex['original']}")
                lines.append(f"+ {ex['corrected']}")
            lines.append("```")

        lines.append("\n---\n")
        return "\n".join(lines)

    def _format_grammar_changes(self, changes: List[Dict]) -> str:
        """Format grammar fixes."""
        if not changes:
            return ""

        # Categorize grammar changes
        whitespace_fixes = [c for c in changes if 'space' in c.get('reason', '').lower()]
        punctuation_fixes = [c for c in changes if 'punctuation' in c.get('reason', '').lower()]
        other_fixes = [c for c in changes if c not in whitespace_fixes and c not in punctuation_fixes]

        lines = ["## Grammar & Formatting Fixes", ""]
        lines.append(f"**Total:** {len(changes)} fixes\n")

        if whitespace_fixes:
            lines.append(f"**Whitespace Corrections:** {len(whitespace_fixes)}")
            examples = self._get_unique_examples(whitespace_fixes, max_examples=3)
            if examples:
                lines.append("```diff")
                for ex in examples:
                    orig_repr = repr(ex['original'])
                    corr_repr = repr(ex['corrected'])
                    lines.append(f"- {orig_repr} (extra spaces)")
                    lines.append(f"+ {corr_repr} (single space)")
                lines.append("```")
                lines.append("")

        if punctuation_fixes:
            lines.append(f"**Punctuation Spacing:** {len(punctuation_fixes)}")
            examples = self._get_unique_examples(punctuation_fixes, max_examples=3)
            if examples:
                lines.append("```diff")
                for ex in examples:
                    lines.append(f"- {ex['original']}")
                    lines.append(f"+ {ex['corrected']}")
                lines.append("```")
                lines.append("")

        if other_fixes:
            lines.append(f"**Other Grammar Fixes:** {len(other_fixes)}")

        lines.append("\n---\n")
        return "\n".join(lines)

    def _format_style_changes(self, changes: List[Dict]) -> str:
        """Format style improvements."""
        if not changes:
            return ""

        examples = self._get_unique_examples(changes, max_examples=5)

        lines = ["## Style Improvements", ""]
        lines.append(f"**Total:** {len(changes)} improvements\n")

        if examples:
            lines.append("**Examples:**")
            lines.append("```diff")
            for ex in examples:
                lines.append(f"- {ex['original']}")
                lines.append(f"+ {ex['corrected']}")
                lines.append(f"  # {ex.get('reason', 'Style improvement')}")
            lines.append("```")

        lines.append("\n---\n")
        return "\n".join(lines)

    def _format_table_issues(self, issues: List[Dict]) -> str:
        """Format table and figure issues."""
        if not issues:
            return ""

        # Categorize by severity
        high_severity = [i for i in issues if i.get('severity') == 'high']
        medium_severity = [i for i in issues if i.get('severity') == 'medium']
        low_severity = [i for i in issues if i.get('severity') == 'low']

        lines = ["## Tables & Figures Issues", ""]
        lines.append(f"**Total Issues:** {len(issues)}\n")

        if high_severity:
            lines.append(f"**High Severity:** {len(high_severity)}")
            examples = high_severity[:3]
            for ex in examples:
                lines.append(f"  - {ex.get('description', 'Unknown issue')}")

        if medium_severity:
            lines.append(f"**Medium Severity:** {len(medium_severity)}")

        if low_severity:
            lines.append(f"**Low Severity:** {len(low_severity)}")

        lines.append("\n---\n")
        return "\n".join(lines)

    def _format_crossref_summary(self, crossref: Dict) -> str:
        """Format cross-reference validation summary."""
        total = crossref.get('total', 0)
        valid = crossref.get('valid', 0)
        invalid = crossref.get('invalid', 0)

        if total == 0:
            return ""

        validity_pct = (valid / total * 100) if total > 0 else 0

        lines = ["## Cross-Reference Validation", ""]
        lines.append(f"**Total References:** {total:,}")
        lines.append(f"**Valid:** {valid:,} ({validity_pct:.1f}%)")
        lines.append(f"**Invalid:** {invalid:,} ({100-validity_pct:.1f}%)")
        lines.append("")

        if invalid > 0:
            lines.append("⚠️ **Note:** Invalid references may require manual review to determine if they are")
            lines.append("actually broken or just not detected by the validator.")

        lines.append("\n---\n")
        return "\n".join(lines)

    def _format_roi_metrics(self, stats: Dict, timing_data: Dict) -> str:
        """Format ROI and time savings metrics."""
        total_pages = stats.get('document', {}).get('total_pages', 0)
        processing_time_minutes = timing_data.get('total_time', 0) / 60

        # Calculate estimated manual review time
        manual_time_minutes = total_pages * self.manual_review_time
        time_saved_minutes = manual_time_minutes - processing_time_minutes
        time_saved_hours = time_saved_minutes / 60
        efficiency_pct = (time_saved_minutes / manual_time_minutes * 100) if manual_time_minutes > 0 else 0

        lines = ["## ROI & Time Savings", ""]
        lines.append(f"**Automated Processing Time:** {processing_time_minutes:.1f} minutes")
        lines.append(f"**Estimated Manual Review Time:** {manual_time_minutes:.0f} minutes ({manual_time_minutes/60:.1f} hours)")
        lines.append(f"**Time Saved:** {time_saved_minutes:.0f} minutes ({time_saved_hours:.1f} hours)")
        lines.append(f"**Efficiency Gain:** {efficiency_pct:.0f}%")
        lines.append("")
        lines.append(f"💡 **This review would have taken ~{manual_time_minutes/60:.1f} hours manually!**")

        lines.append("\n---\n")
        return "\n".join(lines)

    def _generate_recommendations(self, stats: Dict) -> str:
        """Generate recommendations based on review results."""
        lines = ["## Recommendations", ""]

        lang_review = stats.get('language_review', {})
        crossref = stats.get('crossref', {})

        if lang_review.get('total_changes', 0) > 0:
            lines.append("✅ **Language Review:** Review completed with automated suggestions")

        if crossref.get('invalid', 0) > 100:
            lines.append("⚠️ **Cross-References:** High number of invalid references detected - recommend manual verification")
        elif crossref.get('invalid', 0) > 0:
            lines.append("✓ **Cross-References:** Some invalid references found - spot check recommended")

        lines.append("")
        lines.append("**Next Steps:**")
        lines.append("1. Review the full output file for detailed changes")
        lines.append("2. Verify high-priority changes (technical terms, cross-references)")
        lines.append("3. Accept/reject automated suggestions")
        lines.append("4. Run final quality check")

        return "\n".join(lines)

    def _get_unique_examples(self, changes: List[Dict], max_examples: int = 5) -> List[Dict]:
        """Get unique change examples."""
        seen = set()
        unique = []

        for change in changes:
            key = (change.get('original'), change.get('corrected'))
            if key not in seen:
                seen.add(key)
                unique.append(change)
                if len(unique) >= max_examples:
                    break

        return unique

    def _write_output(self, summary: str, document_id: str) -> Path:
        """Write summary to file."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_filename = f"changes_diff_{timestamp}.md"
        output_path = self.output_dir / output_filename

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(summary)

        return output_path
