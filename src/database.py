"""
Database module for managing review state and metadata.
Uses SQLite with async support for state management.
"""

import aiosqlite
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum


class ReviewStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    NEEDS_REVIEW = "needs_review"


@dataclass
class Chunk:
    chunk_id: str
    document_id: str
    content: str
    page_start: int
    page_end: int
    section_hierarchy: str
    chunk_type: str  # text, table, figure
    metadata: Dict[str, Any]
    created_at: str


@dataclass
class ReviewRecord:
    review_id: str
    chunk_id: str
    status: str
    original_content: str
    reviewed_content: Optional[str]
    changes: List[Dict[str, Any]]
    confidence_score: float
    reviewer: str  # 'human' or 'llm'
    created_at: str
    updated_at: str


@dataclass
class CrossReference:
    ref_id: str
    chunk_id: str
    reference_text: str
    reference_type: str  # section, figure, table, equation
    target_id: Optional[str]
    is_valid: bool
    page_number: int


class ReviewDatabase:
    """Manages the SQLite database for review state."""

    def __init__(self, db_path: str = "review_state.db"):
        self.db_path = db_path
        self.conn = None

    async def connect(self):
        """Establish database connection."""
        self.conn = await aiosqlite.connect(self.db_path)
        await self._create_tables()

    async def close(self):
        """Close database connection."""
        if self.conn:
            await self.conn.close()

    async def _create_tables(self):
        """Create database tables if they don't exist."""

        # Chunks table
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                content TEXT NOT NULL,
                page_start INTEGER,
                page_end INTEGER,
                section_hierarchy TEXT,
                chunk_type TEXT,
                metadata TEXT,
                created_at TEXT
            )
        """)

        # Reviews table
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                review_id TEXT PRIMARY KEY,
                chunk_id TEXT NOT NULL,
                status TEXT NOT NULL,
                original_content TEXT NOT NULL,
                reviewed_content TEXT,
                changes TEXT,
                confidence_score REAL,
                reviewer TEXT,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (chunk_id) REFERENCES chunks (chunk_id)
            )
        """)

        # Cross-references table
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS cross_references (
                ref_id TEXT PRIMARY KEY,
                chunk_id TEXT NOT NULL,
                reference_text TEXT NOT NULL,
                reference_type TEXT,
                target_id TEXT,
                is_valid BOOLEAN,
                page_number INTEGER,
                FOREIGN KEY (chunk_id) REFERENCES chunks (chunk_id)
            )
        """)

        # Document metadata table
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                document_id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                total_pages INTEGER,
                total_chunks INTEGER,
                created_at TEXT,
                last_updated TEXT,
                has_embeddings BOOLEAN DEFAULT 0,
                embedding_model TEXT
            )
        """)

        # NEW: Embeddings table (for fallback when ChromaDB unavailable)
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS embeddings (
                embedding_id INTEGER PRIMARY KEY AUTOINCREMENT,
                chunk_id TEXT NOT NULL,
                embedding_vector TEXT NOT NULL,
                embedding_model TEXT NOT NULL,
                created_at TEXT,
                FOREIGN KEY (chunk_id) REFERENCES chunks (chunk_id)
            )
        """)

        # NEW: Index for faster embedding lookups
        await self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_embeddings_chunk_id
            ON embeddings (chunk_id)
        """)

        await self.conn.commit()

    # Chunk operations
    async def insert_chunk(self, chunk: Chunk):
        """Insert a new chunk into the database."""
        await self.conn.execute("""
            INSERT INTO chunks (chunk_id, document_id, content, page_start, page_end,
                              section_hierarchy, chunk_type, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            chunk.chunk_id, chunk.document_id, chunk.content, chunk.page_start,
            chunk.page_end, chunk.section_hierarchy, chunk.chunk_type,
            json.dumps(chunk.metadata), chunk.created_at
        ))
        await self.conn.commit()

    async def get_chunk(self, chunk_id: str) -> Optional[Chunk]:
        """Retrieve a chunk by ID."""
        async with self.conn.execute(
            "SELECT * FROM chunks WHERE chunk_id = ?", (chunk_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return Chunk(
                    chunk_id=row[0],
                    document_id=row[1],
                    content=row[2],
                    page_start=row[3],
                    page_end=row[4],
                    section_hierarchy=row[5],
                    chunk_type=row[6],
                    metadata=json.loads(row[7]),
                    created_at=row[8]
                )
        return None

    async def get_all_chunks(self, document_id: str) -> List[Chunk]:
        """Get all chunks for a document."""
        chunks = []
        async with self.conn.execute(
            "SELECT * FROM chunks WHERE document_id = ? ORDER BY page_start, chunk_id",
            (document_id,)
        ) as cursor:
            async for row in cursor:
                chunks.append(Chunk(
                    chunk_id=row[0],
                    document_id=row[1],
                    content=row[2],
                    page_start=row[3],
                    page_end=row[4],
                    section_hierarchy=row[5],
                    chunk_type=row[6],
                    metadata=json.loads(row[7]),
                    created_at=row[8]
                ))
        return chunks

    # Review operations
    async def insert_review(self, review: ReviewRecord):
        """Insert or update a review record."""
        await self.conn.execute("""
            INSERT OR REPLACE INTO reviews (review_id, chunk_id, status, original_content,
                                           reviewed_content, changes, confidence_score,
                                           reviewer, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            review.review_id, review.chunk_id, review.status, review.original_content,
            review.reviewed_content, json.dumps(review.changes), review.confidence_score,
            review.reviewer, review.created_at, review.updated_at
        ))
        await self.conn.commit()

    async def get_review(self, chunk_id: str) -> Optional[ReviewRecord]:
        """Get review for a chunk."""
        async with self.conn.execute(
            "SELECT * FROM reviews WHERE chunk_id = ? ORDER BY updated_at DESC LIMIT 1",
            (chunk_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return ReviewRecord(
                    review_id=row[0],
                    chunk_id=row[1],
                    status=row[2],
                    original_content=row[3],
                    reviewed_content=row[4],
                    changes=json.loads(row[5]),
                    confidence_score=row[6],
                    reviewer=row[7],
                    created_at=row[8],
                    updated_at=row[9]
                )
        return None

    async def get_pending_reviews(self, document_id: str) -> List[str]:
        """Get chunk IDs with pending reviews."""
        chunk_ids = []
        async with self.conn.execute("""
            SELECT c.chunk_id FROM chunks c
            LEFT JOIN reviews r ON c.chunk_id = r.chunk_id
            WHERE c.document_id = ? AND (r.status IS NULL OR r.status = 'pending')
            ORDER BY c.page_start, c.chunk_id
        """, (document_id,)) as cursor:
            async for row in cursor:
                chunk_ids.append(row[0])
        return chunk_ids

    # Cross-reference operations
    async def insert_cross_reference(self, crossref: CrossReference):
        """Insert a cross-reference."""
        await self.conn.execute("""
            INSERT INTO cross_references (ref_id, chunk_id, reference_text, reference_type,
                                         target_id, is_valid, page_number)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            crossref.ref_id, crossref.chunk_id, crossref.reference_text,
            crossref.reference_type, crossref.target_id, crossref.is_valid,
            crossref.page_number
        ))
        await self.conn.commit()

    async def get_cross_references(self, document_id: str) -> List[CrossReference]:
        """Get all cross-references for a document."""
        crossrefs = []
        async with self.conn.execute("""
            SELECT cr.* FROM cross_references cr
            JOIN chunks c ON cr.chunk_id = c.chunk_id
            WHERE c.document_id = ?
        """, (document_id,)) as cursor:
            async for row in cursor:
                crossrefs.append(CrossReference(
                    ref_id=row[0],
                    chunk_id=row[1],
                    reference_text=row[2],
                    reference_type=row[3],
                    target_id=row[4],
                    is_valid=bool(row[5]),
                    page_number=row[6]
                ))
        return crossrefs

    async def update_crossref_validity(self, ref_id: str, is_valid: bool, target_id: Optional[str] = None):
        """Update cross-reference validation status."""
        if target_id:
            await self.conn.execute(
                "UPDATE cross_references SET is_valid = ?, target_id = ? WHERE ref_id = ?",
                (is_valid, target_id, ref_id)
            )
        else:
            await self.conn.execute(
                "UPDATE cross_references SET is_valid = ? WHERE ref_id = ?",
                (is_valid, ref_id)
            )
        await self.conn.commit()

    # Document operations
    async def insert_document(self, document_id: str, filename: str, total_pages: int):
        """Insert document metadata."""
        now = datetime.now().isoformat()
        await self.conn.execute("""
            INSERT INTO documents (document_id, filename, total_pages, total_chunks,
                                  created_at, last_updated)
            VALUES (?, ?, ?, 0, ?, ?)
        """, (document_id, filename, total_pages, now, now))
        await self.conn.commit()

    async def update_document_chunks(self, document_id: str, total_chunks: int):
        """Update total chunk count for a document."""
        await self.conn.execute("""
            UPDATE documents SET total_chunks = ?, last_updated = ?
            WHERE document_id = ?
        """, (total_chunks, datetime.now().isoformat(), document_id))
        await self.conn.commit()

    async def get_progress(self, document_id: str) -> Dict[str, int]:
        """Get review progress statistics."""
        async with self.conn.execute("""
            SELECT
                COUNT(DISTINCT c.chunk_id) as total,
                COUNT(DISTINCT CASE WHEN r.status = 'completed' THEN c.chunk_id END) as completed,
                COUNT(DISTINCT CASE WHEN r.status = 'in_progress' THEN c.chunk_id END) as in_progress,
                COUNT(DISTINCT CASE WHEN r.status = 'needs_review' THEN c.chunk_id END) as needs_review
            FROM chunks c
            LEFT JOIN reviews r ON c.chunk_id = r.chunk_id
            WHERE c.document_id = ?
        """, (document_id,)) as cursor:
            row = await cursor.fetchone()
            return {
                "total": row[0],
                "completed": row[1],
                "in_progress": row[2],
                "needs_review": row[3],
                "pending": row[0] - (row[1] + row[2] + row[3])
            }

    # NEW: Embedding operations
    async def insert_embedding(self, chunk_id: str, embedding_vector: list, model_name: str):
        """
        Store an embedding vector for a chunk.

        Args:
            chunk_id: Chunk identifier
            embedding_vector: Embedding as list of floats
            model_name: Name of the embedding model used
        """
        import json
        now = datetime.now().isoformat()

        await self.conn.execute("""
            INSERT INTO embeddings (chunk_id, embedding_vector, embedding_model, created_at)
            VALUES (?, ?, ?, ?)
        """, (chunk_id, json.dumps(embedding_vector), model_name, now))
        await self.conn.commit()

    async def get_embedding(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve embedding for a chunk.

        Returns:
            Dict with 'vector' and 'model' or None if not found
        """
        import json
        async with self.conn.execute("""
            SELECT embedding_vector, embedding_model
            FROM embeddings
            WHERE chunk_id = ?
            ORDER BY created_at DESC
            LIMIT 1
        """, (chunk_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    'vector': json.loads(row[0]),
                    'model': row[1]
                }
        return None

    async def has_embeddings(self, document_id: str) -> bool:
        """Check if a document has embeddings."""
        async with self.conn.execute("""
            SELECT COUNT(DISTINCT e.chunk_id)
            FROM embeddings e
            JOIN chunks c ON e.chunk_id = c.chunk_id
            WHERE c.document_id = ?
        """, (document_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] > 0 if row else False

    async def update_document_embeddings_status(self, document_id: str,
                                               has_embeddings: bool,
                                               model_name: str = None):
        """Update document metadata to track embedding status."""
        await self.conn.execute("""
            UPDATE documents
            SET has_embeddings = ?, embedding_model = ?, last_updated = ?
            WHERE document_id = ?
        """, (has_embeddings, model_name, datetime.now().isoformat(), document_id))
        await self.conn.commit()

    async def get_chunks_without_embeddings(self, document_id: str) -> List[Chunk]:
        """
        Get chunks that don't have embeddings yet.

        Returns:
            List of Chunk objects without embeddings
        """
        async with self.conn.execute("""
            SELECT c.chunk_id, c.document_id, c.content, c.page_start, c.page_end,
                   c.section_hierarchy, c.chunk_type, c.metadata, c.created_at
            FROM chunks c
            LEFT JOIN embeddings e ON c.chunk_id = e.chunk_id
            WHERE c.document_id = ? AND e.embedding_id IS NULL
        """, (document_id,)) as cursor:
            rows = await cursor.fetchall()
            chunks = []
            for row in rows:
                chunks.append(Chunk(
                    chunk_id=row[0],
                    document_id=row[1],
                    content=row[2],
                    page_start=row[3],
                    page_end=row[4],
                    section_hierarchy=row[5],
                    chunk_type=row[6],
                    metadata=json.loads(row[7]) if row[7] else {},
                    created_at=row[8]
                ))
            return chunks
