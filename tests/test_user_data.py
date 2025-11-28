"""Tests for the user_data module."""

import json
import os
import tempfile
import pytest

from user_data import (
    UserDataManager,
    UserData,
    Bookmark,
    Highlight,
    ReadingProgress,
    SearchQuery,
    generate_id
)


@pytest.fixture
def temp_data_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def manager(temp_data_dir):
    """Create a UserDataManager instance with a temp directory."""
    return UserDataManager(temp_data_dir)


class TestUserDataManager:
    """Tests for UserDataManager class."""

    def test_initialization(self, manager):
        """Test that manager initializes correctly."""
        assert manager is not None
        data = manager.load()
        assert isinstance(data, UserData)

    def test_save_and_load(self, temp_data_dir):
        """Test saving and loading data."""
        manager = UserDataManager(temp_data_dir)

        # Add some data
        bookmark = Bookmark(
            id=generate_id(),
            book_id="book1",
            chapter_index=0,
            scroll_position=0.5,
            title="Test bookmark"
        )
        manager.add_bookmark(bookmark)

        # Create new manager and load
        new_manager = UserDataManager(temp_data_dir)
        bookmarks = new_manager.get_bookmarks("book1")
        assert len(bookmarks) == 1


class TestBookmarks:
    """Tests for bookmark functionality."""

    def test_add_bookmark(self, manager):
        """Test adding a bookmark."""
        bookmark = Bookmark(
            id=generate_id(),
            book_id="test_book",
            chapter_index=0,
            scroll_position=0.5,
            title="Test Bookmark",
            note="My note"
        )
        result = manager.add_bookmark(bookmark)

        assert result.book_id == "test_book"
        assert result.chapter_index == 0
        assert result.title == "Test Bookmark"
        assert result.note == "My note"

    def test_get_bookmarks_empty(self, manager):
        """Test getting bookmarks when none exist."""
        bookmarks = manager.get_bookmarks("nonexistent_book")
        assert bookmarks == []

    def test_get_bookmarks(self, manager):
        """Test getting bookmarks for a book."""
        for i in range(2):
            bookmark = Bookmark(
                id=generate_id(),
                book_id="book1",
                chapter_index=i,
                scroll_position=0.1 * i,
                title=f"Bookmark {i}"
            )
            manager.add_bookmark(bookmark)

        bookmark3 = Bookmark(
            id=generate_id(),
            book_id="book2",
            chapter_index=0,
            scroll_position=0.5,
            title="Other book bookmark"
        )
        manager.add_bookmark(bookmark3)

        book1_bookmarks = manager.get_bookmarks("book1")
        assert len(book1_bookmarks) == 2

        book2_bookmarks = manager.get_bookmarks("book2")
        assert len(book2_bookmarks) == 1

    def test_delete_bookmark(self, manager):
        """Test deleting a bookmark."""
        bookmark = Bookmark(
            id=generate_id(),
            book_id="book1",
            chapter_index=0,
            scroll_position=0.5,
            title="To delete"
        )
        manager.add_bookmark(bookmark)

        result = manager.delete_bookmark("book1", bookmark.id)
        assert result is True

        bookmarks = manager.get_bookmarks("book1")
        assert len(bookmarks) == 0

    def test_delete_nonexistent_bookmark(self, manager):
        """Test deleting a bookmark that doesn't exist."""
        result = manager.delete_bookmark("book1", "nonexistent_id")
        assert result is False

    def test_update_bookmark(self, manager):
        """Test updating a bookmark."""
        bookmark = Bookmark(
            id=generate_id(),
            book_id="book1",
            chapter_index=0,
            scroll_position=0.5,
            title="Original",
            note="original note"
        )
        manager.add_bookmark(bookmark)

        updated = manager.update_bookmark_note("book1", bookmark.id, "updated note")
        assert updated is True

        bookmarks = manager.get_bookmarks("book1")
        assert bookmarks[0].note == "updated note"


class TestHighlights:
    """Tests for highlight functionality."""

    def test_add_highlight(self, manager):
        """Test adding a highlight."""
        highlight = Highlight(
            id=generate_id(),
            book_id="test_book",
            chapter_index=1,
            text="Highlighted text",
            color="yellow",
            start_offset=10,
            end_offset=25
        )
        result = manager.add_highlight(highlight)

        assert result.book_id == "test_book"
        assert result.chapter_index == 1
        assert result.text == "Highlighted text"
        assert result.color == "yellow"

    def test_get_highlights(self, manager):
        """Test getting highlights for a book."""
        for i, color in enumerate(["yellow", "green"]):
            highlight = Highlight(
                id=generate_id(),
                book_id="book1",
                chapter_index=i,
                text=f"Text {i}",
                color=color
            )
            manager.add_highlight(highlight)

        highlight3 = Highlight(
            id=generate_id(),
            book_id="book2",
            chapter_index=0,
            text="Other book",
            color="blue"
        )
        manager.add_highlight(highlight3)

        book1_highlights = manager.get_highlights("book1")
        assert len(book1_highlights) == 2

    def test_get_highlights_by_chapter(self, manager):
        """Test getting highlights filtered by chapter."""
        for i in range(3):
            highlight = Highlight(
                id=generate_id(),
                book_id="book1",
                chapter_index=i % 2,  # 0, 1, 0
                text=f"Text {i}",
                color="yellow"
            )
            manager.add_highlight(highlight)

        chapter0_highlights = manager.get_highlights("book1", chapter_index=0)
        assert len(chapter0_highlights) == 2

        chapter1_highlights = manager.get_highlights("book1", chapter_index=1)
        assert len(chapter1_highlights) == 1

    def test_delete_highlight(self, manager):
        """Test deleting a highlight."""
        highlight = Highlight(
            id=generate_id(),
            book_id="book1",
            chapter_index=0,
            text="To delete",
            color="yellow"
        )
        manager.add_highlight(highlight)

        result = manager.delete_highlight("book1", highlight.id)
        assert result is True

        highlights = manager.get_highlights("book1")
        assert len(highlights) == 0

    def test_update_highlight_note(self, manager):
        """Test updating highlight note."""
        highlight = Highlight(
            id=generate_id(),
            book_id="book1",
            chapter_index=0,
            text="Text",
            color="yellow",
            note="original"
        )
        manager.add_highlight(highlight)

        updated = manager.update_highlight_note("book1", highlight.id, "updated note")
        assert updated is True

        highlights = manager.get_highlights("book1")
        assert highlights[0].note == "updated note"

    def test_highlight_colors(self, manager):
        """Test different highlight colors."""
        colors = ["yellow", "green", "blue", "pink", "purple"]

        for color in colors:
            highlight = Highlight(
                id=generate_id(),
                book_id="book1",
                chapter_index=0,
                text=f"text_{color}",
                color=color
            )
            manager.add_highlight(highlight)

        highlights = manager.get_highlights("book1")
        assert len(highlights) == 5
        for h, expected_color in zip(highlights, colors):
            assert h.color == expected_color


class TestReadingProgress:
    """Tests for reading progress functionality."""

    def test_save_progress(self, manager):
        """Test saving reading progress."""
        progress = ReadingProgress(
            book_id="test_book",
            chapter_index=5,
            scroll_position=0.45,
            total_chapters=10
        )
        manager.save_progress(progress)

        result = manager.get_progress("test_book")
        assert result is not None
        assert result.chapter_index == 5
        assert result.scroll_position == 0.45

    def test_get_progress_nonexistent(self, manager):
        """Test getting progress for a book with no progress."""
        progress = manager.get_progress("nonexistent_book")
        assert progress is None

    def test_update_progress(self, manager):
        """Test updating reading progress."""
        progress1 = ReadingProgress(
            book_id="book1",
            chapter_index=0,
            scroll_position=0.1
        )
        manager.save_progress(progress1)

        progress2 = ReadingProgress(
            book_id="book1",
            chapter_index=2,
            scroll_position=0.5
        )
        manager.save_progress(progress2)

        result = manager.get_progress("book1")
        assert result.chapter_index == 2
        assert result.scroll_position == 0.5

    def test_update_reading_time(self, manager):
        """Test updating reading time."""
        progress = ReadingProgress(
            book_id="book1",
            chapter_index=0,
            scroll_position=0.0,
            reading_time_seconds=100
        )
        manager.save_progress(progress)

        manager.update_reading_time("book1", 50)

        result = manager.get_progress("book1")
        assert result.reading_time_seconds == 150


class TestSearchHistory:
    """Tests for search history functionality."""

    def test_add_search_query(self, manager):
        """Test adding a search query."""
        query = SearchQuery(query="test query", book_id="book1", results_count=5)
        manager.add_search(query)

        history = manager.get_search_history()
        assert len(history) == 1
        assert history[0].query == "test query"

    def test_search_history_limit(self, manager):
        """Test that search history limit works."""
        for i in range(60):
            query = SearchQuery(query=f"query_{i}", book_id="book1", results_count=i)
            manager.add_search(query)

        # Should only keep 50 searches
        data = manager.load()
        assert len(data.search_history) <= 50

    def test_clear_search_history(self, manager):
        """Test clearing search history."""
        query1 = SearchQuery(query="query1", book_id="book1", results_count=1)
        query2 = SearchQuery(query="query2", book_id="book1", results_count=2)
        manager.add_search(query1)
        manager.add_search(query2)

        manager.clear_search_history()

        history = manager.get_search_history()
        assert len(history) == 0

    def test_search_history_order(self, manager):
        """Test that search history is in reverse chronological order."""
        for word in ["first", "second", "third"]:
            query = SearchQuery(query=word, book_id="book1", results_count=0)
            manager.add_search(query)

        history = manager.get_search_history()

        # Most recent should be first
        assert history[0].query == "third"
        assert history[2].query == "first"


class TestExport:
    """Tests for export functionality."""

    def test_export_book_data_json(self, manager):
        """Test exporting book data as JSON."""
        bookmark = Bookmark(
            id=generate_id(),
            book_id="book1",
            chapter_index=0,
            scroll_position=0.5,
            title="Bookmark",
            note="note"
        )
        manager.add_bookmark(bookmark)

        highlight = Highlight(
            id=generate_id(),
            book_id="book1",
            chapter_index=1,
            text="Highlight text",
            color="yellow"
        )
        manager.add_highlight(highlight)

        json_str = manager.export_book_data("book1", "json")

        data = json.loads(json_str)
        assert "bookmarks" in data
        assert "highlights" in data
        assert len(data["bookmarks"]) == 1
        assert len(data["highlights"]) == 1

    def test_export_book_data_markdown(self, manager):
        """Test exporting book data as Markdown."""
        bookmark = Bookmark(
            id=generate_id(),
            book_id="book1",
            chapter_index=0,
            scroll_position=0.5,
            title="Bookmark Title",
            note="note"
        )
        manager.add_bookmark(bookmark)

        highlight = Highlight(
            id=generate_id(),
            book_id="book1",
            chapter_index=1,
            text="Highlight text",
            color="yellow"
        )
        manager.add_highlight(highlight)

        md = manager.export_book_data("book1", "markdown")

        assert "# Notes and Highlights" in md
        assert "## Bookmarks" in md
        assert "## Highlights" in md
        assert "Bookmark Title" in md
        assert "Highlight text" in md

    def test_export_all_data(self, manager):
        """Test exporting all data."""
        bookmark1 = Bookmark(
            id=generate_id(),
            book_id="book1",
            chapter_index=0,
            scroll_position=0.5,
            title="B1"
        )
        bookmark2 = Bookmark(
            id=generate_id(),
            book_id="book2",
            chapter_index=0,
            scroll_position=0.5,
            title="B2"
        )
        manager.add_bookmark(bookmark1)
        manager.add_bookmark(bookmark2)

        json_str = manager.export_all_data("json")

        data = json.loads(json_str)
        assert "bookmarks" in data
        assert "book1" in data["bookmarks"]
        assert "book2" in data["bookmarks"]


class TestDataPersistence:
    """Tests for data persistence across sessions."""

    def test_data_survives_reload(self, temp_data_dir):
        """Test that data persists across manager instances."""
        # First session
        manager1 = UserDataManager(temp_data_dir)

        bookmark = Bookmark(
            id=generate_id(),
            book_id="book1",
            chapter_index=0,
            scroll_position=0.5,
            title="Test"
        )
        manager1.add_bookmark(bookmark)

        highlight = Highlight(
            id=generate_id(),
            book_id="book1",
            chapter_index=0,
            text="Highlighted",
            color="green"
        )
        manager1.add_highlight(highlight)

        progress = ReadingProgress(
            book_id="book1",
            chapter_index=5,
            scroll_position=0.5
        )
        manager1.save_progress(progress)

        # Second session - new manager instance
        manager2 = UserDataManager(temp_data_dir)

        bookmarks = manager2.get_bookmarks("book1")
        highlights = manager2.get_highlights("book1")
        loaded_progress = manager2.get_progress("book1")

        assert len(bookmarks) == 1
        assert bookmarks[0].title == "Test"

        assert len(highlights) == 1
        assert highlights[0].color == "green"

        assert loaded_progress is not None
        assert loaded_progress.chapter_index == 5

    def test_corrupted_data_handling(self, temp_data_dir):
        """Test handling of corrupted data file."""
        # Write invalid JSON
        data_file = os.path.join(temp_data_dir, "user_data.json")
        with open(data_file, 'w') as f:
            f.write("invalid json {{{")

        # Should not crash, should start with empty data
        manager = UserDataManager(temp_data_dir)
        data = manager.load()
        assert isinstance(data, UserData)


class TestCleanup:
    """Tests for cleanup functionality."""

    def test_cleanup_book_data(self, manager):
        """Test removing all data for a deleted book."""
        # Add data for two books
        for book_id in ["book1", "book2"]:
            bookmark = Bookmark(
                id=generate_id(),
                book_id=book_id,
                chapter_index=0,
                scroll_position=0.5,
                title="Test"
            )
            manager.add_bookmark(bookmark)

            highlight = Highlight(
                id=generate_id(),
                book_id=book_id,
                chapter_index=0,
                text="Text",
                color="yellow"
            )
            manager.add_highlight(highlight)

            progress = ReadingProgress(
                book_id=book_id,
                chapter_index=0,
                scroll_position=0.0
            )
            manager.save_progress(progress)

        # Cleanup book1
        manager.cleanup_book_data("book1")

        # book1 data should be gone
        assert len(manager.get_bookmarks("book1")) == 0
        assert len(manager.get_highlights("book1")) == 0
        assert manager.get_progress("book1") is None

        # book2 data should still exist
        assert len(manager.get_bookmarks("book2")) == 1
        assert len(manager.get_highlights("book2")) == 1
        assert manager.get_progress("book2") is not None


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_special_characters_in_book_id(self, manager):
        """Test handling of special characters in book IDs."""
        book_id = "Book with spaces & special-chars_123"

        bookmark = Bookmark(
            id=generate_id(),
            book_id=book_id,
            chapter_index=0,
            scroll_position=0.5,
            title="Test"
        )
        manager.add_bookmark(bookmark)
        bookmarks = manager.get_bookmarks(book_id)

        assert len(bookmarks) == 1
        assert bookmarks[0].book_id == book_id

    def test_unicode_in_text(self, manager):
        """Test handling of unicode characters."""
        text = "日本語テキスト 中文 한국어 émojis 🎉📚"
        note = "Note with unicode: été, naïve, 北京"

        highlight = Highlight(
            id=generate_id(),
            book_id="book1",
            chapter_index=0,
            text=text,
            color="yellow",
            note=note
        )
        manager.add_highlight(highlight)

        highlights = manager.get_highlights("book1")
        assert highlights[0].text == text
        assert highlights[0].note == note

    def test_empty_text(self, manager):
        """Test handling of empty text."""
        bookmark = Bookmark(
            id=generate_id(),
            book_id="book1",
            chapter_index=0,
            scroll_position=0.0,
            title="",
            note=""
        )
        manager.add_bookmark(bookmark)

        bookmarks = manager.get_bookmarks("book1")
        assert bookmarks[0].title == ""
        assert bookmarks[0].note == ""

    def test_large_text(self, manager):
        """Test handling of large text content."""
        large_text = "x" * 10000

        highlight = Highlight(
            id=generate_id(),
            book_id="book1",
            chapter_index=0,
            text=large_text,
            color="yellow"
        )
        manager.add_highlight(highlight)

        highlights = manager.get_highlights("book1")
        assert len(highlights[0].text) == 10000

    def test_generate_id_uniqueness(self):
        """Test that generated IDs are unique."""
        ids = set()
        for _ in range(100):
            id_ = generate_id()
            assert id_ not in ids
            ids.add(id_)
        assert len(ids) == 100
