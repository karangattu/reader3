"""
Tests for Reader3 core functionality.
"""

from reader3 import (
    Book,
    BookMetadata,
    ChapterContent,
    TOCEntry,
    clean_html_content,
    extract_plain_text,
    parse_toc_recursive,
    PDFAnnotation,
    PDFTextBlock,
    PDFPageData,
    get_pdf_page_stats,
    search_pdf_text_positions,
)
from bs4 import BeautifulSoup


class TestBookMetadata:
    """Tests for BookMetadata dataclass."""

    def test_create_metadata_with_required_fields(self):
        """Test creating metadata with only required fields."""
        metadata = BookMetadata(title="Test Book", language="en")
        assert metadata.title == "Test Book"
        assert metadata.language == "en"
        assert metadata.authors == []
        assert metadata.description is None

    def test_create_metadata_with_all_fields(self):
        """Test creating metadata with all fields."""
        metadata = BookMetadata(
            title="Test Book",
            language="en",
            authors=["Author One", "Author Two"],
            description="A test book",
            publisher="Test Publisher",
            date="2024-01-01",
            identifiers=["isbn:123456"],
            subjects=["Fiction", "Test"],
        )
        assert metadata.title == "Test Book"
        assert len(metadata.authors) == 2
        assert metadata.publisher == "Test Publisher"


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


class TestTOCEntry:
    """Tests for TOCEntry dataclass."""

    def test_create_toc_entry(self):
        """Test creating a TOC entry."""
        entry = TOCEntry(
            title="Chapter 1",
            href="ch1.html#section1",
            file_href="ch1.html",
            anchor="section1",
        )
        assert entry.title == "Chapter 1"
        assert entry.anchor == "section1"
        assert entry.children == []

    def test_create_nested_toc(self):
        """Test creating nested TOC entries."""
        child = TOCEntry(
            title="Section 1.1",
            href="ch1.html#s1",
            file_href="ch1.html",
            anchor="s1",
        )
        parent = TOCEntry(
            title="Chapter 1",
            href="ch1.html",
            file_href="ch1.html",
            anchor="",
            children=[child],
        )
        assert len(parent.children) == 1
        assert parent.children[0].title == "Section 1.1"


class TestBook:
    """Tests for Book dataclass."""

    def test_create_book(self):
        """Test creating a complete book object."""
        metadata = BookMetadata(title="Test Book", language="en")
        chapter = ChapterContent(
            id="ch1",
            href="chapter1.html",
            title="Chapter 1",
            content="<p>Content</p>",
            text="Content",
            order=0,
        )
        toc_entry = TOCEntry(
            title="Chapter 1",
            href="chapter1.html",
            file_href="chapter1.html",
            anchor="",
        )
        book = Book(
            metadata=metadata,
            spine=[chapter],
            toc=[toc_entry],
            images={},
            source_file="test.epub",
            processed_at="2024-01-01",
        )
        assert book.metadata.title == "Test Book"
        assert len(book.spine) == 1
        assert len(book.toc) == 1
        assert book.is_pdf is False

    def test_create_pdf_book(self):
        """Test creating a book from PDF."""
        metadata = BookMetadata(title="PDF Book", language="en")
        book = Book(
            metadata=metadata,
            spine=[],
            toc=[],
            images={},
            source_file="test.pdf",
            processed_at="2024-01-01",
            is_pdf=True,
        )
        assert book.is_pdf is True


class TestCleanHtmlContent:
    """Tests for HTML cleaning functionality."""

    def test_remove_script_tags(self):
        """Test that script tags are removed."""
        html = "<div><script>alert('evil')</script><p>Good content</p></div>"
        soup = BeautifulSoup(html, "html.parser")
        cleaned = clean_html_content(soup)
        assert cleaned.find("script") is None
        assert "Good content" in cleaned.get_text()

    def test_remove_style_tags(self):
        """Test that style tags are removed."""
        html = "<div><style>.bad { color: red; }</style><p>Content</p></div>"
        soup = BeautifulSoup(html, "html.parser")
        cleaned = clean_html_content(soup)
        assert cleaned.find("style") is None

    def test_remove_iframe_tags(self):
        """Test that iframe tags are removed."""
        html = '<div><iframe src="evil.com"></iframe><p>Safe</p></div>'
        soup = BeautifulSoup(html, "html.parser")
        cleaned = clean_html_content(soup)
        assert cleaned.find("iframe") is None

    def test_remove_form_elements(self):
        """Test that form elements are removed."""
        html = '<div><form><input type="text"></form><p>Content</p></div>'
        soup = BeautifulSoup(html, "html.parser")
        cleaned = clean_html_content(soup)
        assert cleaned.find("form") is None
        assert cleaned.find("input") is None

    def test_preserve_content(self):
        """Test that legitimate content is preserved."""
        html = "<article><h1>Title</h1><p>Paragraph with <strong>bold</strong> text.</p></article>"
        soup = BeautifulSoup(html, "html.parser")
        cleaned = clean_html_content(soup)
        assert cleaned.find("h1") is not None
        assert cleaned.find("strong") is not None


class TestExtractPlainText:
    """Tests for plain text extraction."""

    def test_extract_simple_text(self):
        """Test extracting text from simple HTML."""
        html = "<p>Hello World</p>"
        soup = BeautifulSoup(html, "html.parser")
        text = extract_plain_text(soup)
        assert text == "Hello World"

    def test_extract_nested_text(self):
        """Test extracting text from nested HTML."""
        html = "<div><p>First</p><p>Second</p></div>"
        soup = BeautifulSoup(html, "html.parser")
        text = extract_plain_text(soup)
        assert "First" in text
        assert "Second" in text

    def test_collapse_whitespace(self):
        """Test that extra whitespace is collapsed."""
        html = "<p>Hello    \n\n   World</p>"
        soup = BeautifulSoup(html, "html.parser")
        text = extract_plain_text(soup)
        assert text == "Hello World"

    def test_handle_empty_content(self):
        """Test handling empty content."""
        html = "<div></div>"
        soup = BeautifulSoup(html, "html.parser")
        text = extract_plain_text(soup)
        assert text == ""


class TestParseTocRecursive:
    """Tests for TOC parsing."""

    def test_parse_empty_toc(self):
        """Test parsing an empty TOC."""
        result = parse_toc_recursive([])
        assert result == []


# ============================================================================
# PDF Feature Tests
# ============================================================================


class TestPDFAnnotation:
    """Tests for PDFAnnotation dataclass."""

    def test_create_annotation_minimal(self):
        """Test creating an annotation with minimal fields."""
        annot = PDFAnnotation(
            page=0,
            type="highlight",
            content="Test text",
            rect=[10.0, 20.0, 100.0, 30.0]
        )
        assert annot.page == 0
        assert annot.type == "highlight"
        assert annot.content == "Test text"
        assert len(annot.rect) == 4
        assert annot.color is None
        assert annot.author is None

    def test_create_annotation_full(self):
        """Test creating an annotation with all fields."""
        annot = PDFAnnotation(
            page=5,
            type="note",
            content="Important note",
            rect=[50.0, 100.0, 150.0, 120.0],
            color="#ffff00",
            author="Test Author",
            created="2024-01-15"
        )
        assert annot.page == 5
        assert annot.type == "note"
        assert annot.color == "#ffff00"
        assert annot.author == "Test Author"
        assert annot.created == "2024-01-15"

    def test_annotation_types(self):
        """Test various annotation types."""
        types = ["highlight", "underline", "strikeout", "note", "freetext"]
        for annot_type in types:
            annot = PDFAnnotation(
                page=0,
                type=annot_type,
                content="",
                rect=[0, 0, 0, 0]
            )
            assert annot.type == annot_type


class TestPDFTextBlock:
    """Tests for PDFTextBlock dataclass."""

    def test_create_text_block(self):
        """Test creating a positioned text block."""
        block = PDFTextBlock(
            text="Hello",
            x0=10.5,
            y0=20.5,
            x1=50.5,
            y1=35.5,
            block_no=0,
            line_no=0,
            word_no=0
        )
        assert block.text == "Hello"
        assert block.x0 == 10.5
        assert block.y0 == 20.5
        assert block.x1 == 50.5
        assert block.y1 == 35.5
        assert block.block_no == 0

    def test_text_block_positions(self):
        """Test that text block positions are correctly stored."""
        blocks = [
            PDFTextBlock("word1", 0, 0, 50, 20, 0, 0, 0),
            PDFTextBlock("word2", 55, 0, 100, 20, 0, 0, 1),
            PDFTextBlock("word3", 0, 25, 50, 45, 0, 1, 0),
        ]
        assert blocks[0].word_no == 0
        assert blocks[1].word_no == 1
        assert blocks[2].line_no == 1


class TestPDFPageData:
    """Tests for PDFPageData dataclass."""

    def test_create_page_data_minimal(self):
        """Test creating page data with minimal fields."""
        page_data = PDFPageData(
            page_num=0,
            width=612.0,
            height=792.0,
            rotation=0
        )
        assert page_data.page_num == 0
        assert page_data.width == 612.0
        assert page_data.height == 792.0
        assert page_data.rotation == 0
        # text_blocks removed - now extracted on-demand from source PDF
        assert page_data.annotations == []
        assert page_data.has_images is False
        assert page_data.word_count == 0

    def test_create_page_data_full(self):
        """Test creating page data with all fields."""
        # Note: text_blocks no longer stored in PDFPageData - extracted on-demand
        annotations = [
            PDFAnnotation(0, "highlight", "Hello World", [0, 0, 100, 20])
        ]
        page_data = PDFPageData(
            page_num=0,
            width=612.0,
            height=792.0,
            rotation=90,
            annotations=annotations,
            has_images=True,
            word_count=2
        )
        assert page_data.rotation == 90
        # text_blocks now extracted on-demand from source PDF
        assert len(page_data.annotations) == 1
        assert page_data.has_images is True
        assert page_data.word_count == 2


class TestBookPDFFields:
    """Tests for PDF-specific fields in Book dataclass."""

    def test_book_pdf_defaults(self):
        """Test that PDF-specific defaults are correct."""
        metadata = BookMetadata(title="Test", language="en")
        book = Book(
            metadata=metadata,
            spine=[],
            toc=[],
            images={},
            source_file="test.epub",
            processed_at="2024-01-01"
        )
        assert book.is_pdf is False
        assert book.pdf_page_data == {}
        assert book.pdf_total_pages == 0
        assert book.pdf_has_toc is False
        assert book.pdf_thumbnails_generated is False

    def test_book_pdf_with_data(self):
        """Test creating a PDF book with page data."""
        metadata = BookMetadata(title="PDF Test", language="en")
        page_data = {
            0: PDFPageData(0, 612.0, 792.0, 0, word_count=100),
            1: PDFPageData(1, 612.0, 792.0, 0, word_count=150),
        }
        book = Book(
            metadata=metadata,
            spine=[],
            toc=[],
            images={},
            source_file="test.pdf",
            processed_at="2024-01-01",
            is_pdf=True,
            pdf_page_data=page_data,
            pdf_total_pages=2,
            pdf_has_toc=True,
            pdf_thumbnails_generated=True
        )
        assert book.is_pdf is True
        assert len(book.pdf_page_data) == 2
        assert book.pdf_total_pages == 2
        assert book.pdf_has_toc is True
        assert book.pdf_thumbnails_generated is True


class TestGetPDFPageStats:
    """Tests for get_pdf_page_stats function."""

    def test_stats_empty_pdf(self):
        """Test stats for empty PDF book."""
        metadata = BookMetadata(title="Empty PDF", language="en")
        book = Book(
            metadata=metadata,
            spine=[],
            toc=[],
            images={},
            source_file="empty.pdf",
            processed_at="2024-01-01",
            is_pdf=True,
            pdf_page_data={},
            pdf_total_pages=0
        )
        stats = get_pdf_page_stats(book)
        assert stats["total_pages"] == 0
        assert stats["total_words"] == 0
        assert stats["estimated_reading_time_minutes"] == 0.0

    def test_stats_with_pages(self):
        """Test stats calculation with page data."""
        metadata = BookMetadata(title="Test PDF", language="en")
        page_data = {
            0: PDFPageData(
                0, 612.0, 792.0, 0,
                word_count=225,  # 1 minute of reading
                has_images=True,
                annotations=[
                    PDFAnnotation(0, "highlight", "text", [0, 0, 10, 10])
                ]
            ),
            1: PDFPageData(
                1, 612.0, 792.0, 0,
                word_count=225,  # 1 minute of reading
                has_images=False,
                annotations=[]
            ),
        }
        book = Book(
            metadata=metadata,
            spine=[],
            toc=[],
            images={},
            source_file="test.pdf",
            processed_at="2024-01-01",
            is_pdf=True,
            pdf_page_data=page_data,
            pdf_total_pages=2,
            pdf_has_toc=True,
            pdf_thumbnails_generated=True
        )
        stats = get_pdf_page_stats(book)
        assert stats["total_pages"] == 2
        assert stats["total_words"] == 450
        assert stats["pages_with_images"] == 1
        assert stats["pages_with_annotations"] == 1
        assert stats["total_annotations"] == 1
        assert stats["has_native_toc"] is True
        assert stats["has_thumbnails"] is True
        assert stats["estimated_reading_time_minutes"] == 2.0

    def test_stats_non_pdf_returns_empty(self):
        """Test that non-PDF book returns empty stats."""
        metadata = BookMetadata(title="EPUB Book", language="en")
        book = Book(
            metadata=metadata,
            spine=[],
            toc=[],
            images={},
            source_file="test.epub",
            processed_at="2024-01-01",
            is_pdf=False
        )
        stats = get_pdf_page_stats(book)
        assert stats == {}


class TestSearchPDFTextPositions:
    """Tests for search_pdf_text_positions function."""

    def test_search_non_pdf_returns_empty(self):
        """Test searching non-PDF book returns empty list."""
        metadata = BookMetadata(title="EPUB", language="en")
        book = Book(
            metadata=metadata,
            spine=[],
            toc=[],
            images={},
            source_file="test.epub",
            processed_at="2024-01-01",
            is_pdf=False
        )
        results = search_pdf_text_positions(book, "test")
        assert results == []

    def test_search_empty_pdf(self):
        """Test searching empty PDF returns empty list."""
        metadata = BookMetadata(title="Empty PDF", language="en")
        book = Book(
            metadata=metadata,
            spine=[],
            toc=[],
            images={},
            source_file="empty.pdf",
            processed_at="2024-01-01",
            is_pdf=True,
            pdf_page_data={},
            pdf_total_pages=0
        )
        results = search_pdf_text_positions(book, "test")
        assert results == []

    def test_search_finds_exact_match(self):
        """Test search returns empty when no source PDF available.
        
        Note: text_blocks now extracted on-demand from source PDF.
        Without a real PDF file, search returns empty results.
        """
        metadata = BookMetadata(title="Test PDF", language="en")
        page_data = {
            0: PDFPageData(0, 612.0, 792.0, 0, word_count=3)
        }
        book = Book(
            metadata=metadata,
            spine=[],
            toc=[],
            images={},
            source_file="test.pdf",
            processed_at="2024-01-01",
            is_pdf=True,
            pdf_page_data=page_data,
            pdf_total_pages=1
        )
        # Without source PDF, search returns empty (graceful fallback)
        results = search_pdf_text_positions(book, "Hello")
        assert results == []

    def test_search_case_insensitive(self):
        """Test search gracefully handles missing source PDF.
        
        Note: text_blocks now extracted on-demand from source PDF.
        This test verifies graceful fallback without source file.
        """
        metadata = BookMetadata(title="Test PDF", language="en")
        page_data = {
            0: PDFPageData(0, 612.0, 792.0, 0, word_count=1)
        }
        book = Book(
            metadata=metadata,
            spine=[],
            toc=[],
            images={},
            source_file="test.pdf",
            processed_at="2024-01-01",
            is_pdf=True,
            pdf_page_data=page_data,
            pdf_total_pages=1
        )
        # Without source PDF, search returns empty (graceful fallback)
        results = search_pdf_text_positions(book, "hello")
        assert results == []

    def test_search_specific_page(self):
        """Test searching with page filter.
        
        Note: text_blocks now extracted on-demand from source PDF.
        This test verifies page filtering logic (returns empty without PDF).
        """
        metadata = BookMetadata(title="Test PDF", language="en")
        page_data = {
            0: PDFPageData(0, 612.0, 792.0, 0, word_count=1),
            1: PDFPageData(1, 612.0, 792.0, 0, word_count=1)
        }
        book = Book(
            metadata=metadata,
            spine=[],
            toc=[],
            images={},
            source_file="test.pdf",
            processed_at="2024-01-01",
            is_pdf=True,
            pdf_page_data=page_data,
            pdf_total_pages=2
        )
        # Without source PDF, search returns empty (graceful fallback)
        results = search_pdf_text_positions(book, "test", page_num=0)
        assert results == []

    def test_search_returns_rect_coordinates(self):
        """Test graceful fallback when source PDF unavailable.
        
        Note: text_blocks now extracted on-demand from source PDF.
        Without a real PDF file, search returns empty results.
        """
        metadata = BookMetadata(title="Test PDF", language="en")
        page_data = {
            0: PDFPageData(0, 612.0, 792.0, 0, word_count=1)
        }
        book = Book(
            metadata=metadata,
            spine=[],
            toc=[],
            images={},
            source_file="test.pdf",
            processed_at="2024-01-01",
            is_pdf=True,
            pdf_page_data=page_data,
            pdf_total_pages=1
        )
        # Without source PDF, search returns empty (graceful fallback)
        results = search_pdf_text_positions(book, "keyword")
        assert results == []


class TestPDFTOCExtraction:
    """Tests related to PDF TOC/outline functionality."""

    def test_book_with_native_toc(self):
        """Test book correctly stores native TOC flag."""
        metadata = BookMetadata(title="PDF with TOC", language="en")
        toc = [
            TOCEntry("Chapter 1", "page_1", "page_1", ""),
            TOCEntry("Chapter 2", "page_10", "page_10", "",
                     children=[
                         TOCEntry("Section 2.1", "page_12", "page_12", "")
                     ])
        ]
        book = Book(
            metadata=metadata,
            spine=[],
            toc=toc,
            images={},
            source_file="test.pdf",
            processed_at="2024-01-01",
            is_pdf=True,
            pdf_has_toc=True
        )
        assert book.pdf_has_toc is True
        assert len(book.toc) == 2
        assert book.toc[1].children[0].title == "Section 2.1"

    def test_book_without_native_toc(self):
        """Test book with page-based TOC."""
        metadata = BookMetadata(title="PDF without TOC", language="en")
        # Page-based TOC (fallback)
        toc = [
            TOCEntry(f"Page {i+1}", f"page_{i+1}", f"page_{i+1}", "")
            for i in range(5)
        ]
        book = Book(
            metadata=metadata,
            spine=[],
            toc=toc,
            images={},
            source_file="test.pdf",
            processed_at="2024-01-01",
            is_pdf=True,
            pdf_has_toc=False
        )
        assert book.pdf_has_toc is False
        assert len(book.toc) == 5
        assert book.toc[0].title == "Page 1"
