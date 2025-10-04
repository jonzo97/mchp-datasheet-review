"""
PDF extraction and intelligent chunking module.
Extracts text, tables, and figures from PDF with structure preservation.
"""

import fitz  # PyMuPDF
import pdfplumber
import re
import hashlib
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass
from pathlib import Path
import json


@dataclass
class ExtractedChunk:
    """Represents a chunk of extracted content."""
    chunk_id: str
    content: str
    page_start: int
    page_end: int
    chunk_type: str  # 'text', 'table', 'figure'
    section_hierarchy: str
    metadata: Dict[str, Any]


class PDFExtractor:
    """Handles PDF extraction and intelligent chunking."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.chunk_size = config.get('document', {}).get('chunk_size', 1500)
        self.overlap = config.get('document', {}).get('overlap', 200)
        self.preserve_sections = config.get('document', {}).get('preserve_sections', True)
        self.extract_images = config.get('document', {}).get('extract_images', True)

        # NEW: Chunking strategy configuration
        self.chunking_strategy = config.get('document', {}).get('chunking_strategy', 'fixed')  # 'fixed' or 'semantic'
        self.min_chunk_size = config.get('document', {}).get('min_chunk_size', 500)  # Min chars for semantic chunks
        self.max_chunk_size = config.get('document', {}).get('max_chunk_size', 2500)  # Max chars for semantic chunks

    def extract_document(self, pdf_path: str, document_id: str) -> List[ExtractedChunk]:
        """
        Extract and chunk a PDF document.

        Args:
            pdf_path: Path to the PDF file
            document_id: Unique identifier for the document

        Returns:
            List of extracted chunks
        """
        chunks = []

        # Use PyMuPDF for text and structure
        doc = fitz.open(pdf_path)

        # First pass: extract structure and identify section breaks
        document_structure = self._extract_structure(doc)

        # Second pass: extract content with context
        for page_num in range(len(doc)):
            page = doc[page_num]

            # Extract text blocks
            text_chunks = self._extract_text_from_page(page, page_num, document_structure)
            chunks.extend(text_chunks)

            # Extract images/figures
            if self.extract_images:
                figure_chunks = self._extract_figures_from_page(page, page_num, document_id)
                chunks.extend(figure_chunks)

        doc.close()

        # Third pass: extract tables using pdfplumber
        table_chunks = self._extract_tables(pdf_path, document_id)
        chunks.extend(table_chunks)

        # Fourth pass: perform intelligent chunking on text sections
        final_chunks = self._perform_intelligent_chunking(chunks, document_id)

        return final_chunks

    def _extract_structure(self, doc: fitz.Document) -> Dict[int, str]:
        """
        Extract document structure (sections, headings).

        Returns:
            Dictionary mapping page numbers to section hierarchy
        """
        structure = {}
        current_section = ""
        # IMPROVED: More flexible section patterns to reduce false negatives
        section_patterns = [
            re.compile(r'^(\d+(?:\.\d+)*)\s+[A-Z]'),           # "1.2.3 TITLE"
            re.compile(r'^(\d+(?:\.\d+)*)\s+[a-z]'),           # "1.2.3 introduction"
            re.compile(r'(?:^|\n)\s*(\d+(?:\.\d+)*)\s+\w+'),   # Any word after number
            re.compile(r'^SECTION\s+(\d+(?:\.\d+)*)'),         # "SECTION 3.1"
            re.compile(r'^Section\s+(\d+(?:\.\d+)*)'),         # "Section 3.1"
        ]

        for page_num in range(len(doc)):
            page = doc[page_num]
            blocks = page.get_text("dict")["blocks"]

            for block in blocks:
                if block.get("type") == 0:  # Text block
                    for line in block.get("lines", []):
                        text = "".join([span["text"] for span in line.get("spans", [])])

                        # Detect section headers by font size and pattern
                        if line.get("spans"):
                            font_size = line["spans"][0].get("size", 0)

                            # Headers typically have larger font
                            if font_size > 12 and any(p.match(text.strip()) for p in section_patterns):
                                current_section = text.strip()

            structure[page_num] = current_section

        return structure

    def _extract_text_from_page(self, page: fitz.Page, page_num: int,
                                structure: Dict[int, str]) -> List[ExtractedChunk]:
        """Extract text content from a page."""
        chunks = []
        text = page.get_text()

        if not text.strip():
            return chunks

        # Create chunk metadata
        metadata = {
            "page": page_num + 1,
            "extraction_method": "pymupdf",
            "has_images": len(page.get_images()) > 0
        }

        section_hierarchy = structure.get(page_num, "Unknown Section")

        chunk = ExtractedChunk(
            chunk_id=self._generate_chunk_id(text, page_num),
            content=text,
            page_start=page_num + 1,
            page_end=page_num + 1,
            chunk_type="text",
            section_hierarchy=section_hierarchy,
            metadata=metadata
        )

        chunks.append(chunk)
        return chunks

    def _extract_figures_from_page(self, page: fitz.Page, page_num: int,
                                   document_id: str) -> List[ExtractedChunk]:
        """Extract figures/images from a page."""
        chunks = []
        images = page.get_images()

        for img_index, img in enumerate(images):
            xref = img[0]
            base_image = page.parent.extract_image(xref)

            # Look for figure caption nearby
            caption = self._find_figure_caption(page, img_index)

            metadata = {
                "page": page_num + 1,
                "image_index": img_index,
                "image_format": base_image["ext"],
                "image_size": len(base_image["image"]),
                "caption": caption,
                "xref": xref
            }

            content = f"[Figure {img_index + 1}]\n"
            if caption:
                content += f"Caption: {caption}\n"

            chunk = ExtractedChunk(
                chunk_id=self._generate_chunk_id(content, page_num, f"fig_{img_index}"),
                content=content,
                page_start=page_num + 1,
                page_end=page_num + 1,
                chunk_type="figure",
                section_hierarchy=f"Figure {img_index + 1}",
                metadata=metadata
            )

            chunks.append(chunk)

        return chunks

    def _find_figure_caption(self, page: fitz.Page, img_index: int) -> Optional[str]:
        """Attempt to find a caption for a figure."""
        text = page.get_text()

        # Look for common caption patterns
        patterns = [
            rf"Figure\s+{img_index + 1}[:\.]?\s+(.+?)(?:\n|$)",
            rf"Fig\.\s+{img_index + 1}[:\.]?\s+(.+?)(?:\n|$)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return None

    def _extract_tables(self, pdf_path: str, document_id: str) -> List[ExtractedChunk]:
        """Extract tables using pdfplumber with multi-strategy approach."""
        chunks = []

        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                # IMPROVED: Multi-strategy table extraction
                tables = self._extract_tables_multi_strategy(page)

                for table_index, table in enumerate(tables):
                    # Skip empty tables (after all strategies)
                    if not table or len(table) < 2:
                        continue

                    # Check if table has actual content
                    if self._is_table_empty(table):
                        continue

                    # Convert table to markdown format
                    table_md = self._table_to_markdown(table)

                    # IMPROVED: Better caption finding
                    caption = self._find_table_caption_improved(page, table_index)

                    content = f"[Table {table_index + 1}]\n"
                    if caption:
                        content += f"Caption: {caption}\n\n"
                    content += table_md

                    metadata = {
                        "page": page_num + 1,
                        "table_index": table_index,
                        "rows": len(table),
                        "columns": len(table[0]) if table else 0,
                        "caption": caption,
                        "extraction_quality": "good" if not self._is_table_sparse(table) else "sparse"
                    }

                    chunk = ExtractedChunk(
                        chunk_id=self._generate_chunk_id(content, page_num, f"tbl_{table_index}"),
                        content=content,
                        page_start=page_num + 1,
                        page_end=page_num + 1,
                        chunk_type="table",
                        section_hierarchy=f"Table {table_index + 1}",
                        metadata=metadata
                    )

                    chunks.append(chunk)

        return chunks

    def _extract_tables_multi_strategy(self, page) -> List:
        """Try multiple extraction strategies to get the best table data."""
        # Strategy 1: Standard extraction
        tables = page.extract_tables()

        # If we got good tables, return them
        if tables and any(not self._is_table_empty(t) for t in tables):
            return tables

        # Strategy 2: Line-based extraction (for tables with visible borders)
        tables = page.extract_tables(table_settings={
            "vertical_strategy": "lines",
            "horizontal_strategy": "lines",
            "snap_tolerance": 3,
        })

        if tables and any(not self._is_table_empty(t) for t in tables):
            return tables

        # Strategy 3: Text-based extraction (for borderless tables)
        tables = page.extract_tables(table_settings={
            "vertical_strategy": "text",
            "horizontal_strategy": "text",
        })

        return tables or []

    def _is_table_empty(self, table: List[List]) -> bool:
        """Check if a table has actual content."""
        if not table or len(table) < 2:
            return True

        # Count non-empty cells
        non_empty_cells = sum(
            1 for row in table for cell in row
            if cell and str(cell).strip() and str(cell).strip() not in ['', '---']
        )

        # Need at least 3 non-empty cells for a valid table
        return non_empty_cells < 3

    def _is_table_sparse(self, table: List[List]) -> bool:
        """Check if table has many empty cells."""
        if not table:
            return True

        total_cells = sum(len(row) for row in table)
        if total_cells == 0:
            return True

        empty_cells = sum(
            1 for row in table for cell in row
            if not cell or not str(cell).strip()
        )

        return (empty_cells / total_cells) > 0.5  # More than 50% empty

    def _find_table_caption_improved(self, page, table_index: int) -> Optional[str]:
        """Improved caption detection with better patterns."""
        text = page.extract_text()

        if not text:
            return None

        # Try multiple caption patterns
        patterns = [
            rf'Table\s+{table_index + 1}[:\.]?\s+(.+?)(?:\n|$)',
            rf'TABLE\s+{table_index + 1}[:\.]?\s+(.+?)(?:\n|$)',
            rf'Table\s+(\d+-\d+)[:\.]?\s+(.+?)(?:\n|$)',  # Hyphenated table numbers
            rf'TABLE\s+(\d+-\d+)[:\.]?\s+(.+?)(?:\n|$)',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # Get the caption text (last group)
                caption = match.group(match.lastindex).strip()
                if len(caption) > 3:  # Avoid single character matches
                    return caption[:200]  # Limit caption length

        return None

    def _table_to_markdown(self, table: List[List[str]]) -> str:
        """Convert table data to markdown format."""
        if not table:
            return ""

        md_lines = []

        # Header row
        header = [cell or "" for cell in table[0]]
        md_lines.append("| " + " | ".join(header) + " |")

        # Separator
        md_lines.append("| " + " | ".join(["---"] * len(header)) + " |")

        # Data rows
        for row in table[1:]:
            cells = [cell or "" for cell in row]
            # Pad if necessary
            while len(cells) < len(header):
                cells.append("")
            md_lines.append("| " + " | ".join(cells[:len(header)]) + " |")

        return "\n".join(md_lines)

    def _find_table_caption(self, page, table_index: int) -> Optional[str]:
        """Attempt to find a caption for a table."""
        text = page.extract_text()

        if not text:
            return None

        # Look for common caption patterns
        patterns = [
            rf"Table\s+{table_index + 1}[:\.]?\s+(.+?)(?:\n|$)",
            rf"TABLE\s+{table_index + 1}[:\.]?\s+(.+?)(?:\n|$)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return None

    def _perform_intelligent_chunking(self, chunks: List[ExtractedChunk],
                                     document_id: str) -> List[ExtractedChunk]:
        """
        Perform intelligent chunking on text sections.
        Tables and figures are kept as-is.
        """
        final_chunks = []

        for chunk in chunks:
            # Keep tables and figures as single chunks
            if chunk.chunk_type in ["table", "figure"]:
                final_chunks.append(chunk)
                continue

            # Split text chunks if they're too large
            if len(chunk.content) > self.chunk_size:
                sub_chunks = self._split_text_chunk(chunk)
                final_chunks.extend(sub_chunks)
            else:
                final_chunks.append(chunk)

        return final_chunks

    def _split_text_chunk(self, chunk: ExtractedChunk) -> List[ExtractedChunk]:
        """
        Split a large text chunk into smaller pieces with overlap.
        Uses either fixed-size or semantic chunking based on configuration.
        """
        if self.chunking_strategy == 'semantic':
            return self._split_text_chunk_semantic(chunk)
        else:
            return self._split_text_chunk_fixed(chunk)

    def _split_text_chunk_fixed(self, chunk: ExtractedChunk) -> List[ExtractedChunk]:
        """Split a large text chunk using fixed-size strategy with overlap."""
        sub_chunks = []
        text = chunk.content

        # Split by paragraphs first
        paragraphs = text.split('\n\n')

        current_text = ""
        chunk_index = 0

        for para in paragraphs:
            # If adding this paragraph would exceed chunk size
            if len(current_text) + len(para) > self.chunk_size and current_text:
                # Save current chunk
                sub_chunk = ExtractedChunk(
                    chunk_id=f"{chunk.chunk_id}_sub_{chunk_index}",
                    content=current_text.strip(),
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    chunk_type=chunk.chunk_type,
                    section_hierarchy=chunk.section_hierarchy,
                    metadata={**chunk.metadata, "sub_chunk": chunk_index, "chunking_strategy": "fixed"}
                )
                sub_chunks.append(sub_chunk)
                chunk_index += 1

                # Start new chunk with overlap
                overlap_text = current_text[-self.overlap:] if len(current_text) > self.overlap else current_text
                current_text = overlap_text + "\n\n" + para
            else:
                current_text += "\n\n" + para if current_text else para

        # Add final chunk
        if current_text.strip():
            sub_chunk = ExtractedChunk(
                chunk_id=f"{chunk.chunk_id}_sub_{chunk_index}",
                content=current_text.strip(),
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                chunk_type=chunk.chunk_type,
                section_hierarchy=chunk.section_hierarchy,
                metadata={**chunk.metadata, "sub_chunk": chunk_index, "chunking_strategy": "fixed"}
            )
            sub_chunks.append(sub_chunk)

        return sub_chunks if sub_chunks else [chunk]

    def _split_text_chunk_semantic(self, chunk: ExtractedChunk) -> List[ExtractedChunk]:
        """
        Split a large text chunk using semantic-aware strategy.
        Preserves section boundaries, paragraph structure, and topic coherence.
        """
        sub_chunks = []
        text = chunk.content

        # Identify semantic boundaries (section headers, major paragraph breaks)
        semantic_segments = self._identify_semantic_segments(text)

        current_text = ""
        chunk_index = 0

        for segment in semantic_segments:
            segment_text = segment['text']
            is_section_boundary = segment['is_boundary']

            # Force new chunk at section boundaries (if current chunk has content)
            if is_section_boundary and current_text and len(current_text) >= self.min_chunk_size:
                # Save current chunk
                sub_chunk = ExtractedChunk(
                    chunk_id=f"{chunk.chunk_id}_sub_{chunk_index}",
                    content=current_text.strip(),
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    chunk_type=chunk.chunk_type,
                    section_hierarchy=chunk.section_hierarchy,
                    metadata={**chunk.metadata, "sub_chunk": chunk_index, "chunking_strategy": "semantic"}
                )
                sub_chunks.append(sub_chunk)
                chunk_index += 1

                # Start new chunk with semantic context (smaller overlap)
                overlap_text = self._get_semantic_overlap(current_text)
                current_text = overlap_text + "\n\n" + segment_text if overlap_text else segment_text

            # If adding this segment would exceed max size
            elif len(current_text) + len(segment_text) > self.max_chunk_size and current_text:
                # Save current chunk
                sub_chunk = ExtractedChunk(
                    chunk_id=f"{chunk.chunk_id}_sub_{chunk_index}",
                    content=current_text.strip(),
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    chunk_type=chunk.chunk_type,
                    section_hierarchy=chunk.section_hierarchy,
                    metadata={**chunk.metadata, "sub_chunk": chunk_index, "chunking_strategy": "semantic"}
                )
                sub_chunks.append(sub_chunk)
                chunk_index += 1

                # Start new chunk with overlap
                overlap_text = self._get_semantic_overlap(current_text)
                current_text = overlap_text + "\n\n" + segment_text if overlap_text else segment_text
            else:
                current_text += "\n\n" + segment_text if current_text else segment_text

        # Add final chunk (if it meets minimum size or is the only chunk)
        if current_text.strip() and (len(current_text) >= self.min_chunk_size or chunk_index == 0):
            sub_chunk = ExtractedChunk(
                chunk_id=f"{chunk.chunk_id}_sub_{chunk_index}",
                content=current_text.strip(),
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                chunk_type=chunk.chunk_type,
                section_hierarchy=chunk.section_hierarchy,
                metadata={**chunk.metadata, "sub_chunk": chunk_index, "chunking_strategy": "semantic"}
            )
            sub_chunks.append(sub_chunk)
        elif current_text.strip() and sub_chunks:
            # If final segment is too small, append to last chunk
            sub_chunks[-1].content += "\n\n" + current_text.strip()

        return sub_chunks if sub_chunks else [chunk]

    def _identify_semantic_segments(self, text: str) -> List[Dict]:
        """
        Identify semantic segments in text (sections, paragraphs, topic boundaries).

        Returns:
            List of dicts with 'text' and 'is_boundary' (True if section header)
        """
        segments = []

        # Split by double newline (paragraph boundaries)
        paragraphs = text.split('\n\n')

        # IMPROVED: More flexible patterns for section headers
        section_patterns = [
            re.compile(r'^(\d+(?:\.\d+)*)\s+[A-Z]'),           # "3.1 SECTION"
            re.compile(r'^(\d+(?:\.\d+)*)\s+[a-z]'),           # "3.1 introduction"
            re.compile(r'(?:^|\n)\s*(\d+(?:\.\d+)*)\s+\w+'),   # Number + any word
            re.compile(r'^SECTION\s+(\d+(?:\.\d+)*)'),         # "SECTION 3.1"
            re.compile(r'^Section\s+(\d+(?:\.\d+)*)'),         # "Section 3.1"
            re.compile(r'^[A-Z][A-Z\s]{10,}$'),                # ALL CAPS headings
            re.compile(r'^[A-Z][a-z\s]+:$'),                   # Title case with colon
        ]

        for para in paragraphs:
            para_stripped = para.strip()
            if not para_stripped:
                continue

            # Check if this paragraph is a section header
            is_boundary = any(pattern.match(para_stripped) for pattern in section_patterns)

            # Also detect headers by length (very short paragraphs at line start)
            if not is_boundary and len(para_stripped) < 60 and '\n' not in para_stripped:
                # Might be a header if it starts with capital and doesn't end with period
                if para_stripped[0].isupper() and not para_stripped.endswith('.'):
                    is_boundary = True

            segments.append({
                'text': para_stripped,
                'is_boundary': is_boundary
            })

        return segments

    def _get_semantic_overlap(self, text: str) -> str:
        """
        Get semantically meaningful overlap (last complete sentence or two).
        More intelligent than fixed character overlap.
        """
        if len(text) < 100:
            return ""

        # Try to get last 1-2 sentences
        sentences = re.split(r'[.!?]\s+', text)

        if len(sentences) >= 2:
            # Return last 2 sentences (or less if they're too long)
            overlap_candidates = sentences[-2:]
            overlap_text = '. '.join(overlap_candidates)

            # Limit overlap to reasonable size
            max_overlap = min(self.overlap * 2, 400)
            if len(overlap_text) > max_overlap:
                return overlap_text[-max_overlap:]
            return overlap_text

        # Fallback: last N characters
        return text[-self.overlap:] if len(text) > self.overlap else text

    def _generate_chunk_id(self, content: str, page_num: int, suffix: str = "") -> str:
        """Generate a unique chunk ID."""
        hash_input = f"{content[:100]}{page_num}{suffix}".encode()
        hash_val = hashlib.md5(hash_input).hexdigest()[:12]
        return f"chunk_{page_num}_{hash_val}{('_' + suffix) if suffix else ''}"

    def get_document_metadata(self, pdf_path: str) -> Dict[str, Any]:
        """Extract document metadata."""
        doc = fitz.open(pdf_path)

        metadata = {
            "total_pages": len(doc),
            "title": doc.metadata.get("title", ""),
            "author": doc.metadata.get("author", ""),
            "subject": doc.metadata.get("subject", ""),
            "creator": doc.metadata.get("creator", ""),
            "filename": Path(pdf_path).name
        }

        doc.close()
        return metadata
