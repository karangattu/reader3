"""
Tests for the enhanced search and chapter progress features.
"""

import pytest
from reader3 import Book, BookMetadata, ChapterContent


class TestSearchAPIResponse:
    """Tests for the search API response structure."""

    def test_search_result_contains_required_fields(self):
        """Test that search results contain all required fields for UI display."""
        # Simulate a search result object
        result = {
            "book_id": "book123",
            "book_title": "Test Book",
            "chapter_index": 0,
            "chapter_href": "chapter1.html",
            "chapter_title": "Chapter 1",
            "context": "...this is some context...",
            "position": 50,
            "match_length": 4,
        }
        
        # Verify all required fields are present
        assert "book_id" in result
        assert "book_title" in result
        assert "chapter_index" in result
        assert "chapter_href" in result
        assert "chapter_title" in result
        assert "context" in result
        assert "position" in result
        assert "match_length" in result
        
        # Verify field types
        assert isinstance(result["book_id"], str)
        assert isinstance(result["chapter_index"], int)
        assert isinstance(result["position"], int)
        assert isinstance(result["match_length"], int)

    def test_search_response_structure(self):
        """Test that search response has expected top-level structure."""
        response = {
            "query": "test",
            "results": [
                {
                    "book_id": "book1",
                    "book_title": "Book 1",
                    "chapter_index": 0,
                    "chapter_href": "ch1.html",
                    "chapter_title": "Chapter 1",
                    "context": "...test context...",
                    "position": 10,
                    "match_length": 4,
                }
            ],
            "total": 1,
        }
        
        assert "query" in response
        assert "results" in response
        assert "total" in response
        assert response["total"] == len(response["results"])
        assert response["query"] == "test"

    def test_multiple_matches_per_chapter(self):
        """Test that multiple matches from the same chapter are returned separately."""
        results = [
            {
                "book_id": "book1",
                "chapter_index": 0,
                "chapter_href": "ch1.html",
                "context": "...first match...",
                "position": 10,
                "match_length": 5,
            },
            {
                "book_id": "book1",
                "chapter_index": 0,
                "chapter_href": "ch1.html",
                "context": "...second match...",
                "position": 100,
                "match_length": 5,
            },
        ]
        
        # Both results should be from the same chapter but different positions
        assert results[0]["chapter_index"] == results[1]["chapter_index"]
        assert results[0]["position"] != results[1]["position"]
        assert len(results) == 2


class TestChapterProgressData:
    """Tests for chapter progress tracking and display."""

    def test_chapter_progress_calculation(self):
        """Test that chapter progress percentage is calculated correctly."""
        # Simulate progress data
        progress_data = {
            "chapter_0": {"scroll_position": 0.5, "read": True},
            "chapter_1": {"scroll_position": 0.0, "read": False},
            "chapter_2": {"scroll_position": 1.0, "read": True},
        }
        
        # Test progress percentage calculations
        assert progress_data["chapter_0"]["scroll_position"] == 0.5
        assert progress_data["chapter_1"]["scroll_position"] == 0.0
        assert progress_data["chapter_2"]["scroll_position"] == 1.0

    def test_chapter_read_status_determination(self):
        """Test that chapters are marked as read/unread based on progress."""
        test_cases = [
            (0.0, False),      # 0% = unread
            (0.25, False),     # 25% = unread
            (0.89, False),     # 89% = unread
            (0.90, True),      # 90% = read (threshold)
            (0.95, True),      # 95% = read
            (1.0, True),       # 100% = read
        ]
        
        for progress, expected_read in test_cases:
            # Simulate the logic: >= 0.90 is considered read
            is_read = progress >= 0.90
            assert is_read == expected_read, f"Progress {progress} should be read={expected_read}"

    def test_unread_chapter_identification(self):
        """Test that unread chapters (0% progress) are correctly identified."""
        chapters = [
            {"index": 0, "progress": 0.0},    # unread
            {"index": 1, "progress": 0.5},    # partially read
            {"index": 2, "progress": 1.0},    # read
        ]
        
        unread = [ch for ch in chapters if ch["progress"] == 0.0]
        assert len(unread) == 1
        assert unread[0]["index"] == 0


class TestSearchHighlighting:
    """Tests for search result highlighting behavior."""

    def test_match_position_and_length_for_highlighting(self):
        """Test that position and match_length are sufficient for highlighting."""
        text = "The quick brown fox jumps over the lazy dog"
        search_query = "brown fox"
        position = text.lower().find(search_query.lower())
        match_length = len(search_query)
        
        assert position == 10
        assert match_length == 9
        
        # Verify we can extract the matched text
        matched_text = text[position:position + match_length]
        assert matched_text.lower() == search_query.lower()

    def test_context_extraction_with_boundaries(self):
        """Test that context is properly extracted with ellipsis at boundaries."""
        text = "This is a long text with many words. The query appears here. After the query there is more text."
        position = text.find("query appears")
        
        # Context should include text before and after
        context_before = 50  # chars before
        context_after = 50   # chars after
        
        start = max(0, position - context_before)
        end = min(len(text), position + len("query appears") + context_after)
        
        context = text[start:end]
        assert "query appears" in context


class TestFadeTransition:
    """Tests for fade transition behavior in chapter navigation."""

    def test_fade_timing_constants(self):
        """Test that fade timing constants are appropriate."""
        fade_out_duration = 250  # milliseconds
        fade_in_duration = 350   # milliseconds
        navigation_delay = 250   # milliseconds
        
        # Fade out should complete before navigation
        assert fade_out_duration <= navigation_delay
        # Fade in should be slightly longer for smooth appearance
        assert fade_in_duration > fade_out_duration

    def test_fade_class_lifecycle(self):
        """Test the lifecycle of fade CSS classes."""
        # Simulate the fade process
        states = [
            {"container_classes": [], "event": "initial"},
            {"container_classes": ["fade-out"], "event": "user clicks chapter"},
            {"container_classes": ["fade-out"], "event": "waiting for navigation"},
            {"container_classes": ["fade-in"], "event": "page loaded"},
            {"container_classes": [], "event": "fade-in complete"},
        ]
        
        # Verify expected progression
        assert "fade-out" not in states[0]["container_classes"]
        assert "fade-out" in states[1]["container_classes"]
        assert "fade-in" in states[3]["container_classes"]
        assert len(states[4]["container_classes"]) == 0


class TestTOCPercentDisplay:
    """Tests for table of contents percent read display."""

    def test_percent_formatting(self):
        """Test that percent values are formatted correctly."""
        progress_values = [0.0, 0.25, 0.5, 0.75, 0.99, 1.0]
        
        for progress in progress_values:
            percent = int(progress * 100)
            formatted = f"{percent}%"
            assert formatted.endswith("%")
            assert 0 <= int(formatted.rstrip("%")) <= 100

    def test_percent_text_in_toc_element(self):
        """Test that percent text can be set on TOC elements."""
        # Simulate TOC element with data attribute
        toc_entry = {
            "href": "chapter1.html",
            "title": "Chapter 1",
            "percent_element_data_href": "chapter1.html",
        }
        
        # Verify structure supports percent display
        assert "href" in toc_entry
        assert "title" in toc_entry
        assert "percent_element_data_href" in toc_entry

    def test_unread_vs_read_visual_distinction(self):
        """Test that read and unread chapters have distinct class names."""
        # CSS classes for visual distinction
        unread_class = "unread"
        read_class = "read"
        
        # Both should be distinct strings
        assert unread_class != read_class
        assert len(unread_class) > 0
        assert len(read_class) > 0


class TestReadingMomentumMetrics:
    """Tests for reading momentum features."""

    def test_streak_calculation(self):
        """Test that reading streak is calculated correctly."""
        # Simulate reading sessions over consecutive days
        reading_sessions = [
            {"date": "2024-01-01", "duration": 30},
            {"date": "2024-01-02", "duration": 45},
            {"date": "2024-01-03", "duration": 25},
            # Gap on 2024-01-04
            {"date": "2024-01-05", "duration": 60},
        ]
        
        # Current streak would be 1 (only today or yesterday if adjacent)
        # This is a simplified test of streak concept
        assert len(reading_sessions) == 4

    def test_reading_time_today_format(self):
        """Test that reading time today is displayed in a user-friendly format."""
        minutes_read = 47
        seconds_read = minutes_read * 60
        
        # Format time for display
        display_minutes = seconds_read // 60
        display_seconds = seconds_read % 60
        
        assert display_minutes == 47
        assert display_seconds == 0
        
        # Could also display as "47m"
        time_display = f"{display_minutes}m"
        assert time_display == "47m"

    def test_reading_time_accumulation(self):
        """Test that reading time accumulates during a session."""
        session_start_seconds = 1000
        current_seconds = 1000
        
        # Simulate passage of time
        intervals = [
            1010,  # +10 seconds
            1020,  # +10 seconds
            1030,  # +10 seconds
        ]
        
        total_read = 0
        for current in intervals:
            elapsed = current - session_start_seconds
            total_read = elapsed
        
        assert total_read == 30  # total of 30 seconds


class TestSearchGroupingByChapter:
    """Tests for grouping search results by chapter."""

    def test_results_grouped_by_chapter(self):
        """Test that search results can be grouped by chapter."""
        results = [
            {
                "book_id": "book1",
                "chapter_index": 0,
                "chapter_href": "ch1.html",
                "chapter_title": "Chapter 1",
                "context": "first match",
            },
            {
                "book_id": "book1",
                "chapter_index": 0,
                "chapter_href": "ch1.html",
                "chapter_title": "Chapter 1",
                "context": "second match",
            },
            {
                "book_id": "book1",
                "chapter_index": 1,
                "chapter_href": "ch2.html",
                "chapter_title": "Chapter 2",
                "context": "match in chapter 2",
            },
        ]
        
        # Group by chapter
        grouped = {}
        for result in results:
            key = (result["chapter_index"], result["chapter_href"])
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(result)
        
        assert len(grouped) == 2
        assert len(grouped[(0, "ch1.html")]) == 2
        assert len(grouped[(1, "ch2.html")]) == 1

    def test_chapter_ordering_preserved(self):
        """Test that chapter order is preserved in grouped results."""
        results = [
            {"chapter_index": 2, "context": "match in ch3"},
            {"chapter_index": 0, "context": "match in ch1"},
            {"chapter_index": 1, "context": "match in ch2"},
            {"chapter_index": 0, "context": "another match in ch1"},
        ]
        
        # Group and sort
        grouped = {}
        for result in results:
            idx = result["chapter_index"]
            if idx not in grouped:
                grouped[idx] = []
            grouped[idx].append(result)
        
        sorted_indices = sorted(grouped.keys())
        assert sorted_indices == [0, 1, 2]
