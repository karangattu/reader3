"""
Tests for Reader3 core functionality.
"""

import pytest
from dataclasses import dataclass
from reader3 import (
    Book,
    BookMetadata,
    ChapterContent,
    TOCEntry,
    clean_html_content,
    extract_plain_text,
    parse_toc_recursive,
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
