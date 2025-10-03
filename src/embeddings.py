"""
Embedding generation module for semantic search.
Abstracts embedding models and provides easy model swapping.
"""

from typing import List, Union, Optional
import numpy as np


class EmbeddingGenerator:
    """
    Abstract embedding generation with support for multiple models.
    Gracefully handles missing dependencies (sentence-transformers, ChromaDB).
    """

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.model_name = self.config.get('semantic', {}).get('embedding_model', 'all-MiniLM-L6-v2')
        self.model = None
        self.available = False

        # Try to load model
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(self.model_name)
            self.available = True
            print(f"✅ Embedding model loaded: {self.model_name}")
        except ImportError:
            print("⚠️ sentence-transformers not installed. Semantic features disabled.")
            print("   Install with: pip install sentence-transformers")
        except Exception as e:
            print(f"⚠️ Failed to load embedding model: {e}")
            print("   Semantic features disabled.")

    def is_available(self) -> bool:
        """Check if embedding generation is available."""
        return self.available

    def encode(self, texts: Union[str, List[str]],
               batch_size: int = 32,
               show_progress: bool = False) -> Optional[np.ndarray]:
        """
        Generate embeddings for text(s).

        Args:
            texts: Single text string or list of texts
            batch_size: Batch size for processing
            show_progress: Show progress bar

        Returns:
            numpy array of embeddings, or None if unavailable
        """
        if not self.available:
            return None

        try:
            embeddings = self.model.encode(
                texts,
                batch_size=batch_size,
                show_progress_bar=show_progress,
                convert_to_numpy=True
            )
            return embeddings
        except Exception as e:
            print(f"❌ Error generating embeddings: {e}")
            return None

    def encode_single(self, text: str) -> Optional[np.ndarray]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            numpy array of single embedding, or None if unavailable
        """
        if not self.available:
            return None

        try:
            embedding = self.model.encode(text, convert_to_numpy=True)
            return embedding
        except Exception as e:
            print(f"❌ Error generating embedding: {e}")
            return None

    def similarity(self, text1: str, text2: str) -> Optional[float]:
        """
        Calculate cosine similarity between two texts.

        Args:
            text1: First text
            text2: Second text

        Returns:
            Similarity score (0-1), or None if unavailable
        """
        if not self.available:
            return None

        try:
            # Generate embeddings
            emb1 = self.model.encode(text1, convert_to_numpy=True)
            emb2 = self.model.encode(text2, convert_to_numpy=True)

            # Calculate cosine similarity
            similarity = np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))
            return float(similarity)
        except Exception as e:
            print(f"❌ Error calculating similarity: {e}")
            return None

    def get_model_info(self) -> dict:
        """Get information about the loaded model."""
        if not self.available:
            return {
                'available': False,
                'model_name': self.model_name,
                'error': 'Model not loaded'
            }

        try:
            return {
                'available': True,
                'model_name': self.model_name,
                'max_seq_length': self.model.max_seq_length,
                'embedding_dimension': self.model.get_sentence_embedding_dimension(),
            }
        except Exception as e:
            return {
                'available': True,
                'model_name': self.model_name,
                'error': str(e)
            }


class EmbeddingCache:
    """Simple in-memory cache for embeddings to avoid recomputation."""

    def __init__(self, max_size: int = 1000):
        self.cache = {}
        self.max_size = max_size

    def get(self, text_hash: str) -> Optional[np.ndarray]:
        """Get embedding from cache."""
        return self.cache.get(text_hash)

    def put(self, text_hash: str, embedding: np.ndarray):
        """Store embedding in cache."""
        # Simple LRU: remove oldest if full
        if len(self.cache) >= self.max_size:
            # Remove first item (oldest in dict order)
            first_key = next(iter(self.cache))
            del self.cache[first_key]

        self.cache[text_hash] = embedding

    def clear(self):
        """Clear the cache."""
        self.cache.clear()

    def size(self) -> int:
        """Get current cache size."""
        return len(self.cache)


# Recommended embedding models for different use cases
RECOMMENDED_MODELS = {
    'fast': 'all-MiniLM-L6-v2',           # Fast, small, good for most uses (384 dim)
    'balanced': 'all-mpnet-base-v2',       # Better quality, still fast (768 dim)
    'quality': 'all-distilroberta-v1',     # High quality (768 dim)
    'multilingual': 'paraphrase-multilingual-MiniLM-L12-v2',  # Multiple languages
    'technical': 'allenai/scibert_scivocab_uncased',  # Scientific/technical text
}


def get_recommended_model(use_case: str = 'fast') -> str:
    """
    Get recommended model for a use case.

    Args:
        use_case: 'fast', 'balanced', 'quality', 'multilingual', or 'technical'

    Returns:
        Model name string
    """
    return RECOMMENDED_MODELS.get(use_case, RECOMMENDED_MODELS['fast'])


# Example usage
if __name__ == "__main__":
    # Initialize embedding generator
    generator = EmbeddingGenerator()

    if generator.is_available():
        print("\n" + "="*60)
        print("Embedding Generator Test")
        print("="*60)

        # Model info
        info = generator.get_model_info()
        print(f"\nModel: {info['model_name']}")
        print(f"Embedding dimension: {info.get('embedding_dimension', 'N/A')}")
        print(f"Max sequence length: {info.get('max_seq_length', 'N/A')}")

        # Test single embedding
        print("\nTest 1: Single text embedding")
        text = "The PIC32MZ-W1 microcontroller operates at 200 MHz."
        embedding = generator.encode_single(text)
        if embedding is not None:
            print(f"✅ Generated embedding of shape: {embedding.shape}")

        # Test batch embeddings
        print("\nTest 2: Batch text embeddings")
        texts = [
            "The device supports WiFi connectivity.",
            "The microcontroller has 1MB of flash memory.",
            "Operating voltage range is 2.3V to 3.6V."
        ]
        embeddings = generator.encode(texts)
        if embeddings is not None:
            print(f"✅ Generated {len(embeddings)} embeddings of shape: {embeddings.shape}")

        # Test similarity
        print("\nTest 3: Similarity calculation")
        text1 = "The chip operates at high frequency."
        text2 = "The device runs at elevated clock speeds."
        similarity = generator.similarity(text1, text2)
        if similarity is not None:
            print(f"✅ Similarity between texts: {similarity:.3f}")

        print("\n" + "="*60)
        print("All tests completed!")
        print("="*60)
    else:
        print("\n⚠️ Embedding generator not available.")
        print("Install dependencies: pip install sentence-transformers")
