"""
Terminology Consistency Analyzer.

Extracts technical terms and detects variations/inconsistencies.
Helps maintain professional consistency across documentation.

Examples it catches:
- "Wi-Fi" vs "WiFi" vs "wifi" (brand inconsistency)
- "I2C" vs "I²C" (formatting inconsistency)
- "SPI module" vs "SPI peripheral" vs "SPI interface" (terminology inconsistency)
"""

import re
from typing import List, Dict, Set, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict, Counter
import logging

logger = logging.getLogger(__name__)


@dataclass
class Term:
    """Represents a technical term instance."""
    term_id: str
    canonical_form: str  # Normalized form for grouping (lowercase, no special chars)
    actual_form: str  # How it appears in document
    category: str  # 'connectivity', 'peripheral', 'feature', etc.
    locations: List[Tuple[str, int]]  # List of (chunk_id, page_number)
    count: int = 1


@dataclass
class TermVariation:
    """Represents multiple variations of the same term."""
    canonical: str
    variations: Dict[str, int]  # {actual_form: count}
    category: str
    total_instances: int
    recommended_form: str
    severity: str  # 'critical', 'high', 'medium', 'low'
    reason: str


class TerminologyAnalyzer:
    """Analyzes terminology consistency across documentation."""

    def __init__(self, config: Dict):
        self.config = config
        self.enabled = config.get('terminology_analysis', {}).get('enabled', True)

        # Define technical term patterns by category
        self.term_patterns = {
            'connectivity': [
                # Wi-Fi variations
                (r'Wi-?Fi[®™]?', 'Wi-Fi®'),  # Recommended form
                (r'WiFi[®™]?', 'Wi-Fi®'),
                (r'wifi', 'Wi-Fi®'),
                (r'Wi-?fi', 'Wi-Fi®'),
                # Bluetooth
                (r'Bluetooth[®™]?', 'Bluetooth®'),
                (r'BT\b', 'Bluetooth®'),
                # USB
                (r'USB\s*[\d.]+', 'USB'),  # USB 2.0, USB 3.1, etc.
                (r'Universal\s+Serial\s+Bus', 'USB'),
                # Ethernet
                (r'Ethernet', 'Ethernet'),
                (r'ETH\b', 'Ethernet'),
            ],
            'peripherals': [
                # SPI variations
                (r'SPI\s+(?:module|peripheral|interface)', 'SPI peripheral'),
                (r'Serial\s+Peripheral\s+Interface', 'SPI peripheral'),
                # I2C variations
                (r'I[2²]C', 'I²C'),
                (r'Inter-Integrated\s+Circuit', 'I²C'),
                # UART
                (r'UART', 'UART'),
                (r'Universal\s+Asynchronous\s+Receiver/Transmitter', 'UART'),
                # CAN
                (r'CAN\s*FD?', 'CAN'),
                (r'Controller\s+Area\s+Network', 'CAN'),
                # ADC/DAC
                (r'ADC', 'ADC'),
                (r'Analog.to.Digital\s+Converter', 'ADC'),
                (r'DAC', 'DAC'),
                (r'Digital.to.Analog\s+Converter', 'DAC'),
            ],
            'features': [
                # DMA
                (r'DMA', 'DMA'),
                (r'Direct\s+Memory\s+Access', 'DMA'),
                # PWM
                (r'PWM', 'PWM'),
                (r'Pulse.Width\s+Modulation', 'PWM'),
                # Timer variations
                (r'[Tt]imer', 'timer'),  # Lowercase preferred in text
                (r'TIMER', 'Timer'),  # Capitalized in headings
            ],
            'memory': [
                # Flash
                (r'Flash\s+memory', 'Flash memory'),
                (r'flash', 'Flash'),
                # SRAM
                (r'SRAM', 'SRAM'),
                (r'Static\s+RAM', 'SRAM'),
                # EEPROM
                (r'EEPROM', 'EEPROM'),
            ]
        }

        # Build comprehensive pattern list
        self.all_patterns = []
        for category, patterns in self.term_patterns.items():
            for pattern, recommended in patterns:
                self.all_patterns.append((re.compile(pattern, re.IGNORECASE), recommended, category))

    async def analyze_terminology(self, chunks: List) -> Dict:
        """
        Analyze terminology consistency across all chunks.

        Args:
            chunks: All document chunks

        Returns:
            Terminology analysis report
        """
        if not self.enabled:
            return {'enabled': False}

        logger.info("Starting terminology consistency analysis...")

        # Step 1: Extract all term instances
        term_instances = self._extract_term_instances(chunks)
        logger.info(f"Extracted {len(term_instances)} term instances")

        # Step 2: Group by canonical form (detect variations)
        term_groups = self._group_variations(term_instances)
        logger.info(f"Found {len(term_groups)} unique terms")

        # Step 3: Identify inconsistencies
        inconsistencies = self._identify_inconsistencies(term_groups)
        logger.info(f"Detected {len(inconsistencies)} terminology inconsistencies")

        # Step 4: Generate report
        report = self._generate_report(inconsistencies, term_groups)

        return report

    def _extract_term_instances(self, chunks: List) -> List[Term]:
        """Extract all technical term instances from chunks."""
        term_instances = []
        term_id_counter = 0

        for chunk in chunks:
            content = chunk.content

            # Try each pattern
            for pattern_re, recommended, category in self.all_patterns:
                matches = pattern_re.finditer(content)

                for match in matches:
                    actual_form = match.group(0)
                    canonical = self._canonicalize(actual_form)

                    term = Term(
                        term_id=f"term_{term_id_counter}",
                        canonical_form=canonical,
                        actual_form=actual_form,
                        category=category,
                        locations=[(chunk.chunk_id, chunk.page_start)],
                        count=1
                    )
                    term_instances.append(term)
                    term_id_counter += 1

        return term_instances

    def _canonicalize(self, term: str) -> str:
        """
        Convert term to canonical form for grouping.

        Examples:
        - "Wi-Fi®" -> "wifi"
        - "WiFi" -> "wifi"
        - "I²C" -> "i2c"
        - "I2C" -> "i2c"
        """
        # Remove special characters
        canonical = re.sub(r'[®™©\-_\s]', '', term)
        # Normalize superscripts
        canonical = canonical.replace('²', '2')
        canonical = canonical.replace('³', '3')
        # Lowercase
        canonical = canonical.lower()

        return canonical

    def _group_variations(self, term_instances: List[Term]) -> Dict[str, List[Term]]:
        """Group term instances by canonical form."""
        groups = defaultdict(list)

        for term in term_instances:
            groups[term.canonical_form].append(term)

        return dict(groups)

    def _identify_inconsistencies(
        self,
        term_groups: Dict[str, List[Term]]
    ) -> List[TermVariation]:
        """
        Identify terms with multiple variations.

        Args:
            term_groups: Terms grouped by canonical form

        Returns:
            List of terms with inconsistent usage
        """
        inconsistencies = []

        for canonical, instances in term_groups.items():
            # Count variations
            variation_counts = Counter(term.actual_form for term in instances)

            # Only report if there are multiple variations
            if len(variation_counts) > 1:
                # Determine recommended form
                category = instances[0].category
                recommended = self._determine_recommended_form(
                    canonical, variation_counts, category
                )

                # Calculate severity
                severity, reason = self._calculate_severity(
                    canonical, variation_counts, category
                )

                inconsistency = TermVariation(
                    canonical=canonical,
                    variations=dict(variation_counts),
                    category=category,
                    total_instances=sum(variation_counts.values()),
                    recommended_form=recommended,
                    severity=severity,
                    reason=reason
                )
                inconsistencies.append(inconsistency)

        # Sort by severity and total instances
        severity_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        inconsistencies.sort(
            key=lambda x: (severity_order[x.severity], -x.total_instances)
        )

        return inconsistencies

    def _determine_recommended_form(
        self,
        canonical: str,
        variations: Counter,
        category: str
    ) -> str:
        """
        Determine the recommended form for a term.

        Priority:
        1. Branded forms (®, ™) take precedence
        2. Most common form
        3. Proper capitalization/formatting
        """
        # Check for branded forms (®, ™)
        for form in variations:
            if '®' in form or '™' in form:
                return form

        # Check for proper formatting (superscripts for I²C, etc.)
        if canonical == 'i2c':
            for form in variations:
                if '²' in form:
                    return form

        # Default to most common form
        most_common = variations.most_common(1)[0][0]
        return most_common

    def _calculate_severity(
        self,
        canonical: str,
        variations: Counter,
        category: str
    ) -> Tuple[str, str]:
        """
        Calculate severity of terminology inconsistency.

        Returns:
            Tuple of (severity, reason)
        """
        total = sum(variations.values())
        variation_count = len(variations)

        # Critical: Brand compliance issues
        if category == 'connectivity':
            has_branded = any('®' in v or '™' in v for v in variations)
            has_unbranded = any('®' not in v and '™' not in v for v in variations)

            if has_branded and has_unbranded:
                return 'critical', 'Brand compliance issue (mix of branded/unbranded)'

        # High: Many instances, many variations
        if total > 20 and variation_count > 3:
            return 'high', f'High frequency ({total} instances) with {variation_count} variations'

        # Medium: Moderate inconsistency
        if total > 10:
            return 'medium', f'Moderate frequency ({total} instances) with inconsistent usage'

        # Low: Few instances
        return 'low', f'Low frequency ({total} instances)'

    def _generate_report(
        self,
        inconsistencies: List[TermVariation],
        all_terms: Dict[str, List[Term]]
    ) -> Dict:
        """Generate terminology analysis report."""

        # Group by severity
        by_severity = {
            'critical': [],
            'high': [],
            'medium': [],
            'low': []
        }

        for inc in inconsistencies:
            by_severity[inc.severity].append({
                'term': inc.canonical,
                'recommended': inc.recommended_form,
                'variations': inc.variations,
                'total_instances': inc.total_instances,
                'category': inc.category,
                'reason': inc.reason
            })

        # Calculate statistics
        total_unique_terms = len(all_terms)
        total_instances = sum(len(instances) for instances in all_terms.values())
        inconsistent_terms = len(inconsistencies)

        report = {
            'enabled': True,
            'total_unique_terms': total_unique_terms,
            'total_instances': total_instances,
            'inconsistent_terms': inconsistent_terms,
            'consistency_rate': round(
                100 * (1 - inconsistent_terms / total_unique_terms) if total_unique_terms > 0 else 0,
                1
            ),
            'by_severity': {
                'critical': len(by_severity['critical']),
                'high': len(by_severity['high']),
                'medium': len(by_severity['medium']),
                'low': len(by_severity['low'])
            },
            'critical_issues': by_severity['critical'],
            'high_priority_issues': by_severity['high'],
            'medium_priority_issues': by_severity['medium'],
            'low_priority_issues': by_severity['low'],
            'summary_text': self._generate_summary_text(
                inconsistencies, total_instances
            )
        }

        return report

    def _generate_summary_text(
        self,
        inconsistencies: List[TermVariation],
        total_instances: int
    ) -> str:
        """Generate human-readable summary."""
        if not inconsistencies:
            return "✅ No terminology inconsistencies detected. All technical terms are used consistently."

        critical = sum(1 for i in inconsistencies if i.severity == 'critical')
        high = sum(1 for i in inconsistencies if i.severity == 'high')

        summary = f"Found {len(inconsistencies)} terminology inconsistencies across {total_instances} term instances.\n"

        if critical > 0:
            summary += f"⚠️ {critical} critical issues (brand compliance)\n"

        if high > 0:
            summary += f"🔸 {high} high-priority issues (high frequency with many variations)\n"

        # Top 3 issues
        summary += "\nTop issues:\n"
        for i, inc in enumerate(inconsistencies[:3], 1):
            top_variation = max(inc.variations.items(), key=lambda x: x[1])
            summary += f"{i}. \"{inc.canonical}\" - {len(inc.variations)} variations, recommend \"{inc.recommended_form}\"\n"

        return summary
