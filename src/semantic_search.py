"""
Semantic search module with ChromaDB integration.
Provides similarity search and embedding storage with graceful fallback to SQLite.
"""

from typing import List, Dict, Optional, Tuple
import os

from embeddings import EmbeddingGenerator


class SemanticSearchEngine:
    """
    Semantic search engine with ChromaDB backend.
    Gracefully falls back to SQLite-only mode if ChromaDB unavailable.
    """

    def __init__(self, config: dict = None, db_path: str = "./chroma_db"):
        self.config = config or {}
        self.db_path = db_path
        self.client = None
        self.available = False
        self.embedding_generator = EmbeddingGenerator(config)

        # Try to initialize ChromaDB
        if self.embedding_generator.is_available():
            try:
                import chromadb
                from chromadb.config import Settings

                # Initialize ChromaDB client
                self.client = chromadb.PersistentClient(
                    path=db_path,
                    settings=Settings(
                        anonymized_telemetry=False,  # No telemetry
                        allow_reset=False,            # Security: prevent accidental wipes
                    )
                )
                self.available = True
                print(f"✅ ChromaDB initialized at: {db_path}")
            except ImportError:
                print("⚠️ ChromaDB not installed. Semantic search disabled.")
                print("   Install with: pip install chromadb")
            except Exception as e:
                print(f"⚠️ Failed to initialize ChromaDB: {e}")
                print("   Semantic search disabled.")
        else:
            print("⚠️ Semantic search unavailable (embeddings not available)")

    def is_available(self) -> bool:
        """Check if semantic search is available."""
        return self.available and self.embedding_generator.is_available()

    def create_collection(self, document_id: str, metadata: dict = None) -> Optional[object]:
        """
        Create a new collection for a document.
        Uses user-per-collection isolation for security.

        Args:
            document_id: Unique document identifier
            metadata: Optional collection metadata

        Returns:
            Collection object or None if unavailable
        """
        if not self.available:
            return None

        try:
            # Use document_id as collection name (user-per-collection isolation)
            collection_name = f"doc_{document_id}"

            # Get or create collection
            collection = self.client.get_or_create_collection(
                name=collection_name,
                metadata=metadata or {"document_id": document_id}
            )

            print(f"✅ Collection created/retrieved: {collection_name}")
            return collection
        except Exception as e:
            print(f"❌ Error creating collection: {e}")
            return None

    def add_chunks(self, document_id: str, chunks: List[Dict]) -> bool:
        """
        Add document chunks to ChromaDB with embeddings.

        Args:
            document_id: Document identifier
            chunks: List of dicts with 'chunk_id', 'content', 'metadata'

        Returns:
            True if successful, False otherwise
        """
        if not self.available:
            return False

        try:
            collection = self.create_collection(document_id)
            if not collection:
                return False

            # Prepare data
            ids = [chunk['chunk_id'] for chunk in chunks]
            texts = [chunk['content'] for chunk in chunks]
            metadatas = [chunk.get('metadata', {}) for chunk in chunks]

            # Generate embeddings
            print(f"Generating embeddings for {len(texts)} chunks...")
            embeddings = self.embedding_generator.encode(texts, show_progress=True)

            if embeddings is None:
                print("❌ Failed to generate embeddings")
                return False

            # Add to ChromaDB
            collection.add(
                ids=ids,
                embeddings=embeddings.tolist(),
                documents=texts,
                metadatas=metadatas
            )

            print(f"✅ Added {len(chunks)} chunks to collection")
            return True

        except Exception as e:
            print(f"❌ Error adding chunks: {e}")
            return False

    def search_similar(self, document_id: str, query: str, n_results: int = 5,
                      filter_metadata: dict = None) -> List[Dict]:
        """
        Search for similar chunks using semantic similarity.

        Args:
            document_id: Document identifier
            query: Query text
            n_results: Number of results to return
            filter_metadata: Optional metadata filter

        Returns:
            List of dicts with 'chunk_id', 'content', 'similarity', 'metadata'
        """
        if not self.available:
            return []

        try:
            collection_name = f"doc_{document_id}"
            collection = self.client.get_collection(name=collection_name)

            # Generate query embedding
            query_embedding = self.embedding_generator.encode_single(query)

            if query_embedding is None:
                return []

            # Search
            results = collection.query(
                query_embeddings=[query_embedding.tolist()],
                n_results=n_results,
                where=filter_metadata  # Optional metadata filtering
            )

            # Format results
            formatted_results = []
            if results and results['ids'] and len(results['ids']) > 0:
                for i in range(len(results['ids'][0])):
                    formatted_results.append({
                        'chunk_id': results['ids'][0][i],
                        'content': results['documents'][0][i],
                        'similarity': 1 - results['distances'][0][i],  # Convert distance to similarity
                        'metadata': results['metadatas'][0][i] if results['metadatas'] else {}
                    })

            return formatted_results

        except Exception as e:
            print(f"❌ Error searching: {e}")
            return []

    def find_similar_chunks(self, document_id: str, chunk_content: str,
                           n_results: int = 5, exclude_chunk_id: str = None) -> List[Dict]:
        """
        Find chunks similar to a given chunk.

        Args:
            document_id: Document identifier
            chunk_content: Content of the chunk to find similar chunks for
            n_results: Number of results
            exclude_chunk_id: Chunk ID to exclude from results

        Returns:
            List of similar chunks
        """
        results = self.search_similar(document_id, chunk_content, n_results + 1)

        # Filter out the query chunk itself
        if exclude_chunk_id:
            results = [r for r in results if r['chunk_id'] != exclude_chunk_id]

        return results[:n_results]

    def get_collection_stats(self, document_id: str) -> Dict:
        """Get statistics about a collection."""
        if not self.available:
            return {'available': False}

        try:
            collection_name = f"doc_{document_id}"
            collection = self.client.get_collection(name=collection_name)

            return {
                'available': True,
                'name': collection_name,
                'count': collection.count(),
                'metadata': collection.metadata
            }
        except Exception as e:
            return {'available': False, 'error': str(e)}

    def delete_collection(self, document_id: str) -> bool:
        """Delete a collection (cleanup)."""
        if not self.available:
            return False

        try:
            collection_name = f"doc_{document_id}"
            self.client.delete_collection(name=collection_name)
            print(f"✅ Deleted collection: {collection_name}")
            return True
        except Exception as e:
            print(f"❌ Error deleting collection: {e}")
            return False

    def list_collections(self) -> List[str]:
        """List all collections."""
        if not self.available:
            return []

        try:
            collections = self.client.list_collections()
            return [c.name for c in collections]
        except Exception as e:
            print(f"❌ Error listing collections: {e}")
            return []


class SemanticDiffMatcher:
    """Helper for semantic document comparison."""

    def __init__(self, embedding_generator: EmbeddingGenerator):
        self.embedding_generator = embedding_generator

    def align_sections_semantically(self, sections_v1: List[Dict],
                                    sections_v2: List[Dict],
                                    similarity_threshold: float = 0.7) -> List[Tuple[Dict, Dict, float]]:
        """
        Align sections from two document versions using semantic similarity.

        Args:
            sections_v1: Sections from version 1 [{'title': ..., 'content': ...}, ...]
            sections_v2: Sections from version 2
            similarity_threshold: Minimum similarity to consider a match

        Returns:
            List of (section_v1, section_v2, similarity_score) tuples
        """
        if not self.embedding_generator.is_available():
            return []

        alignments = []

        # Generate embeddings for all sections
        texts_v1 = [s['content'] for s in sections_v1]
        texts_v2 = [s['content'] for s in sections_v2]

        emb_v1 = self.embedding_generator.encode(texts_v1)
        emb_v2 = self.embedding_generator.encode(texts_v2)

        if emb_v1 is None or emb_v2 is None:
            return []

        # For each section in v1, find best match in v2
        import numpy as np

        for i, section_v1 in enumerate(sections_v1):
            best_similarity = -1
            best_match_idx = -1

            # Calculate similarity with all v2 sections
            for j in range(len(sections_v2)):
                similarity = np.dot(emb_v1[i], emb_v2[j]) / (
                    np.linalg.norm(emb_v1[i]) * np.linalg.norm(emb_v2[j])
                )

                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match_idx = j

            # Add alignment if above threshold
            if best_similarity >= similarity_threshold and best_match_idx >= 0:
                alignments.append((
                    section_v1,
                    sections_v2[best_match_idx],
                    float(best_similarity)
                ))

        return alignments


# Example usage
if __name__ == "__main__":
    import sys

    print("\n" + "="*60)
    print("Semantic Search Engine Test")
    print("="*60)

    # Initialize
    search_engine = SemanticSearchEngine()

    if search_engine.is_available():
        print("\n✅ Semantic search is available!")

        # Test with sample data
        document_id = "test_doc_001"

        sample_chunks = [
            {
                'chunk_id': 'chunk_1',
                'content': 'The PIC32MZ-W1 microcontroller operates at 200 MHz and supports WiFi connectivity.',
                'metadata': {'page': 1, 'section': 'Overview'}
            },
            {
                'chunk_id': 'chunk_2',
                'content': 'The device includes 1MB of flash memory and 256KB of RAM for application code.',
                'metadata': {'page': 2, 'section': 'Memory'}
            },
            {
                'chunk_id': 'chunk_3',
                'content': 'Operating voltage range is 2.3V to 3.6V with typical power consumption of 50mA.',
                'metadata': {'page': 3, 'section': 'Electrical Specs'}
            },
            {
                'chunk_id': 'chunk_4',
                'content': 'The wireless module supports IEEE 802.11 b/g/n protocols with integrated antenna.',
                'metadata': {'page': 4, 'section': 'WiFi Features'}
            },
        ]

        print(f"\nAdding {len(sample_chunks)} chunks...")
        success = search_engine.add_chunks(document_id, sample_chunks)

        if success:
            # Test search
            print("\nTest 1: Search for 'WiFi features'")
            results = search_engine.search_similar(document_id, "WiFi features", n_results=2)

            for i, result in enumerate(results, 1):
                print(f"\nResult {i} (similarity: {result['similarity']:.3f}):")
                print(f"  Chunk: {result['chunk_id']}")
                print(f"  Content: {result['content'][:80]}...")

            # Test find similar
            print("\nTest 2: Find chunks similar to 'memory and storage'")
            results = search_engine.search_similar(document_id, "memory and storage capacity", n_results=2)

            for i, result in enumerate(results, 1):
                print(f"\nResult {i} (similarity: {result['similarity']:.3f}):")
                print(f"  Chunk: {result['chunk_id']}")
                print(f"  Content: {result['content'][:80]}...")

            # Stats
            print("\nCollection stats:")
            stats = search_engine.get_collection_stats(document_id)
            print(f"  Name: {stats.get('name')}")
            print(f"  Count: {stats.get('count')}")

            # Cleanup
            print("\nCleaning up...")
            search_engine.delete_collection(document_id)

        print("\n" + "="*60)
        print("All tests completed!")
        print("="*60)

    else:
        print("\n⚠️ Semantic search not available.")
        print("Install dependencies:")
        print("  pip install chromadb sentence-transformers")
