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

    def test_delete_highlight_nonexistent(self, manager):
        """Test deleting a highlight that doesn't exist."""
        result = manager.delete_highlight("book1", "nonexistent_id")
        assert result is False

    def test_delete_highlight_wrong_book(self, manager):
        """Test deleting a highlight from wrong book returns False."""
        highlight = Highlight(
            id=generate_id(),
            book_id="book1",
            chapter_index=0,
            text="Test text",
            color="yellow"
        )
        manager.add_highlight(highlight)

        # Try to delete from different book
        result = manager.delete_highlight("book2", highlight.id)
        assert result is False

        # Original should still exist
        highlights = manager.get_highlights("book1")
        assert len(highlights) == 1

    def test_delete_multiple_highlights(self, manager):
        """Test deleting multiple highlights one by one."""
        highlight_ids = []
        for i in range(3):
            highlight = Highlight(
                id=generate_id(),
                book_id="book1",
                chapter_index=i,
                text=f"Text {i}",
                color="yellow"
            )
            manager.add_highlight(highlight)
            highlight_ids.append(highlight.id)

        # Delete first highlight
        result = manager.delete_highlight("book1", highlight_ids[0])
        assert result is True
        assert len(manager.get_highlights("book1")) == 2

        # Delete second highlight
        result = manager.delete_highlight("book1", highlight_ids[1])
        assert result is True
        assert len(manager.get_highlights("book1")) == 1

        # Delete last highlight
        result = manager.delete_highlight("book1", highlight_ids[2])
        assert result is True
        assert len(manager.get_highlights("book1")) == 0

    def test_update_highlight_color(self, manager):
        """Test changing highlight color."""
        highlight = Highlight(
            id=generate_id(),
            book_id="book1",
            chapter_index=0,
            text="Test text",
            color="yellow"
        )
        manager.add_highlight(highlight)

        # Change to green
        result = manager.update_highlight_color("book1", highlight.id, "green")
        assert result is True

        highlights = manager.get_highlights("book1")
        assert highlights[0].color == "green"

    def test_update_highlight_color_all_colors(self, manager):
        """Test changing highlight to all valid colors."""
        highlight = Highlight(
            id=generate_id(),
            book_id="book1",
            chapter_index=0,
            text="Test text",
            color="yellow"
        )
        manager.add_highlight(highlight)

        colors = ["green", "blue", "pink", "purple", "yellow"]
        for color in colors:
            result = manager.update_highlight_color("book1", highlight.id, color)
            assert result is True
            highlights = manager.get_highlights("book1")
            assert highlights[0].color == color

    def test_update_highlight_color_invalid(self, manager):
        """Test changing highlight to invalid color fails."""
        highlight = Highlight(
            id=generate_id(),
            book_id="book1",
            chapter_index=0,
            text="Test text",
            color="yellow"
        )
        manager.add_highlight(highlight)

        # Try invalid colors
        result = manager.update_highlight_color("book1", highlight.id, "red")
        assert result is False

        result = manager.update_highlight_color("book1", highlight.id, "orange")
        assert result is False

        result = manager.update_highlight_color("book1", highlight.id, "")
        assert result is False

        # Original color should be unchanged
        highlights = manager.get_highlights("book1")
        assert highlights[0].color == "yellow"

    def test_update_highlight_color_nonexistent(self, manager):
        """Test changing color of nonexistent highlight returns False."""
        result = manager.update_highlight_color("book1", "nonexistent", "green")
        assert result is False

    def test_update_highlight_color_wrong_book(self, manager):
        """Test changing color with wrong book_id returns False."""
        highlight = Highlight(
            id=generate_id(),
            book_id="book1",
            chapter_index=0,
            text="Test text",
            color="yellow"
        )
        manager.add_highlight(highlight)

        result = manager.update_highlight_color("book2", highlight.id, "green")
        assert result is False

        # Original should be unchanged
        highlights = manager.get_highlights("book1")
        assert highlights[0].color == "yellow"

    def test_highlight_persistence_after_delete(self, manager, temp_data_dir):
        """Test that deletion persists after reloading."""
        highlight = Highlight(
            id=generate_id(),
            book_id="book1",
            chapter_index=0,
            text="Test text",
            color="yellow"
        )
        manager.add_highlight(highlight)
        highlight_id = highlight.id

        # Delete the highlight
        manager.delete_highlight("book1", highlight_id)

        # Create new manager and verify deletion persisted
        new_manager = UserDataManager(temp_data_dir)
        highlights = new_manager.get_highlights("book1")
        assert len(highlights) == 0

    def test_highlight_color_persistence(self, manager, temp_data_dir):
        """Test that color change persists after reloading."""
        highlight = Highlight(
            id=generate_id(),
            book_id="book1",
            chapter_index=0,
            text="Test text",
            color="yellow"
        )
        manager.add_highlight(highlight)
        highlight_id = highlight.id

        # Change the color
        manager.update_highlight_color("book1", highlight_id, "purple")

        # Create new manager and verify color persisted
        new_manager = UserDataManager(temp_data_dir)
        highlights = new_manager.get_highlights("book1")
        assert len(highlights) == 1
        assert highlights[0].color == "purple"


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


class TestChapterProgress:
    """Tests for per-chapter progress tracking functionality."""

    def test_get_chapter_progress_empty(self, manager):
        """Test getting chapter progress when none exists."""
        progress = manager.get_chapter_progress("nonexistent_book")
        assert progress == {}

    def test_save_chapter_progress(self, manager):
        """Test saving chapter progress."""
        manager.save_chapter_progress("book1", 0, 50.0)
        
        progress = manager.get_chapter_progress("book1")
        assert progress == {0: 50.0}

    def test_save_chapter_progress_multiple_chapters(self, manager):
        """Test saving progress for multiple chapters."""
        manager.save_chapter_progress("book1", 0, 100.0)
        manager.save_chapter_progress("book1", 1, 50.0)
        manager.save_chapter_progress("book1", 2, 25.0)
        
        progress = manager.get_chapter_progress("book1")
        assert progress == {0: 100.0, 1: 50.0, 2: 25.0}

    def test_chapter_progress_only_increases(self, manager):
        """Test that chapter progress only increases (doesn't go backwards)."""
        manager.save_chapter_progress("book1", 0, 75.0)
        manager.save_chapter_progress("book1", 0, 50.0)  # Lower value
        
        progress = manager.get_chapter_progress("book1")
        assert progress[0] == 75.0  # Should stay at 75%

    def test_chapter_progress_updates_higher(self, manager):
        """Test that chapter progress updates when higher value is provided."""
        manager.save_chapter_progress("book1", 0, 50.0)
        manager.save_chapter_progress("book1", 0, 90.0)  # Higher value
        
        progress = manager.get_chapter_progress("book1")
        assert progress[0] == 90.0

    def test_chapter_progress_caps_at_100(self, manager):
        """Test that chapter progress is capped at 100%."""
        manager.save_chapter_progress("book1", 0, 150.0)  # Over 100%
        
        progress = manager.get_chapter_progress("book1")
        assert progress[0] == 100.0

    def test_chapter_progress_persistence(self, manager, temp_data_dir):
        """Test that chapter progress persists after reloading."""
        manager.save_chapter_progress("book1", 0, 80.0)
        manager.save_chapter_progress("book1", 3, 100.0)
        
        # Create new manager and verify persistence
        new_manager = UserDataManager(temp_data_dir)
        progress = new_manager.get_chapter_progress("book1")
        assert progress == {0: 80.0, 3: 100.0}

    def test_chapter_progress_multiple_books(self, manager):
        """Test that chapter progress is separate for each book."""
        manager.save_chapter_progress("book1", 0, 50.0)
        manager.save_chapter_progress("book2", 0, 75.0)
        
        progress1 = manager.get_chapter_progress("book1")
        progress2 = manager.get_chapter_progress("book2")
        
        assert progress1 == {0: 50.0}
        assert progress2 == {0: 75.0}

    def test_chapter_progress_cleanup(self, manager):
        """Test that chapter progress is cleaned up when book is deleted."""
        manager.save_chapter_progress("book1", 0, 100.0)
        manager.save_chapter_progress("book1", 1, 50.0)
        
        # Clean up book data
        manager.cleanup_book_data("book1")
        
        progress = manager.get_chapter_progress("book1")
        assert progress == {}


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


# ============================================================================
# NEW FEATURES TESTS
# ============================================================================

from user_data import ReadingSession, VocabularyWord, Annotation


class TestReadingSessions:
    """Tests for reading session functionality."""

    def test_start_reading_session(self, manager):
        """Test starting a reading session."""
        session = ReadingSession(
            id=generate_id(),
            book_id="book1",
            book_title="Test Book",
            chapter_index=0,
            chapter_title="Chapter 1"
        )
        result = manager.start_reading_session(session)
        
        assert result.book_id == "book1"
        assert result.book_title == "Test Book"
        assert result.chapter_index == 0
        assert result.chapter_title == "Chapter 1"

    def test_end_reading_session(self, manager):
        """Test ending a reading session."""
        session = ReadingSession(
            id="test_session_123",
            book_id="book1",
            book_title="Test Book",
            chapter_index=0,
            chapter_title="Chapter 1"
        )
        manager.start_reading_session(session)
        
        success = manager.end_reading_session(
            session_id="test_session_123",
            duration_seconds=300,
            pages_read=5,
            scroll_position=0.75
        )
        
        assert success is True
        sessions = manager.get_reading_sessions("book1")
        assert len(sessions) == 1
        assert sessions[0].duration_seconds == 300
        assert sessions[0].pages_read == 5
        assert sessions[0].scroll_position == 0.75
        assert sessions[0].end_time is not None

    def test_end_nonexistent_session(self, manager):
        """Test ending a session that doesn't exist."""
        success = manager.end_reading_session(
            session_id="nonexistent",
            duration_seconds=100,
            pages_read=1,
            scroll_position=0.5
        )
        assert success is False

    def test_get_reading_sessions_all(self, manager):
        """Test getting all reading sessions."""
        for i in range(3):
            session = ReadingSession(
                id=generate_id(),
                book_id=f"book{i}",
                book_title=f"Book {i}",
                chapter_index=0,
                chapter_title="Chapter 1"
            )
            manager.start_reading_session(session)
        
        sessions = manager.get_reading_sessions()
        assert len(sessions) == 3

    def test_get_reading_sessions_by_book(self, manager):
        """Test getting sessions filtered by book."""
        for i in range(2):
            session = ReadingSession(
                id=generate_id(),
                book_id="book1",
                book_title="Book 1",
                chapter_index=i,
                chapter_title=f"Chapter {i}"
            )
            manager.start_reading_session(session)
        
        session3 = ReadingSession(
            id=generate_id(),
            book_id="book2",
            book_title="Book 2",
            chapter_index=0,
            chapter_title="Chapter 1"
        )
        manager.start_reading_session(session3)
        
        sessions = manager.get_reading_sessions("book1")
        assert len(sessions) == 2
        assert all(s.book_id == "book1" for s in sessions)

    def test_get_reading_stats(self, manager):
        """Test getting reading statistics."""
        session = ReadingSession(
            id="stat_test",
            book_id="book1",
            book_title="Test Book",
            chapter_index=0,
            chapter_title="Chapter 1"
        )
        manager.start_reading_session(session)
        manager.end_reading_session(
            session_id="stat_test",
            duration_seconds=1800,  # 30 minutes
            pages_read=10,
            scroll_position=1.0
        )
        
        stats = manager.get_reading_stats()
        assert stats['total_time_seconds'] == 1800
        assert stats['total_pages'] == 10
        assert stats['session_count'] == 1

    def test_session_limit(self, manager):
        """Test that sessions are limited to 100."""
        for i in range(105):
            session = ReadingSession(
                id=generate_id(),
                book_id="book1",
                book_title="Test",
                chapter_index=0,
                chapter_title="Chapter"
            )
            manager.start_reading_session(session)
        
        sessions = manager.get_reading_sessions(limit=200)
        assert len(sessions) <= 100


class TestVocabulary:
    """Tests for vocabulary/dictionary functionality."""

    def test_add_vocabulary_word(self, manager):
        """Test adding a word to vocabulary."""
        word = VocabularyWord(
            id=generate_id(),
            book_id="book1",
            word="ephemeral",
            definition="lasting for a very short time",
            phonetic="/ɪˈfem(ə)rəl/",
            part_of_speech="adjective",
            example="fashion is ephemeral",
            chapter_index=5,
            context="The ephemeral nature of fame"
        )
        result = manager.add_vocabulary_word(word)
        
        assert result.word == "ephemeral"
        assert result.definition == "lasting for a very short time"
        assert result.part_of_speech == "adjective"

    def test_get_vocabulary_by_book(self, manager):
        """Test getting vocabulary for a specific book."""
        word1 = VocabularyWord(
            id=generate_id(),
            book_id="book1",
            word="test",
            definition="a test word"
        )
        word2 = VocabularyWord(
            id=generate_id(),
            book_id="book2",
            word="other",
            definition="another word"
        )
        manager.add_vocabulary_word(word1)
        manager.add_vocabulary_word(word2)
        
        vocab = manager.get_vocabulary("book1")
        assert len(vocab) == 1
        assert vocab[0].word == "test"

    def test_get_all_vocabulary(self, manager):
        """Test getting all vocabulary across books."""
        for i in range(3):
            word = VocabularyWord(
                id=generate_id(),
                book_id=f"book{i}",
                word=f"word{i}",
                definition=f"definition {i}"
            )
            manager.add_vocabulary_word(word)
        
        vocab = manager.get_vocabulary()
        assert len(vocab) == 3

    def test_duplicate_word_increments_count(self, manager):
        """Test that adding duplicate word increments review count."""
        word = VocabularyWord(
            id=generate_id(),
            book_id="book1",
            word="duplicate",
            definition="a test word"
        )
        manager.add_vocabulary_word(word)
        
        # Add same word again
        word2 = VocabularyWord(
            id=generate_id(),
            book_id="book1",
            word="duplicate",
            definition="different definition"
        )
        result = manager.add_vocabulary_word(word2)
        
        vocab = manager.get_vocabulary("book1")
        assert len(vocab) == 1  # Still just one word
        assert vocab[0].reviewed_count >= 1

    def test_delete_vocabulary_word(self, manager):
        """Test deleting a vocabulary word."""
        word = VocabularyWord(
            id="test_word_id",
            book_id="book1",
            word="delete_me",
            definition="to be deleted"
        )
        manager.add_vocabulary_word(word)
        
        success = manager.delete_vocabulary_word("book1", "test_word_id")
        assert success is True
        
        vocab = manager.get_vocabulary("book1")
        assert len(vocab) == 0

    def test_delete_nonexistent_word(self, manager):
        """Test deleting a word that doesn't exist."""
        success = manager.delete_vocabulary_word("book1", "nonexistent")
        assert success is False

    def test_search_vocabulary(self, manager):
        """Test searching vocabulary."""
        words = [
            VocabularyWord(
                id=generate_id(),
                book_id="book1",
                word="ephemeral",
                definition="lasting for a very short time"
            ),
            VocabularyWord(
                id=generate_id(),
                book_id="book1",
                word="perpetual",
                definition="never ending or changing"
            ),
            VocabularyWord(
                id=generate_id(),
                book_id="book1",
                word="time",
                definition="the indefinite continued progress"
            )
        ]
        for w in words:
            manager.add_vocabulary_word(w)
        
        # Search by word
        results = manager.search_vocabulary("time")
        assert len(results) >= 2  # "time" word + "lasting for a very short time"
        
        # Search by definition
        results = manager.search_vocabulary("lasting")
        assert len(results) >= 1


class TestAnnotations:
    """Tests for annotation functionality."""

    def test_add_annotation(self, manager):
        """Test adding an annotation."""
        annotation = Annotation(
            id=generate_id(),
            book_id="book1",
            chapter_index=3,
            note_text="This is an important passage",
            tags=["important", "review"]
        )
        result = manager.add_annotation(annotation)
        
        assert result.note_text == "This is an important passage"
        assert "important" in result.tags
        assert result.chapter_index == 3

    def test_add_annotation_with_highlight(self, manager):
        """Test adding annotation linked to a highlight."""
        annotation = Annotation(
            id=generate_id(),
            book_id="book1",
            chapter_index=0,
            note_text="Note about highlighted text",
            highlight_id="highlight_123"
        )
        result = manager.add_annotation(annotation)
        
        assert result.highlight_id == "highlight_123"

    def test_get_annotations_by_book(self, manager):
        """Test getting annotations for a book."""
        for i in range(3):
            annotation = Annotation(
                id=generate_id(),
                book_id="book1",
                chapter_index=i,
                note_text=f"Note {i}"
            )
            manager.add_annotation(annotation)
        
        annotations = manager.get_annotations("book1")
        assert len(annotations) == 3

    def test_get_annotations_by_chapter(self, manager):
        """Test getting annotations filtered by chapter."""
        for i in range(3):
            annotation = Annotation(
                id=generate_id(),
                book_id="book1",
                chapter_index=i % 2,  # Chapters 0, 1, 0
                note_text=f"Note {i}"
            )
            manager.add_annotation(annotation)
        
        annotations = manager.get_annotations("book1", chapter_index=0)
        assert len(annotations) == 2

    def test_update_annotation(self, manager):
        """Test updating an annotation."""
        annotation = Annotation(
            id="update_test",
            book_id="book1",
            chapter_index=0,
            note_text="Original note",
            tags=["old"]
        )
        manager.add_annotation(annotation)
        
        success = manager.update_annotation(
            book_id="book1",
            annotation_id="update_test",
            note_text="Updated note",
            tags=["new", "updated"]
        )
        
        assert success is True
        annotations = manager.get_annotations("book1")
        assert annotations[0].note_text == "Updated note"
        assert "updated" in annotations[0].tags

    def test_update_nonexistent_annotation(self, manager):
        """Test updating an annotation that doesn't exist."""
        success = manager.update_annotation(
            book_id="book1",
            annotation_id="nonexistent",
            note_text="New text"
        )
        assert success is False

    def test_delete_annotation(self, manager):
        """Test deleting an annotation."""
        annotation = Annotation(
            id="delete_test",
            book_id="book1",
            chapter_index=0,
            note_text="To be deleted"
        )
        manager.add_annotation(annotation)
        
        success = manager.delete_annotation("book1", "delete_test")
        assert success is True
        
        annotations = manager.get_annotations("book1")
        assert len(annotations) == 0

    def test_delete_nonexistent_annotation(self, manager):
        """Test deleting an annotation that doesn't exist."""
        success = manager.delete_annotation("book1", "nonexistent")
        assert success is False

    def test_search_annotations(self, manager):
        """Test searching annotations by text and tags."""
        annotations = [
            Annotation(
                id=generate_id(),
                book_id="book1",
                chapter_index=0,
                note_text="This is about quantum physics",
                tags=["science", "physics"]
            ),
            Annotation(
                id=generate_id(),
                book_id="book1",
                chapter_index=1,
                note_text="Biology chapter notes",
                tags=["science", "biology"]
            ),
            Annotation(
                id=generate_id(),
                book_id="book1",
                chapter_index=2,
                note_text="Historical overview",
                tags=["history"]
            )
        ]
        for a in annotations:
            manager.add_annotation(a)
        
        # Search by text
        results = manager.search_annotations("book1", "quantum")
        assert len(results) == 1
        
        # Search by tag
        results = manager.search_annotations("book1", "science")
        assert len(results) == 2

    def test_export_annotations_markdown(self, manager):
        """Test exporting annotations to markdown."""
        annotation = Annotation(
            id=generate_id(),
            book_id="book1",
            chapter_index=0,
            note_text="Important passage",
            tags=["review", "exam"]
        )
        manager.add_annotation(annotation)
        
        highlight = Highlight(
            id=generate_id(),
            book_id="book1",
            chapter_index=0,
            text="Highlighted text here",
            color="yellow",
            note="Note on highlight"
        )
        manager.add_highlight(highlight)
        
        markdown = manager.export_annotations_markdown("book1")
        
        assert "# Annotations and Notes" in markdown
        assert "Important passage" in markdown
        assert "#review" in markdown or "review" in markdown


class TestDataCleanup:
    """Tests for data cleanup functionality."""

    def test_cleanup_book_data_vocabulary(self, manager):
        """Test that cleanup removes vocabulary."""
        word = VocabularyWord(
            id=generate_id(),
            book_id="cleanup_test",
            word="test",
            definition="a test"
        )
        manager.add_vocabulary_word(word)
        
        manager.cleanup_book_data("cleanup_test")
        
        vocab = manager.get_vocabulary("cleanup_test")
        assert len(vocab) == 0

    def test_cleanup_book_data_annotations(self, manager):
        """Test that cleanup removes annotations."""
        annotation = Annotation(
            id=generate_id(),
            book_id="cleanup_test",
            chapter_index=0,
            note_text="Test note"
        )
        manager.add_annotation(annotation)
        
        manager.cleanup_book_data("cleanup_test")
        
        annotations = manager.get_annotations("cleanup_test")
        assert len(annotations) == 0

    def test_cleanup_book_data_sessions(self, manager):
        """Test that cleanup removes reading sessions."""
        session = ReadingSession(
            id=generate_id(),
            book_id="cleanup_test",
            book_title="Test",
            chapter_index=0,
            chapter_title="Chapter"
        )
        manager.start_reading_session(session)
        
        manager.cleanup_book_data("cleanup_test")
        
        sessions = manager.get_reading_sessions("cleanup_test")
        assert len(sessions) == 0


class TestDataPersistence:
    """Tests for data persistence with new features."""

    def test_vocabulary_persistence(self, temp_data_dir):
        """Test that vocabulary persists across manager instances."""
        manager1 = UserDataManager(temp_data_dir)
        word = VocabularyWord(
            id="persist_test",
            book_id="book1",
            word="persistent",
            definition="continuing to exist"
        )
        manager1.add_vocabulary_word(word)
        
        # New manager instance
        manager2 = UserDataManager(temp_data_dir)
        manager2._data = None  # Force reload
        vocab = manager2.get_vocabulary("book1")
        
        assert len(vocab) == 1
        assert vocab[0].word == "persistent"

    def test_annotations_persistence(self, temp_data_dir):
        """Test that annotations persist across manager instances."""
        manager1 = UserDataManager(temp_data_dir)
        annotation = Annotation(
            id="persist_annot",
            book_id="book1",
            chapter_index=0,
            note_text="Persisted note",
            tags=["test"]
        )
        manager1.add_annotation(annotation)
        
        # New manager instance
        manager2 = UserDataManager(temp_data_dir)
        manager2._data = None  # Force reload
        annotations = manager2.get_annotations("book1")
        
        assert len(annotations) == 1
        assert annotations[0].note_text == "Persisted note"

    def test_sessions_persistence(self, temp_data_dir):
        """Test that reading sessions persist across manager instances."""
        manager1 = UserDataManager(temp_data_dir)
        session = ReadingSession(
            id="persist_session",
            book_id="book1",
            book_title="Test Book",
            chapter_index=0,
            chapter_title="Chapter 1"
        )
        manager1.start_reading_session(session)
        
        # New manager instance
        manager2 = UserDataManager(temp_data_dir)
        manager2._data = None  # Force reload
        sessions = manager2.get_reading_sessions("book1")
        
        assert len(sessions) == 1
        assert sessions[0].book_title == "Test Book"
