"""
Smart review queue with intelligent API integration.
Optimizes human review by leveraging rule-based + LLM hybrid approach.
"""

import asyncio
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime

from database import ReviewDatabase
from semantic_search import SemanticSearchEngine
from pattern_library import PatternLibrary


@dataclass
class QueueItem:
    """Item in review queue."""
    chunk_id: str
    content: str
    rule_suggestion: Optional[str]
    rule_confidence: float
    priority: str  # 'high', 'normal', 'low'
    metadata: Dict


@dataclass
class ReviewResult:
    """Result from API review."""
    chunk_id: str
    suggestion: str
    confidence: float
    source: str  # 'rule', 'api', 'hybrid', 'needs_human'
    reasoning: Optional[str] = None


class SmartReviewQueue:
    """Intelligent review queue with LLM-powered prioritization."""

    def __init__(self, db_path: str = "review_state.db", config: dict = None):
        self.db = ReviewDatabase(db_path)
        self.config = config or {}

        # NEW: Semantic features for context retrieval
        self.semantic_search = SemanticSearchEngine(config)
        self.pattern_library = PatternLibrary(config)
        self.use_context = config.get('smart_queue', {}).get('use_context_retrieval', True)

    async def process_with_api(self, document_id: str, api_client) -> Dict:
        """
        Process document with intelligent API integration.

        Args:
            document_id: Document identifier
            api_client: Your internal API client (must have review_batch method)

        Returns:
            Processing results with statistics
        """
        await self.db.connect()

        try:
            # Get all chunks needing review
            pending = await self.db.get_pending_reviews(document_id)

            print(f"\n{'='*60}")
            print(f"Smart Review Queue: {len(pending)} chunks to process")
            print(f"{'='*60}\n")

            # Triage: Categorize by confidence
            auto_approve = []
            api_queue = []

            for chunk_id in pending:
                review = await self.db.get_review(chunk_id)
                chunk = await self.db.get_chunk(chunk_id)

                if review and review.confidence_score > 0.95:
                    # High confidence - auto-approve
                    auto_approve.append(chunk_id)
                elif review and review.confidence_score < 0.7:
                    # Low confidence - high priority for API
                    api_queue.append({
                        'chunk_id': chunk_id,
                        'priority': 'high',
                        'content': chunk.content,
                        'rule_suggestion': review.reviewed_content,
                        'rule_confidence': review.confidence_score
                    })
                else:
                    # Medium confidence - normal priority for API
                    api_queue.append({
                        'chunk_id': chunk_id,
                        'priority': 'normal',
                        'content': chunk.content,
                        'rule_suggestion': review.reviewed_content if review else chunk.content,
                        'rule_confidence': review.confidence_score if review else 0.5
                    })

            print(f"Triage Results:")
            print(f"  Auto-approved (high confidence): {len(auto_approve)}")
            print(f"  Sending to API: {len(api_queue)}")
            print(f"  - High priority: {sum(1 for item in api_queue if item['priority'] == 'high')}")
            print(f"  - Normal priority: {sum(1 for item in api_queue if item['priority'] == 'normal')}\n")

            # Process with API if available
            api_results = []
            if api_client and api_queue:
                print("Processing with API...")
                api_results = await self._batch_process_api(api_client, api_queue)
                print(f"API processing complete: {len(api_results)} results\n")

            # Merge API suggestions with rule-based suggestions
            final_reviews = self._merge_suggestions(api_results, api_queue)

            # Count results
            needs_human = len([r for r in final_reviews if r.confidence < 0.9])

            print(f"Final Results:")
            print(f"  Auto-approved: {len(auto_approve)}")
            print(f"  API-reviewed: {len(api_results)}")
            print(f"  Needs human review: {needs_human}")
            print(f"{'='*60}\n")

            return {
                'auto_approved': len(auto_approve),
                'api_reviewed': len(api_results),
                'needs_human': needs_human,
                'total_processed': len(pending),
                'results': final_reviews,
                'auto_approve_ids': auto_approve
            }

        finally:
            await self.db.close()

    async def _batch_process_api(self, api_client, queue: List[Dict]) -> List[ReviewResult]:
        """
        Send batches to API with rate limiting.

        Args:
            api_client: API client with review_batch method
            queue: List of items to process

        Returns:
            List of API results
        """
        results = []

        # Process in batches of 10 to avoid rate limits
        batch_size = 10

        for i in range(0, len(queue), batch_size):
            batch = queue[i:i+batch_size]

            # NEW: Prepare API requests with context retrieval
            api_requests = []
            for item in batch:
                # Get context from past reviews if enabled
                historical_context = None
                if self.use_context and self.semantic_search.is_available():
                    historical_context = await self._get_review_context(item['content'])

                api_requests.append({
                    'content': item['content'],
                    'context': 'technical_datasheet',
                    'priority': item['priority'],
                    'rule_suggestion': item.get('rule_suggestion'),
                    'rule_confidence': item.get('rule_confidence', 0.5),
                    'historical_context': historical_context  # NEW: Past similar reviews
                })

            try:
                # Call API (user must implement review_batch method)
                if hasattr(api_client, 'review_batch'):
                    batch_results = await api_client.review_batch(api_requests)
                else:
                    # Fallback: Call review method individually
                    batch_results = []
                    for req in api_requests:
                        result = await api_client.review(req)
                        batch_results.append(result)

                # Map results back to chunk IDs
                for item, api_result in zip(batch, batch_results):
                    results.append(ReviewResult(
                        chunk_id=item['chunk_id'],
                        suggestion=api_result.get('suggestion', item['rule_suggestion']),
                        confidence=api_result.get('confidence', 0.7),
                        source='api',
                        reasoning=api_result.get('reasoning')
                    ))

            except Exception as e:
                print(f"API error for batch {i//batch_size + 1}: {e}")
                # Fallback to rule-based for this batch
                for item in batch:
                    results.append(ReviewResult(
                        chunk_id=item['chunk_id'],
                        suggestion=item['rule_suggestion'],
                        confidence=item['rule_confidence'],
                        source='rule_fallback',
                        reasoning=f"API error: {str(e)}"
                    ))

            # Rate limiting delay
            if i + batch_size < len(queue):
                await asyncio.sleep(0.5)  # 500ms between batches

        return results

    def _merge_suggestions(self, api_results: List[ReviewResult],
                          queue_items: List[Dict]) -> List[ReviewResult]:
        """
        Merge rule-based + API suggestions intelligently.

        Args:
            api_results: Results from API
            queue_items: Original queue items with rule suggestions

        Returns:
            Merged results with final decisions
        """
        merged = []

        # Create lookup for rule suggestions
        rule_lookup = {item['chunk_id']: item for item in queue_items}

        for api_result in api_results:
            rule_item = rule_lookup.get(api_result.chunk_id)

            if not rule_item:
                merged.append(api_result)
                continue

            rule_suggestion = rule_item.get('rule_suggestion', '')
            rule_confidence = rule_item.get('rule_confidence', 0.5)

            # Strategy 1: Agreement boosts confidence
            if api_result.suggestion == rule_suggestion:
                merged.append(ReviewResult(
                    chunk_id=api_result.chunk_id,
                    suggestion=api_result.suggestion,
                    confidence=min(0.98, (api_result.confidence + rule_confidence) / 2 * 1.1),
                    source='hybrid_agreement',
                    reasoning=f"Rule-based and API agree"
                ))

            # Strategy 2: API very confident, trust it
            elif api_result.confidence > 0.9:
                merged.append(ReviewResult(
                    chunk_id=api_result.chunk_id,
                    suggestion=api_result.suggestion,
                    confidence=api_result.confidence,
                    source='api_high_confidence',
                    reasoning=api_result.reasoning
                ))

            # Strategy 3: Rule-based very confident, might be API error
            elif rule_confidence > 0.9:
                merged.append(ReviewResult(
                    chunk_id=api_result.chunk_id,
                    suggestion=rule_suggestion,
                    confidence=rule_confidence,
                    source='rule_high_confidence',
                    reasoning=f"Rule-based very confident, API disagreed"
                ))

            # Strategy 4: Both uncertain, flag for human
            elif api_result.confidence < 0.8 and rule_confidence < 0.8:
                merged.append(ReviewResult(
                    chunk_id=api_result.chunk_id,
                    suggestion=None,
                    confidence=0.5,
                    source='needs_human',
                    reasoning=f"Both rule-based and API uncertain"
                ))

            # Strategy 5: Moderate disagreement, use average
            else:
                avg_conf = (api_result.confidence + rule_confidence) / 2
                merged.append(ReviewResult(
                    chunk_id=api_result.chunk_id,
                    suggestion=api_result.suggestion,  # Prefer API when moderate
                    confidence=avg_conf,
                    source='hybrid_moderate',
                    reasoning=f"API: {api_result.confidence:.2f}, Rule: {rule_confidence:.2f}"
                ))

        return merged

    async def get_human_review_queue(self, document_id: str) -> List[Dict]:
        """
        Get prioritized queue for human review.

        Args:
            document_id: Document identifier

        Returns:
            List of items needing human review, sorted by priority
        """
        await self.db.connect()

        try:
            all_reviews = []
            chunks = await self.db.get_all_chunks(document_id)

            for chunk in chunks:
                review = await self.db.get_review(chunk.chunk_id)

                if review and review.confidence_score < 0.9:
                    all_reviews.append({
                        'chunk_id': chunk.chunk_id,
                        'section': chunk.section_hierarchy,
                        'page': chunk.page_start,
                        'confidence': review.confidence_score,
                        'original': chunk.content[:200],
                        'suggestion': review.reviewed_content[:200] if review.reviewed_content else None,
                        'changes_count': len(review.changes),
                        'priority': self._calculate_review_priority(review, chunk)
                    })

            # Sort by priority (high first), then by confidence (low first)
            all_reviews.sort(key=lambda x: (
                {'high': 0, 'medium': 1, 'low': 2}[x['priority']],
                x['confidence']
            ))

            return all_reviews

        finally:
            await self.db.close()

    def _calculate_review_priority(self, review, chunk) -> str:
        """Calculate priority for human review."""
        # Very low confidence = high priority
        if review.confidence_score < 0.6:
            return 'high'

        # Many changes = medium priority
        if len(review.changes) > 10:
            return 'medium'

        # Early sections more important
        if chunk.page_start < 50:
            return 'medium'

        return 'low'

    async def _get_review_context(self, content: str) -> Optional[Dict]:
        """
        Retrieve historical context for a chunk from past reviews.
        Uses semantic search to find similar chunks and pattern library for corrections.

        Args:
            content: Chunk content to find context for

        Returns:
            Dict with similar reviews and suggested patterns, or None
        """
        if not self.use_context or not self.semantic_search.is_available():
            return None

        try:
            # Find similar patterns from pattern library
            patterns = self.pattern_library.find_similar_patterns(content, n_results=3)

            # Get pattern suggestion
            suggestion = self.pattern_library.suggest_correction(content, threshold=0.85)

            if patterns or suggestion:
                return {
                    'similar_patterns': patterns[:2] if patterns else [],  # Top 2 patterns
                    'suggested_correction': suggestion,
                    'confidence_boost': len(patterns) * 0.05  # Small boost for having historical data
                }

        except Exception as e:
            print(f"⚠️ Error retrieving context: {e}")

        return None


# Example integration with your internal API
class InternalAPIClient:
    """
    Example implementation of internal API client.
    Replace this with your actual API integration.
    """

    def __init__(self, endpoint: str, auth_token: str):
        self.endpoint = endpoint
        self.auth_token = auth_token

    async def review(self, request: Dict) -> Dict:
        """
        Review a single text.

        Args:
            request: {
                'content': str,
                'context': str,
                'priority': str,
                'rule_suggestion': str (optional),
                'rule_confidence': float (optional)
            }

        Returns:
            {
                'suggestion': str,
                'confidence': float,
                'reasoning': str
            }
        """
        # TODO: Implement your API call here
        # Example:
        # async with httpx.AsyncClient() as client:
        #     response = await client.post(
        #         f"{self.endpoint}/review",
        #         headers={"Authorization": f"Bearer {self.auth_token}"},
        #         json=request
        #     )
        #     return response.json()

        # Placeholder implementation
        return {
            'suggestion': request.get('content'),
            'confidence': 0.8,
            'reasoning': 'Example API response'
        }

    async def review_batch(self, requests: List[Dict]) -> List[Dict]:
        """
        Review a batch of texts.

        Args:
            requests: List of review requests

        Returns:
            List of review responses
        """
        # TODO: Implement batch API call
        # For now, call review() for each
        results = []
        for req in requests:
            result = await self.review(req)
            results.append(result)
        return results


async def main():
    """Example usage."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python smart_queue.py <document_id>")
        sys.exit(1)

    document_id = sys.argv[1]

    # Initialize queue
    queue = SmartReviewQueue()

    # Example: Get human review queue
    print("Fetching human review queue...")
    human_queue = await queue.get_human_review_queue(document_id)

    print(f"\nHuman Review Queue: {len(human_queue)} items")
    print("\nTop 5 Priority Items:")
    for item in human_queue[:5]:
        print(f"  [{item['priority'].upper()}] {item['section']} (page {item['page']})")
        print(f"    Confidence: {item['confidence']:.2f}")
        print(f"    Changes: {item['changes_count']}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
