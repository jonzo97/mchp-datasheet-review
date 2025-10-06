"""
Knowledge Base Manager for RAG (Retrieval-Augmented Generation).

Indexes approved datasheets and retrieves relevant examples to enhance
LLM prompts with company-specific style and standards.

Uses existing infrastructure:
- src/embeddings.py: Sentence transformer embeddings
- src/semantic_search.py: ChromaDB integration
"""

import asyncio
from typing import List, Dict, Optional, Tuple
from pathlib import Path
import logging
import json

from embeddings import EmbeddingGenerator
from semantic_search import SemanticSearchEngine

logger = logging.getLogger(__name__)


class KnowledgeBaseManager:
    """Manages approved datasheet examples for RAG."""

    def __init__(self, config: Dict, db_path: str = "./knowledge_base/chroma_db"):
        self.config = config
        self.db_path = db_path
        self.enabled = config.get('rag', {}).get('enabled', False)

        # Initialize semantic search engine
        self.embedding_generator = EmbeddingGenerator(config)
        self.search_engine = SemanticSearchEngine(config, db_path)

        # Collection for approved examples
        self.approved_collection = None

        # Metadata storage
        self.metadata_path = Path(db_path).parent / "metadata.json"
        self.metadata = self._load_metadata()

    def is_available(self) -> bool:
        """Check if RAG is available."""
        return (
            self.enabled and
            self.embedding_generator.is_available() and
            self.search_engine.is_available()
        )

    def _load_metadata(self) -> Dict:
        """Load knowledge base metadata."""
        if self.metadata_path.exists():
            with open(self.metadata_path, 'r') as f:
                return json.load(f)
        return {
            'indexed_documents': [],
            'total_chunks': 0,
            'categories': {}
        }

    def _save_metadata(self):
        """Save knowledge base metadata."""
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.metadata_path, 'w') as f:
            json.dump(self.metadata, f, indent=2)

    async def initialize_collection(self):
        """Initialize the approved examples collection."""
        if not self.is_available():
            logger.warning("RAG not available - embeddings or ChromaDB missing")
            return False

        try:
            self.approved_collection = self.search_engine.client.get_or_create_collection(
                name="approved_datasheets",
                metadata={"description": "Approved datasheet examples for RAG"}
            )
            logger.info("✅ Knowledge base collection initialized")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize collection: {e}")
            return False

    async def index_approved_document(
        self,
        pdf_path: str,
        extractor,
        quality_rating: float = 1.0,
        tags: List[str] = None
    ) -> bool:
        """
        Index an approved datasheet for reference.

        Args:
            pdf_path: Path to approved PDF
            extractor: PDFExtractor instance
            quality_rating: Quality score (0-1)
            tags: Document tags (e.g., ['PIC32MZ', 'wireless'])

        Returns:
            Success status
        """
        if not self.is_available():
            return False

        if not self.approved_collection:
            await self.initialize_collection()

        try:
            logger.info(f"Indexing approved document: {pdf_path}")

            # Extract chunks from PDF
            from pathlib import Path
            doc_id = Path(pdf_path).stem
            chunks = extractor.extract_document(pdf_path, doc_id)

            logger.info(f"Extracted {len(chunks)} chunks to index")

            # Prepare for indexing
            chunk_ids = []
            chunk_contents = []
            chunk_metadata = []

            for i, chunk in enumerate(chunks):
                # Only index meaningful chunks
                if len(chunk.content) < 50:
                    continue

                # Classify section type
                section_type = self._classify_section_type(chunk.section_hierarchy)

                chunk_id = f"{doc_id}_chunk_{i}"
                chunk_ids.append(chunk_id)
                chunk_contents.append(chunk.content)
                chunk_metadata.append({
                    'document_id': doc_id,
                    'pdf_path': pdf_path,
                    'section': chunk.section_hierarchy,
                    'section_type': section_type,
                    'page': chunk.page_start,
                    'chunk_type': chunk.chunk_type,
                    'quality_rating': quality_rating,
                    'tags': ','.join(tags) if tags else ''
                })

            # Generate embeddings
            embeddings = self.embedding_generator.encode(
                chunk_contents,
                batch_size=32,
                show_progress=True
            )

            # Add to ChromaDB
            self.approved_collection.add(
                ids=chunk_ids,
                embeddings=embeddings.tolist(),
                documents=chunk_contents,
                metadatas=chunk_metadata
            )

            # Update metadata
            self.metadata['indexed_documents'].append({
                'doc_id': doc_id,
                'pdf_path': pdf_path,
                'chunks_indexed': len(chunk_ids),
                'quality_rating': quality_rating,
                'tags': tags or []
            })
            self.metadata['total_chunks'] += len(chunk_ids)
            self._save_metadata()

            logger.info(f"✅ Indexed {len(chunk_ids)} chunks from {doc_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to index document: {e}")
            return False

    async def retrieve_similar_sections(
        self,
        query: str,
        section_type: str = None,
        n_results: int = 3,
        min_quality: float = 0.7
    ) -> List[Dict]:
        """
        Retrieve similar approved sections for RAG.

        Args:
            query: Current section being reviewed
            section_type: Filter by type ('features', 'specifications', etc.)
            n_results: Number of examples to retrieve
            min_quality: Minimum quality rating

        Returns:
            List of similar approved sections with metadata
        """
        if not self.is_available() or not self.approved_collection:
            return []

        try:
            # Build where filter
            where_filter = {}
            if section_type:
                where_filter['section_type'] = section_type

            # Query ChromaDB
            results = self.approved_collection.query(
                query_texts=[query],
                n_results=n_results * 2,  # Get extra in case we filter
                where=where_filter if where_filter else None
            )

            # Format results
            similar_sections = []
            for i in range(len(results['ids'][0])):
                metadata = results['metadatas'][0][i]

                # Filter by quality
                if metadata.get('quality_rating', 0) < min_quality:
                    continue

                similar_sections.append({
                    'content': results['documents'][0][i],
                    'document_id': metadata.get('document_id'),
                    'section': metadata.get('section'),
                    'section_type': metadata.get('section_type'),
                    'page': metadata.get('page'),
                    'quality_rating': metadata.get('quality_rating'),
                    'distance': results['distances'][0][i],
                    'similarity': 1 - results['distances'][0][i]  # Convert distance to similarity
                })

                if len(similar_sections) >= n_results:
                    break

            return similar_sections

        except Exception as e:
            logger.error(f"Failed to retrieve similar sections: {e}")
            return []

    def _classify_section_type(self, section_hierarchy: str) -> str:
        """
        Classify section type based on hierarchy/name.

        Returns:
            One of: 'features', 'specifications', 'functional', 'pinout',
                   'electrical', 'timing', 'register', 'overview', 'other'
        """
        section_lower = section_hierarchy.lower()

        # Features/Overview
        if any(keyword in section_lower for keyword in ['feature', 'overview', 'introduction', 'highlights']):
            return 'features'

        # Specifications
        if any(keyword in section_lower for keyword in ['electrical', 'dc characteristics', 'ac characteristics']):
            return 'electrical'

        if 'timing' in section_lower:
            return 'timing'

        if any(keyword in section_lower for keyword in ['pinout', 'pin description', 'pin configuration']):
            return 'pinout'

        # Functional descriptions
        if any(keyword in section_lower for keyword in ['functional', 'operation', 'description', 'module']):
            return 'functional'

        # Registers
        if 'register' in section_lower:
            return 'register'

        return 'other'

    def get_collection_stats(self) -> Dict:
        """Get statistics about indexed knowledge base."""
        if not self.is_available() or not self.approved_collection:
            return {'enabled': False}

        try:
            count = self.approved_collection.count()
            return {
                'enabled': True,
                'total_chunks': count,
                'indexed_documents': len(self.metadata.get('indexed_documents', [])),
                'documents': self.metadata.get('indexed_documents', [])
            }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {'enabled': False, 'error': str(e)}


async def quick_rag_example():
    """Quick example of RAG usage."""
    import yaml

    # Load config
    with open('config.yaml') as f:
        config = yaml.safe_load(f)

    # Initialize knowledge base
    kb = KnowledgeBaseManager(config)

    if not kb.is_available():
        print("⚠️ RAG not available")
        return

    await kb.initialize_collection()

    # Example: Index an approved datasheet
    # from extraction import PDFExtractor
    # extractor = PDFExtractor(config)
    # await kb.index_approved_document(
    #     "path/to/approved/PIC32MX_datasheet.pdf",
    #     extractor,
    #     quality_rating=0.95,
    #     tags=['PIC32MX', 'reference', 'approved']
    # )

    # Example: Retrieve similar sections
    query = "The SPI peripheral provides high-speed synchronous serial communication"
    similar = await kb.retrieve_similar_sections(
        query,
        section_type='features',
        n_results=3
    )

    print(f"\nFound {len(similar)} similar sections:")
    for i, section in enumerate(similar, 1):
        print(f"\n{i}. From {section['document_id']} (similarity: {section['similarity']:.2f})")
        print(f"   Section: {section['section']}")
        print(f"   Content: {section['content'][:200]}...")

    # Get stats
    stats = kb.get_collection_stats()
    print(f"\nKnowledge base stats: {stats}")


if __name__ == "__main__":
    asyncio.run(quick_rag_example())
