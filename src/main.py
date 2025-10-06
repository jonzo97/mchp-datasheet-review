"""
Main orchestration module for datasheet review system.
Coordinates extraction, review, and output generation.
"""

import asyncio
import yaml
import time
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from tqdm import tqdm
import logging

from database import ReviewDatabase, Chunk, ReviewRecord, CrossReference
from extraction import PDFExtractor
from review_language import LanguageReviewer
from review_crossref import CrossReferenceValidator
from review_tables import TableFigureReviewer
from completeness_validator import CompletenessValidator
from terminology_analyzer import TerminologyAnalyzer
from llm_client import LLMClient
from output import MarkdownGenerator
from changes_diff import ChangesDiffGenerator


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DatasheetReviewSystem:
    """Main system for datasheet review."""

    def __init__(self, config_path: str = "config.yaml"):
        """Initialize the review system."""
        self.config = self._load_config(config_path)

        # Initialize components
        self.db = ReviewDatabase(self.config.get('database', {}).get('path', 'review_state.db'))
        self.extractor = PDFExtractor(self.config)
        self.language_reviewer = LanguageReviewer(self.config)
        self.crossref_validator = CrossReferenceValidator(self.config)
        self.table_reviewer = TableFigureReviewer(self.config)
        self.completeness_validator = None  # Initialized with LLM if enabled
        self.terminology_analyzer = TerminologyAnalyzer(self.config)
        self.output_generator = MarkdownGenerator(self.config)
        self.diff_generator = ChangesDiffGenerator(self.config)
        self.llm_client = None  # Initialized when needed

        # Statistics tracking
        self.stats = {
            'document': {},
            'processing': {'total': 0, 'completed': 0, 'failed': 0, 'avg_confidence': 0.0},
            'language_review': {'total_changes': 0, 'spelling': 0, 'grammar': 0, 'style': 0},
            'crossref': {'total': 0, 'valid': 0, 'invalid': 0},
            'tables_figures': {'tables': 0, 'figures': 0, 'issues': 0}
        }

        # Timing tracking
        self.timing = {
            'start_time': 0,
            'extraction_time': 0,
            'review_time': 0,
            'crossref_time': 0,
            'output_time': 0,
            'total_time': 0,
            'pages_per_second': 0,
            'chunks_per_second': 0
        }

        # LLM call tracking
        self.llm_calls = {
            'total_calls': 0,
            'successful_calls': 0,
            'failed_calls': 0,
            'chunks_enhanced': 0
        }

    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from YAML file."""
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)

    async def process_document(self, pdf_path: str, document_id: Optional[str] = None) -> str:
        """
        Process a complete document.

        Args:
            pdf_path: Path to PDF file
            document_id: Optional document ID (generated if not provided)

        Returns:
            Path to generated markdown output
        """
        # Start timing
        self.timing['start_time'] = time.time()

        logger.info(f"Starting document processing: {pdf_path}")

        # Generate document ID if not provided
        if not document_id:
            document_id = Path(pdf_path).stem

        # Initialize database
        await self.db.connect()

        # Initialize LLM client if enabled
        if self.config.get('llm', {}).get('enabled', False):
            logger.info("Initializing LLM client...")
            self.llm_client = LLMClient(self.config)
            await self.llm_client.__aenter__()
            logger.info("LLM client initialized ✓")

            # Initialize completeness validator with LLM
            self.completeness_validator = CompletenessValidator(self.config, self.llm_client)
            logger.info("Completeness validator initialized ✓")

        try:
            # Step 1: Extract document
            logger.info("Step 1: Extracting PDF content...")
            step_start = time.time()
            chunks = await self._extract_document(pdf_path, document_id)
            self.timing['extraction_time'] = time.time() - step_start

            # Step 2: Review chunks
            logger.info(f"Step 2: Reviewing {len(chunks)} chunks...")
            step_start = time.time()
            await self._review_chunks(chunks, document_id)
            self.timing['review_time'] = time.time() - step_start

            # Step 3: Validate cross-references
            logger.info("Step 3: Validating cross-references...")
            step_start = time.time()
            crossref_report = await self._validate_crossrefs(document_id)
            self.timing['crossref_time'] = time.time() - step_start

            # Step 3.5: Semantic completeness validation (if LLM enabled)
            completeness_report = None
            if self.completeness_validator:
                logger.info("Step 3.5: Validating semantic completeness...")
                step_start = time.time()
                completeness_report = await self._validate_completeness(chunks)
                self.timing['completeness_time'] = time.time() - step_start
                logger.info(f"Completeness validation: {completeness_report.get('total_claims', 0)} claims analyzed")

            # Step 3.6: Terminology consistency analysis
            logger.info("Step 3.6: Analyzing terminology consistency...")
            step_start = time.time()
            terminology_report = await self._analyze_terminology(chunks)
            self.timing['terminology_time'] = time.time() - step_start
            logger.info(f"Terminology analysis: {terminology_report.get('inconsistent_terms', 0)} inconsistencies found")

            # Step 4: Generate output
            logger.info("Step 4: Generating output...")
            step_start = time.time()
            output_path = await self._generate_output(document_id, crossref_report, completeness_report)
            self.timing['output_time'] = time.time() - step_start

            # Calculate final timing metrics
            self.timing['total_time'] = time.time() - self.timing['start_time']
            total_pages = self.stats['document'].get('total_pages', 1)
            total_chunks = self.stats['processing'].get('completed', 1)

            self.timing['pages_per_second'] = total_pages / self.timing['total_time'] if self.timing['total_time'] > 0 else 0
            self.timing['chunks_per_second'] = total_chunks / self.timing['total_time'] if self.timing['total_time'] > 0 else 0

            # Step 5: Generate summary report
            logger.info("Step 5: Generating summary report...")
            summary_path = self.output_generator.generate_summary_report(self.stats, self.timing)

            # Step 6: Generate changes diff (if enabled)
            if self.config.get('output', {}).get('generate_changes_diff', True):
                logger.info("Step 6: Generating changes diff...")
                diff_path = await self.diff_generator.generate_diff_summary(
                    self.db, document_id, self.stats, self.timing
                )
                logger.info(f"Changes diff: {diff_path}")

            logger.info(f"Processing complete in {self.timing['total_time']:.1f} seconds!")
            logger.info(f"Speed: {self.timing['pages_per_second']:.1f} pages/sec")

            # Log LLM usage stats if LLM was enabled
            if self.llm_client:
                logger.info(f"LLM Calls: {self.llm_calls['total_calls']} total, {self.llm_calls['successful_calls']} successful, {self.llm_calls['failed_calls']} failed")
                logger.info(f"LLM Enhanced: {self.llm_calls['chunks_enhanced']} chunks improved by LLM")

            logger.info(f"Output: {output_path}")
            logger.info(f"Summary: {summary_path}")

            return output_path

        finally:
            # Clean up LLM client
            if self.llm_client:
                await self.llm_client.__aexit__(None, None, None)

            await self.db.close()

    async def _extract_document(self, pdf_path: str, document_id: str) -> List[Chunk]:
        """Extract and chunk the PDF document."""
        # Get document metadata
        metadata = self.extractor.get_document_metadata(pdf_path)
        self.stats['document'] = metadata

        # Insert document record
        await self.db.insert_document(
            document_id=document_id,
            filename=metadata['filename'],
            total_pages=metadata['total_pages']
        )

        # Extract chunks
        extracted_chunks = self.extractor.extract_document(pdf_path, document_id)

        logger.info(f"Extracted {len(extracted_chunks)} chunks from {metadata['total_pages']} pages")

        # IMPROVED: Inject TOC sections for accurate cross-reference validation
        if hasattr(self.extractor, 'toc_sections') and self.extractor.toc_sections:
            logger.info(f"Using {len(self.extractor.toc_sections)} section numbers from PDF TOC")
            self.crossref_validator.update_targets('section', self.extractor.toc_sections)

        # Store chunks in database
        for chunk in tqdm(extracted_chunks, desc="Storing chunks"):
            db_chunk = Chunk(
                chunk_id=chunk.chunk_id,
                document_id=document_id,
                content=chunk.content,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                section_hierarchy=chunk.section_hierarchy,
                chunk_type=chunk.chunk_type,
                metadata=chunk.metadata,
                created_at=datetime.now().isoformat()
            )
            await self.db.insert_chunk(db_chunk)

        # Update document chunk count
        await self.db.update_document_chunks(document_id, len(extracted_chunks))

        self.stats['processing']['total'] = len(extracted_chunks)

        return extracted_chunks

    async def _review_chunks(self, chunks: List, document_id: str):
        """Review all chunks."""
        total_confidence = 0.0
        completed = 0

        for chunk in tqdm(chunks, desc="Reviewing chunks"):
            try:
                # Perform appropriate review based on chunk type
                if chunk.chunk_type == 'text':
                    reviewed_content, changes, confidence = await self._review_text_chunk(chunk)
                elif chunk.chunk_type == 'table':
                    reviewed_content, changes, confidence = await self._review_table_chunk(chunk)
                elif chunk.chunk_type == 'figure':
                    reviewed_content, changes, confidence = await self._review_figure_chunk(chunk)
                else:
                    reviewed_content = chunk.content
                    changes = []
                    confidence = 1.0

                # Create review record
                review = ReviewRecord(
                    review_id=f"review_{chunk.chunk_id}_{datetime.now().timestamp()}",
                    chunk_id=chunk.chunk_id,
                    status='completed',
                    original_content=chunk.content,
                    reviewed_content=reviewed_content,
                    changes=changes,
                    confidence_score=confidence,
                    reviewer='system',
                    created_at=datetime.now().isoformat(),
                    updated_at=datetime.now().isoformat()
                )

                await self.db.insert_review(review)

                # Extract cross-references
                refs = self.crossref_validator.extract_references(
                    chunk.content,
                    chunk.chunk_id,
                    chunk.page_start
                )

                for ref in refs:
                    crossref = CrossReference(
                        ref_id=ref.ref_id,
                        chunk_id=ref.chunk_id,
                        reference_text=ref.reference_text,
                        reference_type=ref.reference_type,
                        target_id=ref.target_number,
                        is_valid=False,  # Will be validated later
                        page_number=ref.page_number
                    )
                    await self.db.insert_cross_reference(crossref)

                # Extract targets for cross-reference validation
                targets = self.crossref_validator.extract_targets(chunk.content, chunk.chunk_type)
                if targets:
                    self.crossref_validator.update_targets(chunk.chunk_type, targets)

                total_confidence += confidence
                completed += 1

            except Exception as e:
                logger.error(f"Error reviewing chunk {chunk.chunk_id}: {e}")
                self.stats['processing']['failed'] += 1

        self.stats['processing']['completed'] = completed
        if completed > 0:
            self.stats['processing']['avg_confidence'] = total_confidence / completed

    async def _review_text_chunk(self, chunk) -> tuple:
        """Review a text chunk (with optional LLM enhancement)."""
        # Language review (rule-based)
        corrected, changes = await self.language_reviewer.review_chunk(chunk.content)

        # Calculate confidence
        confidence = self.language_reviewer.calculate_confidence(changes)

        # If LLM is enabled and confidence is low, enhance with LLM
        llm_threshold = self.config.get('llm', {}).get('confidence_threshold', 0.95)
        if self.llm_client and confidence < llm_threshold:
            try:
                # Track LLM call
                self.llm_calls['total_calls'] += 1

                # Send to LLM for review
                llm_response = await self.llm_client.review_text(
                    chunk.content,
                    context=f"Section: {chunk.section_hierarchy}"
                )

                # Track successful call
                self.llm_calls['successful_calls'] += 1

                # Use LLM suggestion if it improves confidence significantly
                min_improvement = self.config.get('llm', {}).get('min_improvement', 0.05)
                if llm_response.confidence > (confidence + min_improvement):
                    corrected = llm_response.content
                    confidence = llm_response.confidence
                    self.llm_calls['chunks_enhanced'] += 1

                    # Add LLM changes to stats
                    if llm_response.metadata and 'changes' in llm_response.metadata:
                        for llm_change in llm_response.metadata['changes']:
                            # Handle both string and dict formats (defensive parsing)
                            if isinstance(llm_change, str):
                                # LLM returned array of strings instead of objects
                                changes_dict = {
                                    'type': 'llm_suggestion',
                                    'original': '',
                                    'corrected': llm_change,
                                    'position': 0,
                                    'confidence': llm_response.confidence,
                                    'reason': 'LLM suggestion'
                                }
                            elif isinstance(llm_change, dict):
                                # Expected format: object with original/corrected/reason
                                changes_dict = {
                                    'type': 'llm_suggestion',
                                    'original': llm_change.get('original', ''),
                                    'corrected': llm_change.get('corrected', ''),
                                    'position': 0,
                                    'confidence': llm_response.confidence,
                                    'reason': llm_change.get('reason', 'LLM suggestion')
                                }
                            else:
                                # Unexpected format, skip
                                continue

                            # Add to changes list for storage
                            if not isinstance(changes, list):
                                changes = list(changes)
                            # Note: storing as dict directly instead of LanguageChange object

            except Exception as e:
                logger.warning(f"LLM review failed for chunk {chunk.chunk_id}: {e}")
                self.llm_calls['failed_calls'] += 1
                # Continue with rule-based review

        # Update statistics
        for change in changes:
            self.stats['language_review']['total_changes'] += 1
            if hasattr(change, 'change_type'):
                if change.change_type == 'spelling':
                    self.stats['language_review']['spelling'] += 1
                elif change.change_type == 'grammar':
                    self.stats['language_review']['grammar'] += 1
                elif change.change_type == 'style':
                    self.stats['language_review']['style'] += 1

        # Generate diff markdown
        if changes:
            reviewed_content = self.language_reviewer.generate_diff_markdown(
                chunk.content, corrected, changes
            )
        else:
            reviewed_content = corrected

        # Convert changes to dict for storage
        changes_dict = [
            {
                'type': c.change_type if hasattr(c, 'change_type') else c.get('type', 'unknown'),
                'original': c.original if hasattr(c, 'original') else c.get('original', ''),
                'corrected': c.corrected if hasattr(c, 'corrected') else c.get('corrected', ''),
                'position': c.position if hasattr(c, 'position') else c.get('position', 0),
                'confidence': c.confidence if hasattr(c, 'confidence') else c.get('confidence', 0.8),
                'reason': c.reason if hasattr(c, 'reason') else c.get('reason', '')
            }
            for c in changes
        ]

        return reviewed_content, changes_dict, confidence

    async def _review_table_chunk(self, chunk) -> tuple:
        """Review a table chunk."""
        reviewed_content, issues = self.table_reviewer.review_table(
            chunk.content,
            chunk.metadata
        )

        self.stats['tables_figures']['tables'] += 1
        self.stats['tables_figures']['issues'] += len(issues)

        # Convert issues to dict
        changes = [
            {
                'type': 'table_issue',
                'issue_type': issue.issue_type,
                'description': issue.description,
                'row': issue.row,
                'column': issue.column,
                'severity': issue.severity
            }
            for issue in issues
        ]

        # Confidence based on severity of issues
        high_severity_count = sum(1 for i in issues if i.severity == 'high')
        confidence = 1.0 - (high_severity_count * 0.2)
        confidence = max(0.5, confidence)

        return reviewed_content, changes, confidence

    async def _review_figure_chunk(self, chunk) -> tuple:
        """Review a figure chunk."""
        reviewed_content, issues = self.table_reviewer.review_figure(
            chunk.content,
            chunk.metadata
        )

        self.stats['tables_figures']['figures'] += 1
        self.stats['tables_figures']['issues'] += len(issues)

        # Convert issues to dict
        changes = [
            {
                'type': 'figure_issue',
                'issue_type': issue.issue_type,
                'description': issue.description,
                'severity': issue.severity
            }
            for issue in issues
        ]

        # Confidence based on severity
        high_severity_count = sum(1 for i in issues if i.severity == 'high')
        confidence = 1.0 - (high_severity_count * 0.2)
        confidence = max(0.5, confidence)

        return reviewed_content, changes, confidence

    async def _validate_crossrefs(self, document_id: str) -> Dict:
        """Validate all cross-references in the document."""
        # Get all cross-references
        crossrefs = await self.db.get_cross_references(document_id)

        logger.info(f"Validating {len(crossrefs)} cross-references...")

        # Convert to validator's Reference format
        from review_crossref import Reference

        references = [
            Reference(
                ref_id=cr.ref_id,
                chunk_id=cr.chunk_id,
                reference_text=cr.reference_text,
                reference_type=cr.reference_type,
                target_number=cr.target_id or '',
                page_number=cr.page_number
            )
            for cr in crossrefs
        ]

        # Validate references
        validated_refs = self.crossref_validator.validate_references(references)

        # Update database
        for ref in validated_refs:
            await self.db.update_crossref_validity(ref.ref_id, ref.is_valid, ref.target_id)

        # Generate report
        report = self.crossref_validator.generate_reference_report(validated_refs)

        self.stats['crossref'] = {
            'total': report['total_references'],
            'valid': report['valid_references'],
            'invalid': report['invalid_references']
        }

        return report

    async def _validate_completeness(self, chunks: List) -> Dict:
        """
        Validate semantic completeness using LLM.

        Args:
            chunks: All document chunks

        Returns:
            Completeness validation report
        """
        document_structure = {
            'total_chunks': len(chunks),
            'sections': list(set(c.section_hierarchy for c in chunks))
        }

        report = await self.completeness_validator.validate_completeness(
            chunks,
            document_structure
        )

        # Store in stats
        self.stats['completeness'] = {
            'total_claims': report.get('total_claims', 0),
            'supported': report.get('claims_supported', 0),
            'unsupported': report.get('claims_unsupported', 0),
            'support_rate': report.get('support_rate', 0)
        }

        return report

    async def _analyze_terminology(self, chunks: List) -> Dict:
        """Analyze terminology consistency."""
        report = await self.terminology_analyzer.analyze_terminology(chunks)

        # Store in stats
        if report.get('enabled'):
            self.stats['terminology'] = {
                'total_unique_terms': report.get('total_unique_terms', 0),
                'inconsistent_terms': report.get('inconsistent_terms', 0),
                'consistency_rate': report.get('consistency_rate', 0)
            }

        return report

    async def _generate_output(self, document_id: str, crossref_report: Dict, completeness_report: Dict = None) -> str:
        """Generate final markdown output."""
        # Get all chunks with reviews
        all_chunks = await self.db.get_all_chunks(document_id)

        chunks_data = []
        for chunk in all_chunks:
            review = await self.db.get_review(chunk.chunk_id)

            chunk_dict = {
                'chunk_id': chunk.chunk_id,
                'content': chunk.content,
                'reviewed_content': review.reviewed_content if review else chunk.content,
                'page_start': chunk.page_start,
                'page_end': chunk.page_end,
                'section_hierarchy': chunk.section_hierarchy,
                'chunk_type': chunk.chunk_type,
                'metadata': chunk.metadata
            }

            chunks_data.append(chunk_dict)

        # Generate document
        output_path = self.output_generator.generate_document(
            chunks_data,
            self.stats['document'],
            crossref_report
        )

        return output_path


async def main():
    """Main entry point."""
    import sys
    import argparse

    parser = argparse.ArgumentParser(
        description='Datasheet Review System - Intelligent document processing with hybrid rule-based + LLM review'
    )
    parser.add_argument('pdf_path', help='Path to PDF file to review')
    parser.add_argument('--with-llm', action='store_true',
                       help='Enable LLM review for uncertain chunks (requires MCHP_LLM_API_KEY)')
    parser.add_argument('--document-id', help='Optional document ID (default: filename)')

    args = parser.parse_args()

    pdf_path = args.pdf_path

    if not Path(pdf_path).exists():
        print(f"Error: File not found: {pdf_path}")
        sys.exit(1)

    # Create system
    system = DatasheetReviewSystem()

    # Enable LLM if requested
    if args.with_llm:
        system.config['llm']['enabled'] = True
        print("\n🤖 LLM Review Mode Enabled")
        print(f"   API: {system.config['llm']['api_url']}")
        print(f"   Model: {system.config['llm']['model']}")
        print(f"   Streaming: {system.config['llm']['stream']}")
        print()

        # Check API key
        import os
        api_key = os.getenv(system.config['llm']['api_key_env'])
        if not api_key:
            print(f"❌ ERROR: {system.config['llm']['api_key_env']} environment variable not set!")
            print("   Please set it with:")
            print(f"   export {system.config['llm']['api_key_env']}='your-api-key-here'")
            sys.exit(1)

    # Process document
    output_path = await system.process_document(pdf_path, document_id=args.document_id)

    print(f"\n{'=' * 60}")
    print(f"Review complete!")

    # Display LLM usage stats if enabled
    if system.llm_client:
        print(f"\nLLM API Usage:")
        print(f"  Total Calls: {system.llm_calls['total_calls']}")
        print(f"  Successful: {system.llm_calls['successful_calls']}")
        print(f"  Failed: {system.llm_calls['failed_calls']}")
        print(f"  Chunks Enhanced: {system.llm_calls['chunks_enhanced']}")

    print(f"\nOutput: {output_path}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
