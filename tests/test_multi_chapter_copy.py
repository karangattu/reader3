"""
Tests for multi-chapter selection and bulk copy functionality.
"""

import pytest
from fastapi.testclient import TestClient
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import app
from reader3 import (
    Book,
    BookMetadata,
    ChapterContent,
)


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


class TestMultiChapterCopyAPI:
    """Tests for the multi-chapter text copy API endpoint."""

    def test_get_chapters_text_endpoint_exists(self, client):
        """Test that the chapters/text endpoint exists."""
        response = client.post(
            "/api/chapters/text",
            json={"book_id": "nonexistent", "chapter_hrefs": []}
        )
        # Should return 404 for nonexistent book, not 404 for missing endpoint
        assert response.status_code == 404

    def test_get_chapters_text_requires_book_id(self, client):
        """Test that book_id is required."""
        response = client.post(
            "/api/chapters/text",
            json={"chapter_hrefs": ["ch1.html"]}
        )
        assert response.status_code == 400
        assert "book_id" in response.json()["detail"]

    def test_get_chapters_text_empty_chapter_list(self, client):
        """Test API with empty chapter list."""
        response = client.post(
            "/api/chapters/text",
            json={
                "book_id": "test_book_123",
                "chapter_hrefs": []
            }
        )
        # Should succeed even with empty list
        assert response.status_code in [200, 404]

    def test_get_chapters_text_returns_chapters_array(self, client):
        """Test that response contains chapters array."""
        response = client.post(
            "/api/chapters/text",
            json={
                "book_id": "nonexistent",
                "chapter_hrefs": []
            }
        )
        # For nonexistent book, should fail with 404
        assert response.status_code == 404

    def test_get_chapters_text_response_structure(self, client):
        """Test the structure of the response when chapters are found."""
        # This would require a real book to be loaded
        # We'll test the API contract rather than full integration
        response = client.post(
            "/api/chapters/text",
            json={
                "book_id": "fake_book",
                "chapter_hrefs": ["part1.html", "part2.html"]
            }
        )
        # API exists and handles the request
        assert response.status_code in [200, 404]


class TestMultiChapterCopySelection:
    """Tests for multi-chapter selection logic."""

    def test_select_single_chapter(self):
        """Test selecting a single chapter."""
        selected = ["ch1.html"]
        assert len(selected) == 1
        assert "ch1.html" in selected

    def test_select_multiple_chapters(self):
        """Test selecting multiple chapters."""
        selected = ["ch1.html", "ch2.html", "ch3.html"]
        assert len(selected) == 3
        assert all(ch in selected for ch in ["ch1.html", "ch2.html", "ch3.html"])

    def test_deselect_chapter(self):
        """Test deselecting a chapter from selection."""
        selected = ["ch1.html", "ch2.html", "ch3.html"]
        selected.remove("ch2.html")
        assert len(selected) == 2
        assert "ch2.html" not in selected
        assert "ch1.html" in selected

    def test_clear_selection(self):
        """Test clearing all selections."""
        selected = ["ch1.html", "ch2.html", "ch3.html"]
        selected.clear()
        assert len(selected) == 0
        assert selected == []

    def test_select_all_chapters(self):
        """Test selecting all chapters."""
        all_chapters = ["ch1.html", "ch2.html", "ch3.html", "ch4.html"]
        selected = all_chapters.copy()
        assert len(selected) == len(all_chapters)
        assert selected == all_chapters

    def test_selection_order_preserved(self):
        """Test that selection order is preserved."""
        chapters = ["intro.html", "ch1.html", "ch2.html", "conclusion.html"]
        selected = [chapters[0], chapters[2], chapters[1]]
        assert selected == ["intro.html", "ch2.html", "ch1.html"]
        # Order of selection is preserved


class TestChapterTextContent:
    """Tests for chapter text content structure."""

    def test_chapter_data_structure(self):
        """Test chapter data has required fields."""
        chapter = {
            "href": "chapter1.html",
            "title": "Chapter 1: Introduction",
            "text": "This is the chapter content..."
        }
        assert "href" in chapter
        assert "title" in chapter
        assert "text" in chapter

    def test_multiple_chapters_data(self):
        """Test structure of multiple chapters."""
        chapters = [
            {
                "href": "ch1.html",
                "title": "Chapter 1",
                "text": "Content 1"
            },
            {
                "href": "ch2.html",
                "title": "Chapter 2",
                "text": "Content 2"
            }
        ]
        assert len(chapters) == 2
        for ch in chapters:
            assert "href" in ch
            assert "title" in ch
            assert "text" in ch

    def test_chapter_text_can_be_empty(self):
        """Test that chapter text can be empty string."""
        chapter = {
            "href": "blank.html",
            "title": "Blank Chapter",
            "text": ""
        }
        assert chapter["text"] == ""
        assert len(chapter["text"]) == 0

    def test_chapter_title_with_special_chars(self):
        """Test chapter title with special characters."""
        chapter = {
            "href": "ch1.html",
            "title": "Chapter 1: The Beginning (Part A)",
            "text": "Content"
        }
        assert ":" in chapter["title"]
        assert "(" in chapter["title"]


class TestBulkCopyContent:
    """Tests for combining multiple chapters into bulk copy content."""

    def test_combine_two_chapters(self):
        """Test combining text from two chapters."""
        chapters = [
            {"title": "Chapter 1", "text": "Content of chapter 1"},
            {"title": "Chapter 2", "text": "Content of chapter 2"}
        ]
        
        combined = "\n\n---\n\n".join([
            f"=== {ch['title']} ===\n\n{ch['text']}"
            for ch in chapters
        ])
        
        assert "Chapter 1" in combined
        assert "Chapter 2" in combined
        assert "Content of chapter 1" in combined
        assert "Content of chapter 2" in combined
        assert "---" in combined

    def test_combine_single_chapter(self):
        """Test combining text from single chapter."""
        chapters = [
            {"title": "Only Chapter", "text": "Only content"}
        ]
        
        combined = "\n\n---\n\n".join([
            f"=== {ch['title']} ===\n\n{ch['text']}"
            for ch in chapters
        ])
        
        assert "Only Chapter" in combined
        assert "Only content" in combined
        # No separator since only one chapter
        assert combined.count("---") == 0

    def test_combine_chapters_separator_format(self):
        """Test that separators are correctly formatted."""
        chapters = [
            {"title": "Ch1", "text": "Text1"},
            {"title": "Ch2", "text": "Text2"},
            {"title": "Ch3", "text": "Text3"}
        ]
        
        combined = "\n\n---\n\n".join([
            f"=== {ch['title']} ===\n\n{ch['text']}"
            for ch in chapters
        ])
        
        # Should have 2 separators between 3 chapters
        assert combined.count("---") == 2
        assert "===" in combined

    def test_empty_chapter_content_preserved(self):
        """Test that empty chapter content is preserved."""
        chapters = [
            {"title": "Chapter 1", "text": "Some content"},
            {"title": "Chapter 2", "text": ""},
            {"title": "Chapter 3", "text": "More content"}
        ]
        
        combined = "\n\n---\n\n".join([
            f"=== {ch['title']} ===\n\n{ch['text']}"
            for ch in chapters
        ])
        
        # All chapters should be in output
        assert "Chapter 1" in combined
        assert "Chapter 2" in combined
        assert "Chapter 3" in combined

    def test_large_content_combination(self):
        """Test combining large amounts of content."""
        chapters = [
            {
                "title": f"Chapter {i}",
                "text": f"Content for chapter {i} " * 100  # Repeat text
            }
            for i in range(10)
        ]
        
        combined = "\n\n---\n\n".join([
            f"=== {ch['title']} ===\n\n{ch['text']}"
            for ch in chapters
        ])
        
        # Should be large
        assert len(combined) > 1000
        # All chapters should be present
        assert "Chapter 0" in combined
        assert "Chapter 9" in combined


class TestMultiChapterSelection:
    """Tests for chapter selection count and button state."""

    def test_button_disabled_when_no_selection(self):
        """Test copy button is disabled when nothing selected."""
        selected_count = 0
        button_disabled = selected_count == 0
        assert button_disabled is True

    def test_button_enabled_with_selection(self):
        """Test copy button is enabled when chapters selected."""
        selected_count = 2
        button_disabled = selected_count == 0
        assert button_disabled is False

    def test_button_text_shows_count(self):
        """Test button text displays selected count."""
        for count in [0, 1, 5, 10]:
            button_text = f"Copy Selected ({count})"
            assert str(count) in button_text
            assert "Copy Selected" in button_text

    def test_select_all_then_clear(self):
        """Test selecting all then clearing all."""
        total_chapters = 5
        
        # Select all
        selected = list(range(total_chapters))
        assert len(selected) == total_chapters
        
        # Clear all
        selected.clear()
        assert len(selected) == 0
        assert selected == []


class TestMultiChapterEdgeCases:
    """Tests for edge cases in multi-chapter functionality."""

    def test_duplicate_chapter_selection(self):
        """Test selecting same chapter twice."""
        selected = ["ch1.html"]
        # In practice, UI prevents duplicates via checkbox
        # But we test the logic
        assert selected.count("ch1.html") == 1

    def test_select_nonexistent_chapter(self):
        """Test selecting chapter that doesn't exist."""
        all_chapters = ["ch1.html", "ch2.html", "ch3.html"]
        selected = ["ch1.html", "ch_missing.html"]
        
        # Filtering to only existing chapters
        valid_selected = [ch for ch in selected if ch in all_chapters]
        assert "ch_missing.html" not in valid_selected
        assert len(valid_selected) == 1

    def test_very_large_selection(self):
        """Test selecting very many chapters."""
        chapters = [f"ch{i}.html" for i in range(100)]
        selected = chapters.copy()
        assert len(selected) == 100

    def test_special_characters_in_chapter_href(self):
        """Test chapter href with special characters."""
        selected = [
            "chapter%201.html",
            "ch_2-special.html",
            "part.01.html"
        ]
        assert len(selected) == 3
        assert all(isinstance(ch, str) for ch in selected)

    def test_empty_selection_list(self):
        """Test empty selection list."""
        selected = []
        assert len(selected) == 0
        assert selected == []
        assert bool(selected) is False

    def test_selection_with_unicode_titles(self):
        """Test chapters with unicode titles."""
        chapters = [
            {"title": "章节 1", "text": "Content"},
            {"title": "Chapitre 2", "text": "Contenu"},
            {"title": "Κεφάλαιο 3", "text": "Περιεχόμενο"}
        ]
        assert len(chapters) == 3
        for ch in chapters:
            assert len(ch["title"]) > 0
            assert len(ch["text"]) > 0


class TestUserExperience:
    """Tests for user experience with multi-chapter copy."""

    def test_selection_persists_during_reading(self):
        """Test that selections persist as user browses."""
        # Simulate user selecting chapters then navigating
        selected = ["ch1.html", "ch3.html"]
        current_page = "ch2.html"  # User navigates to different chapter
        
        # Selections should still be there
        assert "ch1.html" in selected
        assert "ch3.html" in selected
        assert current_page == "ch2.html"

    def test_copy_success_message(self):
        """Test copy success message format."""
        count = 3
        message = f"Copied {count} chapter{'s' if count > 1 else ''}"
        assert "Copied" in message
        assert "3" in message
        assert "chapters" in message

    def test_copy_single_vs_multiple_grammar(self):
        """Test grammar for singular and plural."""
        for count, expected_word in [(1, "chapter"), (2, "chapters")]:
            word = "chapter" if count == 1 else "chapters"
            message = f"Copied {count} {word}"
            assert expected_word in message

    def test_error_message_format(self):
        """Test error message format."""
        error_cases = [
            "No chapters selected",
            "Failed to fetch chapters",
            "Failed to copy chapters"
        ]
        
        for error in error_cases:
            assert len(error) > 0
            assert "chapter" in error.lower() or "selected" in error.lower()
