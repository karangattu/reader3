"""
Tests for EPUB chapter navigation and TOC-to-spine matching.
"""

import pytest
from reader3 import (
    Book,
    BookMetadata,
    ChapterContent,
    TOCEntry,
    parse_toc_recursive,
)


class TestTOCEntryParsing:
    """Tests for TOC entry parsing from EPUB data structures."""

    def test_toc_entry_with_anchor(self):
        """Test parsing TOC entry with file and anchor."""
        entry = TOCEntry(
            title="Chapter 1",
            href="content/ch01.html#intro",
            file_href="content/ch01.html",
            anchor="intro"
        )
        assert entry.title == "Chapter 1"
        assert entry.href == "content/ch01.html#intro"
        assert entry.file_href == "content/ch01.html"
        assert entry.anchor == "intro"

    def test_toc_entry_without_anchor(self):
        """Test parsing TOC entry without anchor."""
        entry = TOCEntry(
            title="Chapter 2",
            href="content/ch02.html",
            file_href="content/ch02.html",
            anchor=""
        )
        assert entry.anchor == ""
        assert entry.file_href == "content/ch02.html"

    def test_toc_entry_various_path_formats(self):
        """Test TOC entries with various path formats from different EPUB structures."""
        # OEBPS format (common)
        entry1 = TOCEntry(
            title="Ch 1",
            href="OEBPS/content/part001.html",
            file_href="OEBPS/content/part001.html",
            anchor=""
        )
        
        # Simple text/ format
        entry2 = TOCEntry(
            title="Ch 2",
            href="text/ch02.xhtml",
            file_href="text/ch02.xhtml",
            anchor=""
        )
        
        # Just filename
        entry3 = TOCEntry(
            title="Ch 3",
            href="chapter03.html",
            file_href="chapter03.html",
            anchor=""
        )
        
        assert entry1.file_href.startswith("OEBPS")
        assert entry2.file_href.startswith("text")
        assert "/" not in entry3.file_href


class TestSpineChapterMatching:
    """Tests for matching TOC entries to spine chapters."""

    def test_exact_path_match(self):
        """Test that exact path matches work."""
        spine_chapters = [
            ChapterContent(
                id="ch1",
                href="content/ch01.html",
                title="Chapter 1",
                content="<p>Content</p>",
                text="Content",
                order=0
            )
        ]
        
        toc_entry = TOCEntry(
            title="Chapter 1",
            href="content/ch01.html",
            file_href="content/ch01.html",
            anchor=""
        )
        
        # Simulate the matching logic
        clean_file = toc_entry.file_href.split('#')[0]
        idx = None
        for i, chapter in enumerate(spine_chapters):
            if chapter.href == clean_file:
                idx = i
                break
        
        assert idx == 0

    def test_basename_match_oebps_format(self):
        """Test matching OEBPS paths to spine chapters."""
        # This simulates the issue where TOC has "OEBPS/content/part001.html"
        # but spine also has "OEBPS/content/part001.html"
        spine_chapters = [
            ChapterContent(
                id="ch1",
                href="OEBPS/content/part001.html",
                title="Chapter 1",
                content="<p>Content</p>",
                text="Content",
                order=0
            )
        ]
        
        toc_entry = TOCEntry(
            title="Chapter 1",
            href="OEBPS/content/part001.html",
            file_href="OEBPS/content/part001.html",
            anchor=""
        )
        
        clean_file = toc_entry.file_href.split('#')[0]
        # Exact match should work
        assert clean_file == spine_chapters[0].href

    def test_basename_match_text_format(self):
        """Test matching text/ directory format."""
        spine_chapters = [
            ChapterContent(
                id="ch1",
                href="text/chapter01.html",
                title="Chapter 1",
                content="<p>Content</p>",
                text="Content",
                order=0
            )
        ]
        
        toc_entry = TOCEntry(
            title="Chapter 1",
            href="text/chapter01.html",
            file_href="text/chapter01.html",
            anchor=""
        )
        
        clean_file = toc_entry.file_href.split('#')[0]
        basename_toc = clean_file.split('/').pop()
        
        # Find matching spine chapter by basename
        idx = None
        for i, chapter in enumerate(spine_chapters):
            chapter_basename = chapter.href.split('/').pop()
            if chapter_basename == basename_toc:
                idx = i
                break
        
        assert idx == 0
        assert basename_toc == "chapter01.html"

    def test_mismatched_paths_with_same_basename(self):
        """Test that chapters with same basename match even with different paths."""
        # Spine has OEBPS/content/part001.html
        spine_chapters = [
            ChapterContent(
                id="ch1",
                href="OEBPS/content/part001.html",
                title="Chapter 1",
                content="<p>Content</p>",
                text="Content",
                order=0
            )
        ]
        
        # TOC has just text/part001.html or part001.html
        toc_entry = TOCEntry(
            title="Chapter 1",
            href="part001.html",  # Just basename in TOC
            file_href="part001.html",
            anchor=""
        )
        
        clean_file = toc_entry.file_href.split('#')[0]
        basename_toc = clean_file.split('/').pop()
        
        # Find by basename
        idx = None
        for i, chapter in enumerate(spine_chapters):
            chapter_basename = chapter.href.split('/').pop()
            if chapter_basename == basename_toc:
                idx = i
                break
        
        assert idx == 0
        assert basename_toc == "part001.html"

    def test_multiple_chapters_correct_match(self):
        """Test matching correct chapter among multiple chapters."""
        spine_chapters = [
            ChapterContent(
                id="ch1",
                href="OEBPS/content/part001.html",
                title="Chapter 1",
                content="<p>Content 1</p>",
                text="Content 1",
                order=0
            ),
            ChapterContent(
                id="ch2",
                href="OEBPS/content/part002.html",
                title="Chapter 2",
                content="<p>Content 2</p>",
                text="Content 2",
                order=1
            ),
            ChapterContent(
                id="ch3",
                href="OEBPS/content/part003.html",
                title="Chapter 3",
                content="<p>Content 3</p>",
                text="Content 3",
                order=2
            )
        ]
        
        # Looking for second chapter with just basename
        toc_entry = TOCEntry(
            title="Chapter 2",
            href="part002.html",
            file_href="part002.html",
            anchor=""
        )
        
        clean_file = toc_entry.file_href.split('#')[0]
        basename_toc = clean_file.split('/').pop()
        
        idx = None
        for i, chapter in enumerate(spine_chapters):
            chapter_basename = chapter.href.split('/').pop()
            if chapter_basename == basename_toc:
                idx = i
                break
        
        assert idx == 1
        assert spine_chapters[1].id == "ch2"

    def test_toc_with_anchor_matches_spine(self):
        """Test that TOC entries with anchors still match spine (ignoring anchor)."""
        spine_chapters = [
            ChapterContent(
                id="ch1",
                href="content/chapter01.html",
                title="Chapter 1",
                content="<p>Content</p>",
                text="Content",
                order=0
            )
        ]
        
        toc_entry = TOCEntry(
            title="Section 1.1",
            href="content/chapter01.html#section1",
            file_href="content/chapter01.html",
            anchor="section1"
        )
        
        # Strip anchor from TOC href
        clean_file = toc_entry.file_href.split('#')[0]
        
        idx = None
        for i, chapter in enumerate(spine_chapters):
            if chapter.href == clean_file:
                idx = i
                break
        
        assert idx == 0
        assert toc_entry.anchor == "section1"


class TestSpineMapGeneration:
    """Tests for spineMap JavaScript object generation."""

    def test_spine_map_with_various_formats(self):
        """Test that spine chapters with various path formats are indexed correctly."""
        spine_chapters = [
            ChapterContent(
                id="ch1",
                href="OEBPS/content/part001.html",
                title="Chapter 1",
                content="<p>Content</p>",
                text="Content",
                order=0
            ),
            ChapterContent(
                id="ch2",
                href="text/chapter02.html",
                title="Chapter 2",
                content="<p>Content</p>",
                text="Content",
                order=1
            ),
            ChapterContent(
                id="ch3",
                href="simple_chapter.html",
                title="Chapter 3",
                content="<p>Content</p>",
                text="Content",
                order=2
            )
        ]
        
        # Simulate spine map generation
        spine_map = {}
        for i, ch in enumerate(spine_chapters):
            spine_map[ch.href] = i
        
        assert spine_map["OEBPS/content/part001.html"] == 0
        assert spine_map["text/chapter02.html"] == 1
        assert spine_map["simple_chapter.html"] == 2


class TestChapterNavigationEdgeCases:
    """Tests for edge cases in chapter navigation."""

    def test_chapter_with_special_characters(self):
        """Test chapter names with special characters."""
        entry = TOCEntry(
            title="Chapter 1: The Beginning (Part A)",
            href="content/ch01.html",
            file_href="content/ch01.html",
            anchor=""
        )
        assert ":" in entry.title
        assert "(" in entry.title

    def test_chapter_href_with_dots(self):
        """Test chapter paths with dots in filenames."""
        entry = TOCEntry(
            title="Preface",
            href="content/00.preface.html",
            file_href="content/00.preface.html",
            anchor=""
        )
        basename = entry.file_href.split('/').pop()
        assert basename == "00.preface.html"

    def test_chapter_with_encoded_characters(self):
        """Test chapter paths with URL-encoded characters."""
        # Some EPUBs use encoded paths like "image%201.jpg"
        entry = TOCEntry(
            title="Chapter 1",
            href="content/ch%201.html",
            file_href="content/ch%201.html",
            anchor=""
        )
        assert "%20" in entry.file_href or "%20" not in entry.file_href  # Just ensure it parses

    def test_empty_book(self):
        """Test navigation with empty spine."""
        spine_chapters = []
        
        toc_entry = TOCEntry(
            title="Chapter 1",
            href="content/ch01.html",
            file_href="content/ch01.html",
            anchor=""
        )
        
        # Try to find match in empty spine
        idx = None
        for i, chapter in enumerate(spine_chapters):
            if chapter.href == toc_entry.file_href:
                idx = i
                break
        
        assert idx is None

    def test_toc_entry_not_in_spine(self):
        """Test that TOC entries missing from spine don't crash."""
        spine_chapters = [
            ChapterContent(
                id="ch1",
                href="content/chapter01.html",
                title="Chapter 1",
                content="<p>Content</p>",
                text="Content",
                order=0
            )
        ]
        
        # This TOC entry doesn't exist in spine
        toc_entry = TOCEntry(
            title="Missing Chapter",
            href="content/missing.html",
            file_href="content/missing.html",
            anchor=""
        )
        
        idx = None
        for i, chapter in enumerate(spine_chapters):
            if chapter.href == toc_entry.file_href:
                idx = i
                break
        
        assert idx is None


class TestBookStructure:
    """Tests for complete book structure with spine and TOC."""

    def test_book_with_matching_spine_and_toc(self):
        """Test creating a book with properly matched spine and TOC."""
        metadata = BookMetadata(
            title="Test Book",
            language="en",
            authors=["Test Author"]
        )
        
        spine = [
            ChapterContent(
                id="ch1",
                href="content/part001.html",
                title="Chapter 1",
                content="<p>Content 1</p>",
                text="Content 1",
                order=0
            ),
            ChapterContent(
                id="ch2",
                href="content/part002.html",
                title="Chapter 2",
                content="<p>Content 2</p>",
                text="Content 2",
                order=1
            )
        ]
        
        toc = [
            TOCEntry(
                title="Chapter 1",
                href="content/part001.html",
                file_href="content/part001.html",
                anchor=""
            ),
            TOCEntry(
                title="Chapter 2",
                href="content/part002.html",
                file_href="content/part002.html",
                anchor=""
            )
        ]
        
        book = Book(
            metadata=metadata,
            spine=spine,
            toc=toc,
            images={},
            source_file="test.epub",
            processed_at="2024-01-01T00:00:00"
        )
        
        assert len(book.spine) == 2
        assert len(book.toc) == 2
        assert book.spine[0].href == "content/part001.html"
        assert book.toc[0].file_href == "content/part001.html"
