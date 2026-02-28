"""
Additional tests for Reader3 - covering utility functions and basic structures.
"""

import pytest
import sys
import os
from unittest.mock import Mock
import tempfile

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from reader3 import (
    BookMetadata,
    ChapterContent,
    TOCEntry,
    PDFAnnotation,
    PDFTextBlock,
    PDFPageData,
    Book,
    sanitize_text,
    validate_pdf,
    get_pdf_page_stats,
)


class TestSanitizeText:
    """Tests for sanitize_text utility function."""

    def test_sanitize_none_text(self):
        """Test sanitizing None text."""
        result = sanitize_text(None)
        assert result is None

    def test_sanitize_normal_text(self):
        """Test sanitizing normal text."""
        result = sanitize_text("Normal text")
        assert result == "Normal text"

    def test_sanitize_text_with_newlines(self):
        """Test sanitizing text with newlines."""
        result = sanitize_text("Line 1\nLine 2")
        assert result is not None

    def test_sanitize_empty_string(self):
        """Test sanitizing empty string."""
        result = sanitize_text("")
        assert result == "" or result is None

    def test_sanitize_text_with_special_chars(self):
        """Test sanitizing text with special characters."""
        result = sanitize_text("Text with <>&\"' chars")
        assert result is not None


class TestChapterContent:
    """Tests for ChapterContent dataclass."""

    def test_create_chapter(self):
        """Test creating a chapter content object."""
        chapter = ChapterContent(
            id="ch1",
            href="chapter1.html",
            title="Chapter 1",
            content="<p>Hello World</p>",
            text="Hello World",
            order=0,
        )
        assert chapter.id == "ch1"
        assert chapter.href == "chapter1.html"
        assert chapter.order == 0
        assert chapter.title == "Chapter 1"


class TestTOCEntry:
    """Tests for TOC entry."""

    def test_create_toc_entry_basic(self):
        """Test creating basic TOC entry."""
        entry = TOCEntry(
            title="Chapter 1",
            href="ch1.html",
            file_href="ch1.html",
            anchor="",
        )
        assert entry.title == "Chapter 1"
        assert entry.href == "ch1.html"

    def test_toc_entry_with_children(self):
        """Test TOC entry with children."""
        child = TOCEntry(
            title="Section",
            href="ch1.html#s1",
            file_href="ch1.html",
            anchor="s1",
        )
        parent = TOCEntry(
            title="Chapter",
            href="ch1.html",
            file_href="ch1.html",
            anchor="",
            children=[child],
        )
        assert len(parent.children) == 1


class TestBookMetadata:
    """Tests for BookMetadata."""

    def test_create_basic_metadata(self):
        """Test creating basic metadata."""
        metadata = BookMetadata(title="Test Book", language="en")
        assert metadata.title == "Test Book"
        assert metadata.language == "en"
        assert metadata.authors == []

    def test_create_full_metadata(self):
        """Test creating full metadata."""
        metadata = BookMetadata(
            title="Test",
            language="en",
            authors=["Author"],
            description="Desc",
            publisher="Pub",
            date="2024",
        )
        assert metadata.title == "Test"
        assert len(metadata.authors) == 1


class TestPDFPageData:
    """Tests for PDFPageData."""

    def test_create_pdf_page(self):
        """Test creating PDF page data."""
        page = PDFPageData(
            page_num=0,
            width=612.0,
            height=792.0,
            rotation=0,
        )
        assert page.page_num == 0
        assert page.width == 612.0
        assert len(page.annotations) == 0


class TestPDFAnnotation:
    """Tests for PDFAnnotation."""

    def test_create_annotation(self):
        """Test creating annotation."""
        annot = PDFAnnotation(
            page=0,
            type="highlight",
            content="Important",
            rect=[10, 10, 100, 20],
        )
        assert annot.page == 0
        assert annot.type == "highlight"


class TestPDFTextBlock:
    """Tests for PDFTextBlock."""

    def test_create_text_block(self):
        """Test creating text block."""
        block = PDFTextBlock(
            text="Content",
            x0=0.0,
            y0=0.0,
            x1=100.0,
            y1=20.0,
            block_no=0,
            line_no=0,
            word_no=0,
        )
        assert block.text == "Content"
        assert block.x0 == 0.0


class TestValidatePDF:
    """Tests for PDF validation."""

    def test_validate_missing_pdf(self):
        """Test validating missing PDF file."""
        result = validate_pdf("/nonexistent/file.pdf")
        assert isinstance(result, dict)
        assert "valid" in result

    def test_validate_invalid_pdf_content(self):
        """Test validating invalid PDF content."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"Not a PDF")
            f.flush()
            pdf_path = f.name

        try:
            result = validate_pdf(pdf_path)
            assert isinstance(result, dict)
        finally:
            os.unlink(pdf_path)


class TestGetPDFPageStats:
    """Tests for PDF page statistics."""

    def test_get_stats_empty_pdf(self):
        """Test getting stats for empty PDF."""
        mock_book = Mock()
        mock_book.pdf_page_data = {}

        result = get_pdf_page_stats(mock_book)
        assert isinstance(result, dict)

    def test_get_stats_with_pages(self):
        """Test getting stats with pages."""
        page = PDFPageData(
            page_num=0,
            width=612.0,
            height=792.0,
            rotation=0,
            word_count=50,
        )
        mock_book = Mock()
        mock_book.pdf_page_data = {0: page}

        result = get_pdf_page_stats(mock_book)
        assert isinstance(result, dict)
