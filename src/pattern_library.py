"""
Pattern library for learning from past reviews.
Builds institutional knowledge by storing and retrieving common corrections.
"""

from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime

from semantic_search import SemanticSearchEngine
from embeddings import EmbeddingGenerator


@dataclass
class ReviewPattern:
    """Represents a learned pattern from past reviews."""
    pattern_id: str
    original_text: str
    corrected_text: str
    issue_type: str  # 'spelling', 'grammar', 'style', 'technical', 'cross_ref'
    confidence: float
    frequency: int  # How many times this pattern has been seen
    created_at: str
    last_seen: str
    metadata: Dict


class PatternLibrary:
    """
    Learns from past reviews and suggests corrections based on similar patterns.
    Uses ChromaDB for semantic similarity search of patterns.
    """

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.embedding_generator = EmbeddingGenerator(config)
        self.search_engine = SemanticSearchEngine(config, db_path="./pattern_library_db")
        self.collection_name = "review_patterns"
        self.available = self.search_engine.is_available()

        if self.available:
            print("✅ Pattern library initialized (semantic learning enabled)")
        else:
            print("⚠️ Pattern library unavailable (semantic features disabled)")

    def is_available(self) -> bool:
        """Check if pattern library is available."""
        return self.available

    def add_pattern(self, original: str, corrected: str, issue_type: str,
                   confidence: float, metadata: dict = None) -> bool:
        """
        Add a new pattern to the library.

        Args:
            original: Original text with issue
            corrected: Corrected version
            issue_type: Type of issue
            confidence: Confidence score
            metadata: Additional metadata

        Returns:
            True if successful
        """
        if not self.available:
            return False

        try:
            # Generate pattern ID
            import hashlib
            pattern_id = hashlib.md5(f"{original}_{corrected}".encode()).hexdigest()[:16]

            # Check if pattern already exists
            existing = self._get_pattern_by_id(pattern_id)

            if existing:
                # Update frequency and last_seen
                return self._update_pattern_frequency(pattern_id)

            # Create new pattern
            now = datetime.now().isoformat()

            pattern_data = {
                'chunk_id': pattern_id,
                'content': f"Original: {original}\nCorrected: {corrected}",
                'metadata': {
                    'pattern_id': pattern_id,
                    'original_text': original,
                    'corrected_text': corrected,
                    'issue_type': issue_type,
                    'confidence': confidence,
                    'frequency': 1,
                    'created_at': now,
                    'last_seen': now,
                    **(metadata or {})
                }
            }

            # Add to ChromaDB
            success = self.search_engine.add_chunks(self.collection_name, [pattern_data])

            if success:
                print(f"✅ Added new pattern: {issue_type} (ID: {pattern_id})")

            return success

        except Exception as e:
            print(f"❌ Error adding pattern: {e}")
            return False

    def find_similar_patterns(self, text: str, n_results: int = 5,
                             issue_type: str = None) -> List[Dict]:
        """
        Find patterns similar to given text.

        Args:
            text: Text to find similar patterns for
            n_results: Number of results
            issue_type: Optional filter by issue type

        Returns:
            List of similar patterns with suggested corrections
        """
        if not self.available:
            return []

        try:
            # Build metadata filter if issue_type specified
            filter_metadata = {'issue_type': issue_type} if issue_type else None

            # Search for similar patterns
            results = self.search_engine.search_similar(
                self.collection_name,
                text,
                n_results=n_results,
                filter_metadata=filter_metadata
            )

            # Format results
            patterns = []
            for result in results:
                metadata = result.get('metadata', {})
                patterns.append({
                    'pattern_id': metadata.get('pattern_id'),
                    'original_text': metadata.get('original_text'),
                    'corrected_text': metadata.get('corrected_text'),
                    'issue_type': metadata.get('issue_type'),
                    'confidence': metadata.get('confidence'),
                    'frequency': metadata.get('frequency', 1),
                    'similarity': result.get('similarity'),
                    'last_seen': metadata.get('last_seen')
                })

            return patterns

        except Exception as e:
            print(f"❌ Error finding similar patterns: {e}")
            return []

    def suggest_correction(self, text: str, threshold: float = 0.85) -> Optional[Dict]:
        """
        Suggest a correction based on learned patterns.

        Args:
            text: Text to suggest correction for
            threshold: Minimum similarity threshold

        Returns:
            Dict with suggestion or None if no good match
        """
        if not self.available:
            return None

        patterns = self.find_similar_patterns(text, n_results=1)

        if patterns and patterns[0]['similarity'] >= threshold:
            pattern = patterns[0]
            return {
                'suggestion': pattern['corrected_text'],
                'confidence': pattern['confidence'] * pattern['similarity'],
                'issue_type': pattern['issue_type'],
                'reasoning': f"Similar to {pattern['frequency']} past corrections (similarity: {pattern['similarity']:.2f})"
            }

        return None

    def learn_from_review(self, original_text: str, corrected_text: str,
                         changes: List[Dict], confidence: float) -> int:
        """
        Learn patterns from a completed review.

        Args:
            original_text: Original content
            corrected_text: Corrected content
            changes: List of changes made
            confidence: Review confidence

        Returns:
            Number of patterns learned
        """
        if not self.available:
            return 0

        patterns_learned = 0

        for change in changes:
            # Extract pattern from change
            issue_type = change.get('change_type', 'unknown')
            original = change.get('original', '')
            corrected = change.get('corrected', '')

            if original and corrected and original != corrected:
                success = self.add_pattern(
                    original=original,
                    corrected=corrected,
                    issue_type=issue_type,
                    confidence=confidence,
                    metadata={
                        'change_reason': change.get('reason', ''),
                        'position': change.get('position', -1)
                    }
                )

                if success:
                    patterns_learned += 1

        if patterns_learned > 0:
            print(f"✅ Learned {patterns_learned} new patterns from review")

        return patterns_learned

    def get_stats(self) -> Dict:
        """Get pattern library statistics."""
        if not self.available:
            return {'available': False}

        try:
            stats = self.search_engine.get_collection_stats(self.collection_name)

            # Get patterns by issue type (if we had this data)
            return {
                'available': True,
                'total_patterns': stats.get('count', 0),
                'collection_name': stats.get('name'),
            }
        except Exception as e:
            return {'available': False, 'error': str(e)}

    def _get_pattern_by_id(self, pattern_id: str) -> Optional[Dict]:
        """Internal: Get pattern by ID."""
        # Note: ChromaDB doesn't have great support for exact ID lookup
        # This is a simplified implementation
        return None

    def _update_pattern_frequency(self, pattern_id: str) -> bool:
        """Internal: Update pattern frequency."""
        # Note: ChromaDB doesn't support in-place updates easily
        # Would need to delete and re-add with updated frequency
        # Simplified implementation for now
        return True

    def clear(self) -> bool:
        """Clear all patterns (use with caution!)."""
        if not self.available:
            return False

        try:
            return self.search_engine.delete_collection(self.collection_name)
        except Exception as e:
            print(f"❌ Error clearing patterns: {e}")
            return False


# Example usage
if __name__ == "__main__":
    print("\n" + "="*60)
    print("Pattern Library Test")
    print("="*60)

    # Initialize
    library = PatternLibrary()

    if library.is_available():
        print("\n✅ Pattern library is available!")

        # Add some example patterns
        print("\nAdding example patterns...")

        library.add_pattern(
            original="occured",
            corrected="occurred",
            issue_type="spelling",
            confidence=0.95,
            metadata={'common_typo': True}
        )

        library.add_pattern(
            original="The device support WiFi",
            corrected="The device supports WiFi",
            issue_type="grammar",
            confidence=0.92
        )

        library.add_pattern(
            original="Operating voltage 3.3V +/- 10%",
            corrected="Operating voltage: 3.3V ±10%",
            issue_type="style",
            confidence=0.88
        )

        # Test finding similar patterns
        print("\nTest 1: Find similar patterns to 'occured in testing'")
        patterns = library.find_similar_patterns("The error occured in testing", n_results=2)

        for i, pattern in enumerate(patterns, 1):
            print(f"\nPattern {i} (similarity: {pattern['similarity']:.3f}):")
            print(f"  Type: {pattern['issue_type']}")
            print(f"  Original: {pattern['original_text']}")
            print(f"  Corrected: {pattern['corrected_text']}")
            print(f"  Frequency: {pattern['frequency']}")

        # Test suggestion
        print("\nTest 2: Suggest correction for 'The chip support Bluetooth'")
        suggestion = library.suggest_correction("The chip support Bluetooth", threshold=0.7)

        if suggestion:
            print(f"  Suggestion: {suggestion['suggestion']}")
            print(f"  Confidence: {suggestion['confidence']:.2f}")
            print(f"  Reasoning: {suggestion['reasoning']}")
        else:
            print("  No suggestion found")

        # Stats
        print("\nPattern library stats:")
        stats = library.get_stats()
        print(f"  Total patterns: {stats.get('total_patterns', 0)}")
        print(f"  Collection: {stats.get('collection_name')}")

        # Cleanup
        print("\nCleaning up...")
        library.clear()

        print("\n" + "="*60)
        print("All tests completed!")
        print("="*60)

    else:
        print("\n⚠️ Pattern library not available.")
        print("Install dependencies:")
        print("  pip install chromadb sentence-transformers")
