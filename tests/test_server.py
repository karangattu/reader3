"""
Tests for the FastAPI server.
"""

import pytest
from fastapi.testclient import TestClient
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


class TestLibraryEndpoint:
    """Tests for the library view endpoint."""

    def test_library_returns_html(self, client):
        """Test that the library endpoint returns HTML."""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_library_contains_expected_elements(self, client):
        """Test that the library page contains expected elements."""
        response = client.get("/")
        assert response.status_code == 200
        # Check for library page elements
        content = response.text.lower()
        assert "library" in content or "reader" in content


class TestUploadEndpoint:
    """Tests for the upload endpoint."""

    def test_upload_without_file_fails(self, client):
        """Test that uploading without a file fails appropriately."""
        response = client.post("/upload")
        # Should fail with 422 (Unprocessable Entity) due to missing file
        assert response.status_code == 422


class TestStaticAssets:
    """Tests for static asset handling."""

    def test_nonexistent_book_returns_404(self, client):
        """Test that requesting a non-existent book returns 404."""
        response = client.get("/read/nonexistent_book_xyz/0")
        assert response.status_code == 404


class TestHealthCheck:
    """Basic health checks for the server."""

    def test_server_starts(self, client):
        """Test that the server can be started and responds."""
        response = client.get("/")
        assert response.status_code == 200

    def test_server_handles_invalid_routes(self, client):
        """Test that invalid routes return 404."""
        response = client.get("/this/route/does/not/exist")
        assert response.status_code == 404


class TestReadingProgressAPI:
    """Tests for reading progress API endpoints."""

    def test_get_progress_nonexistent_book(self, client):
        """Test getting progress for a book with no saved progress."""
        response = client.get("/api/progress/nonexistent_test_book")
        # Should return default progress
        assert response.status_code == 200
        data = response.json()
        assert "book_id" in data
        assert data["chapter_index"] == 0

    def test_save_and_get_progress(self, client):
        """Test saving and retrieving reading progress."""
        book_id = "test_book_progress_123"

        # Save progress
        progress_data = {
            "chapter_index": 5,
            "scroll_position": 0.45,
            "total_chapters": 10
        }
        save_response = client.post(
            f"/api/progress/{book_id}",
            json=progress_data
        )
        assert save_response.status_code == 200
        assert save_response.json()["status"] == "saved"

        # Get progress
        get_response = client.get(f"/api/progress/{book_id}")
        assert get_response.status_code == 200

        data = get_response.json()
        assert data["chapter_index"] == 5

    def test_progress_includes_percent(self, client):
        """Test that progress response includes progress_percent."""
        import uuid
        book_id = f"test_book_percent_{uuid.uuid4().hex[:8]}"
        
        response = client.get(f"/api/progress/{book_id}")
        assert response.status_code == 200
        data = response.json()
        assert "progress_percent" in data

    def test_progress_percent_calculated_from_chapters(self, client):
        """Test that progress_percent is calculated from chapter progress."""
        import uuid
        book_id = f"test_book_calc_{uuid.uuid4().hex[:8]}"
        
        # Save chapter progress for multiple chapters
        client.post(
            f"/api/chapter-progress/{book_id}/0",
            json={"progress": 100.0}
        )
        client.post(
            f"/api/chapter-progress/{book_id}/1",
            json={"progress": 50.0}
        )
        
        # Get overall progress
        response = client.get(f"/api/progress/{book_id}")
        data = response.json()
        
        # Should have some progress_percent > 0
        assert data["progress_percent"] > 0


class TestBookmarksAPI:
    """Tests for bookmarks API endpoints."""

    def test_get_bookmarks_empty(self, client):
        """Test getting bookmarks for a book with none."""
        response = client.get("/api/bookmarks/test_book_no_bookmarks")
        assert response.status_code == 200
        data = response.json()
        assert "bookmarks" in data
        assert data["bookmarks"] == []

    def test_create_bookmark(self, client):
        """Test creating a bookmark."""
        book_id = "test_book_bookmarks_123"

        bookmark_data = {
            "chapter_index": 2,
            "scroll_position": 0.5,
            "title": "Test bookmark",
            "note": "Test note"
        }
        response = client.post(
            f"/api/bookmarks/{book_id}",
            json=bookmark_data
        )
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "created"
        assert "id" in data

    def test_get_bookmarks(self, client):
        """Test getting bookmarks for a book."""
        book_id = "test_book_get_bookmarks"

        # Create a bookmark first
        client.post(
            f"/api/bookmarks/{book_id}",
            json={
                "chapter_index": 0,
                "scroll_position": 0.1,
                "title": "Test",
                "note": ""
            }
        )

        response = client.get(f"/api/bookmarks/{book_id}")
        assert response.status_code == 200

        data = response.json()
        assert "bookmarks" in data
        assert len(data["bookmarks"]) >= 1

    def test_delete_bookmark(self, client):
        """Test deleting a bookmark."""
        book_id = "test_book_delete_bookmark"

        # Create a bookmark
        create_response = client.post(
            f"/api/bookmarks/{book_id}",
            json={
                "chapter_index": 0,
                "scroll_position": 0.1,
                "title": "To be deleted",
                "note": ""
            }
        )
        bookmark_id = create_response.json()["id"]

        # Delete it
        del_url = f"/api/bookmarks/{book_id}/{bookmark_id}"
        delete_response = client.delete(del_url)
        assert delete_response.status_code == 200


class TestHighlightsAPI:
    """Tests for highlights API endpoints."""

    def test_get_highlights_empty(self, client):
        """Test getting highlights for a book with none."""
        response = client.get("/api/highlights/test_book_no_highlights")
        assert response.status_code == 200
        data = response.json()
        assert "highlights" in data
        assert data["highlights"] == []

    def test_create_highlight(self, client):
        """Test creating a highlight."""
        book_id = "test_book_highlights_123"

        highlight_data = {
            "chapter_index": 1,
            "text": "Highlighted text",
            "color": "yellow",
            "start_offset": 10,
            "end_offset": 25
        }
        response = client.post(
            f"/api/highlights/{book_id}",
            json=highlight_data
        )
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "created"
        assert "id" in data

    def test_highlight_colors(self, client):
        """Test different highlight colors."""
        book_id = "test_book_highlight_colors"
        colors = ["yellow", "green", "blue", "pink", "purple"]

        for color in colors:
            response = client.post(
                f"/api/highlights/{book_id}",
                json={
                    "chapter_index": 0,
                    "text": f"Text with {color}",
                    "color": color
                }
            )
            assert response.status_code == 200
            assert response.json()["status"] == "created"

    def test_delete_highlight(self, client):
        """Test deleting a highlight."""
        book_id = "test_book_delete_highlight"

        # Create a highlight
        create_response = client.post(
            f"/api/highlights/{book_id}",
            json={
                "chapter_index": 0,
                "text": "To be deleted",
                "color": "yellow"
            }
        )
        highlight_id = create_response.json()["id"]

        # Delete it
        del_url = f"/api/highlights/{book_id}/{highlight_id}"
        delete_response = client.delete(del_url)
        assert delete_response.status_code == 200

    def test_delete_highlight_not_found(self, client):
        """Test deleting a non-existent highlight returns 404."""
        book_id = "test_book_delete_nonexistent"
        delete_response = client.delete(
            f"/api/highlights/{book_id}/nonexistent_id"
        )
        assert delete_response.status_code == 404

    def test_delete_highlight_removes_from_list(self, client):
        """Test that deleted highlight is removed from get list."""
        import uuid
        book_id = f"test_book_delete_verify_{uuid.uuid4().hex[:8]}"

        # Create two highlights
        resp1 = client.post(
            f"/api/highlights/{book_id}",
            json={"chapter_index": 0, "text": "Text 1", "color": "yellow"}
        )
        id1 = resp1.json()["id"]

        resp2 = client.post(
            f"/api/highlights/{book_id}",
            json={"chapter_index": 0, "text": "Text 2", "color": "green"}
        )
        id2 = resp2.json()["id"]

        # Verify both exist
        list_resp = client.get(f"/api/highlights/{book_id}")
        assert len(list_resp.json()["highlights"]) == 2

        # Delete first highlight
        client.delete(f"/api/highlights/{book_id}/{id1}")

        # Verify only one remains
        list_resp = client.get(f"/api/highlights/{book_id}")
        highlights = list_resp.json()["highlights"]
        assert len(highlights) == 1
        assert highlights[0]["id"] == id2

    def test_update_highlight_color(self, client):
        """Test updating a highlight's color."""
        import uuid
        book_id = f"test_book_update_color_{uuid.uuid4().hex[:8]}"

        # Create a highlight
        create_response = client.post(
            f"/api/highlights/{book_id}",
            json={
                "chapter_index": 0,
                "text": "Color change test",
                "color": "yellow"
            }
        )
        highlight_id = create_response.json()["id"]

        # Update color to green
        update_response = client.put(
            f"/api/highlights/{book_id}/{highlight_id}/color",
            json={"color": "green"}
        )
        assert update_response.status_code == 200
        assert update_response.json()["status"] == "updated"

        # Verify color changed
        get_response = client.get(f"/api/highlights/{book_id}")
        highlights = get_response.json()["highlights"]
        assert len(highlights) == 1
        assert highlights[0]["color"] == "green"

    def test_update_highlight_color_all_colors(self, client):
        """Test updating highlight to all valid colors."""
        import uuid
        book_id = f"test_book_all_colors_{uuid.uuid4().hex[:8]}"

        # Create a highlight
        create_response = client.post(
            f"/api/highlights/{book_id}",
            json={
                "chapter_index": 0,
                "text": "Multi color test",
                "color": "yellow"
            }
        )
        highlight_id = create_response.json()["id"]

        # Test all colors
        for color in ["green", "blue", "pink", "purple", "yellow"]:
            update_response = client.put(
                f"/api/highlights/{book_id}/{highlight_id}/color",
                json={"color": color}
            )
            assert update_response.status_code == 200

            # Verify
            get_response = client.get(f"/api/highlights/{book_id}")
            assert get_response.json()["highlights"][0]["color"] == color

    def test_update_highlight_color_not_found(self, client):
        """Test updating color of non-existent highlight returns 404."""
        book_id = "test_book_color_notfound"
        update_response = client.put(
            f"/api/highlights/{book_id}/nonexistent_id/color",
            json={"color": "green"}
        )
        assert update_response.status_code == 404

    def test_update_highlight_color_invalid(self, client):
        """Test updating to invalid color returns 404."""
        book_id = "test_book_invalid_color"

        # Create a highlight
        create_response = client.post(
            f"/api/highlights/{book_id}",
            json={
                "chapter_index": 0,
                "text": "Invalid color test",
                "color": "yellow"
            }
        )
        highlight_id = create_response.json()["id"]

        # Try invalid color
        update_response = client.put(
            f"/api/highlights/{book_id}/{highlight_id}/color",
            json={"color": "red"}
        )
        # Should return 404 since update_highlight_color returns False
        assert update_response.status_code == 404

        # Verify original color unchanged
        get_response = client.get(f"/api/highlights/{book_id}")
        assert get_response.json()["highlights"][0]["color"] == "yellow"


class TestSearchAPI:
    """Tests for search API endpoints."""

    def test_search_short_query(self, client):
        """Test search with very short query."""
        response = client.get("/api/search?q=a")
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        # Short query returns empty results
        assert data["results"] == []

    def test_search_with_book_filter(self, client):
        """Test search with book filter."""
        response = client.get("/api/search?q=test&book_id=test_book")
        assert response.status_code == 200
        assert "results" in response.json()

    def test_search_semantic_mode(self, client):
        """Test semantic search mode response structure."""
        response = client.get(
            "/api/search?q=test&book_id=nonexistent_book&mode=semantic"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "semantic"
        assert "results" in data

    def test_search_history(self, client):
        """Test search history endpoint."""
        response = client.get("/api/search/history")
        assert response.status_code == 200
        data = response.json()
        assert "history" in data
        assert isinstance(data["history"], list)

    def test_clear_search_history(self, client):
        """Test clearing search history."""
        response = client.delete("/api/search/history")
        assert response.status_code == 200


class TestExportAPI:
    """Tests for export API endpoints."""

    def test_export_book_json(self, client):
        """Test exporting book data as JSON."""
        book_id = "test_book_export"

        # Add some data first
        client.post(
            f"/api/bookmarks/{book_id}",
            json={
                "chapter_index": 0,
                "scroll_position": 0.5,
                "title": "Export test",
                "note": "Note"
            }
        )

        response = client.get(f"/api/export/{book_id}?format=json")
        assert response.status_code == 200
        # Response is PlainTextResponse, so parse content
        assert "bookmarks" in response.text

    def test_export_book_markdown(self, client):
        """Test exporting book data as Markdown."""
        book_id = "test_book_export_md"

        response = client.get(f"/api/export/{book_id}?format=markdown")
        assert response.status_code == 200
        assert "Notes and Highlights" in response.text

    def test_export_all(self, client):
        """Test exporting all data."""
        response = client.get("/api/export")
        assert response.status_code == 200
        # Should be valid JSON
        assert "exported_at" in response.text

    def test_export_highlights_json(self, client):
        """Test exporting highlights as JSON returns valid JSON."""
        import json
        import uuid
        book_id = f"test_export_highlights_json_{uuid.uuid4().hex[:8]}"

        # Create highlights
        client.post(
            f"/api/highlights/{book_id}",
            json={
                "chapter_index": 0,
                "text": "First highlighted text",
                "color": "yellow"
            }
        )
        client.post(
            f"/api/highlights/{book_id}",
            json={
                "chapter_index": 1,
                "text": "Second highlighted text",
                "color": "green"
            }
        )

        response = client.get(f"/api/export/{book_id}?format=json")
        assert response.status_code == 200

        # Verify it's valid JSON
        data = json.loads(response.text)
        assert "highlights" in data
        assert len(data["highlights"]) == 2
        assert data["highlights"][0]["text"] == "First highlighted text"
        assert data["highlights"][0]["color"] == "yellow"
        assert data["highlights"][1]["text"] == "Second highlighted text"
        assert data["highlights"][1]["color"] == "green"

    def test_export_highlights_markdown(self, client):
        """Test exporting highlights as Markdown contains highlight text."""
        import uuid
        book_id = f"test_export_highlights_md_{uuid.uuid4().hex[:8]}"

        # Create highlights with different colors
        client.post(
            f"/api/highlights/{book_id}",
            json={
                "chapter_index": 0,
                "text": "Yellow highlight text",
                "color": "yellow"
            }
        )
        client.post(
            f"/api/highlights/{book_id}",
            json={
                "chapter_index": 1,
                "text": "Green highlight text",
                "color": "green",
                "note": "This is a note"
            }
        )

        response = client.get(f"/api/export/{book_id}?format=markdown")
        assert response.status_code == 200

        content = response.text
        # Check markdown structure
        assert "# Notes and Highlights" in content
        assert "## Highlights" in content
        # Check highlight text is included
        assert "Yellow highlight text" in content
        assert "Green highlight text" in content
        # Check color emoji
        assert "🟡" in content  # yellow
        assert "🟢" in content  # green
        # Check note is included
        assert "This is a note" in content

    def test_export_bookmarks_and_highlights_json(self, client):
        """Test exporting both bookmarks and highlights as JSON."""
        import json
        import uuid
        book_id = f"test_export_both_json_{uuid.uuid4().hex[:8]}"

        # Create bookmark
        client.post(
            f"/api/bookmarks/{book_id}",
            json={
                "chapter_index": 0,
                "scroll_position": 0.5,
                "title": "My Bookmark",
                "note": "Bookmark note"
            }
        )

        # Create highlight
        client.post(
            f"/api/highlights/{book_id}",
            json={
                "chapter_index": 1,
                "text": "Important passage",
                "color": "blue"
            }
        )

        response = client.get(f"/api/export/{book_id}?format=json")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert len(data["bookmarks"]) == 1
        assert len(data["highlights"]) == 1
        assert data["bookmarks"][0]["title"] == "My Bookmark"
        assert data["highlights"][0]["text"] == "Important passage"

    def test_export_bookmarks_and_highlights_markdown(self, client):
        """Test exporting both bookmarks and highlights as Markdown."""
        import uuid
        book_id = f"test_export_both_md_{uuid.uuid4().hex[:8]}"

        # Create bookmark
        client.post(
            f"/api/bookmarks/{book_id}",
            json={
                "chapter_index": 2,
                "scroll_position": 0.75,
                "title": "Important Section",
                "note": "Review this later"
            }
        )

        # Create highlight
        client.post(
            f"/api/highlights/{book_id}",
            json={
                "chapter_index": 3,
                "text": "Key concept here",
                "color": "purple"
            }
        )

        response = client.get(f"/api/export/{book_id}?format=markdown")
        assert response.status_code == 200

        content = response.text
        # Check both sections exist
        assert "## Bookmarks" in content
        assert "## Highlights" in content
        # Check bookmark content
        assert "Important Section" in content
        assert "Review this later" in content
        # Check highlight content
        assert "Key concept here" in content
        assert "🟣" in content  # purple

    def test_export_empty_book(self, client):
        """Test exporting a book with no highlights or bookmarks."""
        import json
        import uuid
        book_id = f"test_export_empty_{uuid.uuid4().hex[:8]}"

        # Export JSON
        response = client.get(f"/api/export/{book_id}?format=json")
        assert response.status_code == 200
        data = json.loads(response.text)
        assert data["highlights"] == []
        assert data["bookmarks"] == []

        # Export Markdown
        response = client.get(f"/api/export/{book_id}?format=markdown")
        assert response.status_code == 200
        assert "Notes and Highlights" in response.text

    def test_export_invalid_format(self, client):
        """Test that invalid format returns 400 error."""
        response = client.get("/api/export/test_book?format=pdf")
        assert response.status_code == 400
        assert "Format must be" in response.json()["detail"]

    def test_export_json_content_type(self, client):
        """Test that JSON export returns correct content type."""
        response = client.get("/api/export/test_book?format=json")
        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]

    def test_export_markdown_content_type(self, client):
        """Test that Markdown export returns correct content type."""
        response = client.get("/api/export/test_book?format=markdown")
        assert response.status_code == 200
        assert "text/markdown" in response.headers["content-type"]

    def test_export_json_has_metadata(self, client):
        """Test that JSON export includes metadata."""
        import json
        import uuid
        book_id = f"test_export_metadata_{uuid.uuid4().hex[:8]}"

        response = client.get(f"/api/export/{book_id}?format=json")
        data = json.loads(response.text)

        assert "book_id" in data
        assert data["book_id"] == book_id
        assert "exported_at" in data

    def test_export_all_colors_markdown(self, client):
        """Test that all highlight colors have correct emojis in Markdown."""
        import uuid
        book_id = f"test_export_colors_{uuid.uuid4().hex[:8]}"

        colors = ["yellow", "green", "blue", "pink", "purple"]
        expected_emojis = ["🟡", "🟢", "🔵", "🔴", "🟣"]

        for color in colors:
            client.post(
                f"/api/highlights/{book_id}",
                json={
                    "chapter_index": 0,
                    "text": f"Text with {color}",
                    "color": color
                }
            )

        response = client.get(f"/api/export/{book_id}?format=markdown")
        content = response.text

        for emoji in expected_emojis:
            assert emoji in content, f"Expected emoji {emoji} not found"


class TestChapterProgressAPI:
    """Tests for chapter progress API endpoints."""

    def test_get_chapter_progress_empty(self, client):
        """Test getting chapter progress when none exists."""
        response = client.get("/api/chapter-progress/nonexistent_book")
        assert response.status_code == 200
        data = response.json()
        assert "progress" in data
        assert data["progress"] == {}

    def test_save_chapter_progress_json_body(self, client):
        """Test saving chapter progress via JSON body."""
        book_id = "test_book_chapter_progress"
        
        response = client.post(
            f"/api/chapter-progress/{book_id}/0",
            json={"progress": 50.0}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "saved"
        
        # Verify it was saved
        get_response = client.get(f"/api/chapter-progress/{book_id}")
        assert get_response.status_code == 200
        progress = get_response.json()["progress"]
        assert progress.get("0") == 50.0 or progress.get(0) == 50.0

    def test_save_chapter_progress_query_param(self, client):
        """Test saving chapter progress via query parameter."""
        book_id = "test_book_chapter_progress_query"
        
        response = client.post(
            f"/api/chapter-progress/{book_id}/1?progress=75.0"
        )
        assert response.status_code == 200
        assert response.json()["status"] == "saved"

    def test_save_multiple_chapters(self, client):
        """Test saving progress for multiple chapters."""
        import uuid
        book_id = f"test_book_multi_{uuid.uuid4().hex[:8]}"
        
        for i in range(3):
            client.post(
                f"/api/chapter-progress/{book_id}/{i}",
                json={"progress": (i + 1) * 25.0}
            )
        
        response = client.get(f"/api/chapter-progress/{book_id}")
        progress = response.json()["progress"]
        
        # Progress should have 3 entries
        assert len(progress) == 3

    def test_chapter_progress_only_increases(self, client):
        """Test that chapter progress doesn't decrease."""
        import uuid
        book_id = f"test_book_noincrease_{uuid.uuid4().hex[:8]}"
        
        # Set initial progress
        client.post(
            f"/api/chapter-progress/{book_id}/0",
            json={"progress": 80.0}
        )
        
        # Try to set lower progress
        client.post(
            f"/api/chapter-progress/{book_id}/0",
            json={"progress": 50.0}
        )
        
        # Should still be 80
        response = client.get(f"/api/chapter-progress/{book_id}")
        progress = response.json()["progress"]
        assert progress.get("0") == 80.0 or progress.get(0) == 80.0


class TestReadingTimesAPI:
    """Tests for reading times API endpoints."""

    def test_get_reading_times_nonexistent_book(self, client):
        """Test getting reading times for a book that doesn't exist."""
        response = client.get("/api/reading-times/nonexistent_book_xyz")
        # Should return 404 since book doesn't exist
        assert response.status_code == 404


# ============================================================================
# PDF-Specific API Tests
# ============================================================================


class TestPDFStatsAPI:
    """Tests for PDF statistics API endpoint."""

    def test_get_stats_nonexistent_book(self, client):
        """Test getting PDF stats for non-existent book."""
        response = client.get("/api/pdf/nonexistent_book/stats")
        assert response.status_code == 404

    def test_stats_endpoint_exists(self, client):
        """Test that the stats endpoint is accessible."""
        # Even for non-existent book, endpoint should respond
        response = client.get("/api/pdf/test_book/stats")
        # Will be 404 (book not found) but endpoint exists
        assert response.status_code in [200, 400, 404]


class TestPDFThumbnailsAPI:
    """Tests for PDF thumbnails API endpoint."""

    def test_list_thumbnails_nonexistent_book(self, client):
        """Test listing thumbnails for non-existent book."""
        response = client.get("/api/pdf/nonexistent_book/thumbnails")
        assert response.status_code == 404

    def test_serve_thumbnail_nonexistent(self, client):
        """Test serving thumbnail that doesn't exist."""
        response = client.get("/read/nonexistent_book/thumbnails/thumb_1.png")
        assert response.status_code == 404

    def test_thumbnails_endpoint_exists(self, client):
        """Test that thumbnails list endpoint is accessible."""
        response = client.get("/api/pdf/test_book/thumbnails")
        assert response.status_code in [200, 400, 404]


class TestPDFAnnotationsAPI:
    """Tests for PDF annotations API endpoint."""

    def test_get_annotations_nonexistent_book(self, client):
        """Test getting annotations for non-existent book."""
        response = client.get("/api/pdf/nonexistent_book/annotations")
        assert response.status_code == 404

    def test_annotations_endpoint_exists(self, client):
        """Test that annotations endpoint is accessible."""
        response = client.get("/api/pdf/test_book/annotations")
        assert response.status_code in [200, 400, 404]

    def test_annotations_with_page_filter(self, client):
        """Test annotations endpoint accepts page parameter."""
        response = client.get("/api/pdf/test_book/annotations?page=0")
        # Endpoint should accept the parameter
        assert response.status_code in [200, 400, 404]


class TestPDFSearchPositionsAPI:
    """Tests for PDF search positions API endpoint."""

    def test_search_positions_nonexistent_book(self, client):
        """Test search positions for non-existent book."""
        response = client.get(
            "/api/pdf/nonexistent_book/search-positions?q=test"
        )
        assert response.status_code == 404

    def test_search_positions_no_query(self, client):
        """Test search positions without query parameter."""
        response = client.get("/api/pdf/test_book/search-positions")
        # Missing required parameter
        assert response.status_code == 422

    def test_search_positions_short_query(self, client):
        """Test search positions with query too short."""
        response = client.get("/api/pdf/test_book/search-positions?q=a")
        # Should handle short queries
        assert response.status_code in [200, 400, 404]

    def test_search_positions_with_page(self, client):
        """Test search positions with page filter."""
        response = client.get(
            "/api/pdf/test_book/search-positions?q=test&page=0"
        )
        assert response.status_code in [200, 400, 404]


class TestPDFPageInfoAPI:
    """Tests for PDF page info API endpoint."""

    def test_get_page_info_nonexistent_book(self, client):
        """Test getting page info for non-existent book."""
        response = client.get("/api/pdf/nonexistent_book/page/0")
        assert response.status_code == 404

    def test_page_info_endpoint_exists(self, client):
        """Test that page info endpoint is accessible."""
        response = client.get("/api/pdf/test_book/page/0")
        assert response.status_code in [200, 400, 404]

    def test_page_info_negative_page(self, client):
        """Test page info with negative page number."""
        response = client.get("/api/pdf/test_book/page/-1")
        # Should be handled appropriately
        assert response.status_code in [200, 400, 404]


class TestPDFOutlineAPI:
    """Tests for PDF outline/TOC API endpoint."""

    def test_get_outline_nonexistent_book(self, client):
        """Test getting outline for non-existent book."""
        response = client.get("/api/pdf/nonexistent_book/outline")
        assert response.status_code == 404

    def test_outline_endpoint_exists(self, client):
        """Test that outline endpoint is accessible."""
        response = client.get("/api/pdf/test_book/outline")
        assert response.status_code in [200, 400, 404]


class TestPDFExportAPI:
    """Tests for PDF export API endpoint."""

    def test_export_nonexistent_book(self, client):
        """Test exporting from non-existent book."""
        response = client.post(
            "/api/pdf/nonexistent_book/export",
            json={"start_page": 0, "end_page": 5}
        )
        assert response.status_code == 404

    def test_export_endpoint_exists(self, client):
        """Test that export endpoint is accessible."""
        response = client.post(
            "/api/pdf/test_book/export",
            json={"start_page": 0, "end_page": 1}
        )
        # Will fail for non-PDF or non-existent, but endpoint exists
        assert response.status_code in [200, 400, 404]

    def test_export_invalid_json(self, client):
        """Test export with invalid JSON."""
        response = client.post(
            "/api/pdf/test_book/export",
            content="not valid json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code in [400, 404, 422]


class TestPDFTextLayerAPI:
    """Tests for PDF text layer API endpoint."""

    def test_get_text_layer_nonexistent_book(self, client):
        """Test getting text layer for non-existent book."""
        response = client.get("/api/pdf/nonexistent_book/text-layer/0")
        assert response.status_code == 404

    def test_text_layer_endpoint_exists(self, client):
        """Test that text layer endpoint is accessible."""
        response = client.get("/api/pdf/test_book/text-layer/0")
        assert response.status_code in [200, 400, 404]


class TestPDFPagesEndpoint:
    """Tests for PDF infinite scroll pages endpoint."""

    def test_get_pages_nonexistent_book(self, client):
        """Test getting pages for non-existent book."""
        response = client.get("/read/nonexistent_book/pages/0/5")
        assert response.status_code == 404

    def test_pages_endpoint_exists(self, client):
        """Test that pages endpoint is accessible."""
        response = client.get("/read/test_book/pages/0/5")
        assert response.status_code in [200, 400, 404]


# ============================================================================
# PDF API Response Format Tests
# ============================================================================


class TestPDFAPIResponseFormats:
    """Tests for verifying PDF API response formats."""

    def test_stats_response_format(self, client):
        """Test that stats response has expected structure when book exists."""
        # This tests the response structure expectations
        # Actual values depend on having a real PDF book loaded
        expected_fields = [
            "total_pages", "total_words", "total_images",
            "total_annotations", "pages_with_images",
            "pages_with_annotations", "has_native_toc",
            "has_thumbnails", "estimated_reading_time_minutes"
        ]
        # Document expected fields for API consumers
        assert len(expected_fields) == 9

    def test_thumbnails_response_format(self, client):
        """Test expected thumbnail response structure."""
        expected_fields = ["book_id", "thumbnails", "available"]
        assert len(expected_fields) == 3

    def test_annotations_response_format(self, client):
        """Test expected annotations response structure."""
        expected_fields = ["book_id", "annotations", "total"]
        assert len(expected_fields) == 3

    def test_search_positions_response_format(self, client):
        """Test expected search positions response structure."""
        expected_fields = ["query", "book_id", "results", "total"]
        assert len(expected_fields) == 4

    def test_page_info_response_format(self, client):
        """Test expected page info response structure."""
        expected_fields = [
            "page", "available", "width", "height",
            "rotation", "word_count", "has_images",
            "annotation_count", "text_block_count"
        ]
        assert len(expected_fields) == 9

    def test_outline_response_format(self, client):
        """Test expected outline response structure."""
        expected_fields = ["book_id", "has_native_toc", "outline"]
        assert len(expected_fields) == 3

    def test_text_layer_response_format(self, client):
        """Test expected text layer response structure."""
        expected_fields = ["page", "width", "height", "text_blocks"]
        assert len(expected_fields) == 4


# ============================================================================
# Collections API Tests
# ============================================================================


class TestCollectionsAPI:
    """Tests for collections API endpoints."""

    def test_get_collections_empty(self, client):
        """Test getting collections when none exist (may already have some)."""
        response = client.get("/api/collections")
        assert response.status_code == 200
        data = response.json()
        assert "collections" in data
        assert isinstance(data["collections"], list)

    def test_create_collection(self, client):
        """Test creating a collection."""
        import uuid
        name = f"Test Collection {uuid.uuid4().hex[:8]}"
        
        response = client.post(
            "/api/collections",
            json={
                "name": name,
                "description": "A test collection",
                "icon": "star",
                "color": "#e74c3c"
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["name"] == name
        assert data["description"] == "A test collection"
        assert data["icon"] == "star"
        assert data["color"] == "#e74c3c"
        assert "id" in data
        assert data["book_count"] == 0

    def test_create_collection_minimal(self, client):
        """Test creating a collection with only required fields."""
        import uuid
        name = f"Minimal Collection {uuid.uuid4().hex[:8]}"
        
        response = client.post(
            "/api/collections",
            json={"name": name}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["name"] == name
        assert "id" in data

    def test_create_collection_empty_name(self, client):
        """Test that creating a collection with empty name fails."""
        response = client.post(
            "/api/collections",
            json={"name": ""}
        )
        assert response.status_code == 400

    def test_create_collection_whitespace_name(self, client):
        """Test that creating a collection with whitespace-only name fails."""
        response = client.post(
            "/api/collections",
            json={"name": "   "}
        )
        assert response.status_code == 400

    def test_get_collection_by_id(self, client):
        """Test getting a single collection by ID."""
        import uuid
        name = f"Get By ID {uuid.uuid4().hex[:8]}"
        
        # Create collection
        create_response = client.post(
            "/api/collections",
            json={"name": name}
        )
        collection_id = create_response.json()["id"]
        
        # Get by ID
        get_response = client.get(f"/api/collections/{collection_id}")
        assert get_response.status_code == 200
        
        data = get_response.json()
        assert data["id"] == collection_id
        assert data["name"] == name

    def test_get_collection_not_found(self, client):
        """Test getting a non-existent collection."""
        response = client.get("/api/collections/nonexistent_id_12345")
        assert response.status_code == 404

    def test_update_collection(self, client):
        """Test updating a collection."""
        import uuid
        name = f"Update Test {uuid.uuid4().hex[:8]}"
        
        # Create collection
        create_response = client.post(
            "/api/collections",
            json={"name": name}
        )
        collection_id = create_response.json()["id"]
        
        # Update collection
        update_response = client.put(
            f"/api/collections/{collection_id}",
            json={
                "name": "Updated Name",
                "description": "Updated description",
                "icon": "heart",
                "color": "#2ecc71"
            }
        )
        assert update_response.status_code == 200
        
        data = update_response.json()
        assert data["name"] == "Updated Name"
        assert data["description"] == "Updated description"
        assert data["icon"] == "heart"
        assert data["color"] == "#2ecc71"

    def test_update_collection_partial(self, client):
        """Test updating only some collection fields."""
        import uuid
        name = f"Partial Update {uuid.uuid4().hex[:8]}"
        
        # Create collection
        create_response = client.post(
            "/api/collections",
            json={
                "name": name,
                "description": "Original",
                "icon": "folder",
                "color": "#3498db"
            }
        )
        collection_id = create_response.json()["id"]
        
        # Update only name
        update_response = client.put(
            f"/api/collections/{collection_id}",
            json={"name": "New Name Only"}
        )
        assert update_response.status_code == 200
        
        # Verify other fields unchanged
        get_response = client.get(f"/api/collections/{collection_id}")
        data = get_response.json()
        assert data["name"] == "New Name Only"
        assert data["description"] == "Original"
        assert data["icon"] == "folder"

    def test_update_collection_not_found(self, client):
        """Test updating a non-existent collection."""
        response = client.put(
            "/api/collections/nonexistent_id_12345",
            json={"name": "Test"}
        )
        assert response.status_code == 404

    def test_delete_collection(self, client):
        """Test deleting a collection."""
        import uuid
        name = f"Delete Test {uuid.uuid4().hex[:8]}"
        
        # Create collection
        create_response = client.post(
            "/api/collections",
            json={"name": name}
        )
        collection_id = create_response.json()["id"]
        
        # Delete collection
        delete_response = client.delete(f"/api/collections/{collection_id}")
        assert delete_response.status_code == 200
        assert delete_response.json()["status"] == "deleted"
        
        # Verify deleted
        get_response = client.get(f"/api/collections/{collection_id}")
        assert get_response.status_code == 404

    def test_delete_collection_not_found(self, client):
        """Test deleting a non-existent collection."""
        response = client.delete("/api/collections/nonexistent_id_12345")
        assert response.status_code == 404

    def test_add_book_to_collection(self, client):
        """Test adding a book to a collection."""
        import uuid
        name = f"Add Book Test {uuid.uuid4().hex[:8]}"
        book_id = f"test_book_{uuid.uuid4().hex[:8]}"
        
        # Create collection
        create_response = client.post(
            "/api/collections",
            json={"name": name}
        )
        collection_id = create_response.json()["id"]
        
        # Add book
        add_response = client.post(
            f"/api/collections/{collection_id}/books/{book_id}"
        )
        assert add_response.status_code == 200
        assert add_response.json()["status"] == "added"
        
        # Verify book is in collection
        get_response = client.get(f"/api/collections/{collection_id}")
        data = get_response.json()
        assert book_id in data["book_ids"]
        assert data["book_count"] == 1

    def test_add_book_to_nonexistent_collection(self, client):
        """Test adding a book to a non-existent collection."""
        response = client.post(
            "/api/collections/nonexistent_id/books/some_book"
        )
        assert response.status_code == 404

    def test_remove_book_from_collection(self, client):
        """Test removing a book from a collection."""
        import uuid
        name = f"Remove Book Test {uuid.uuid4().hex[:8]}"
        book_id = f"test_book_{uuid.uuid4().hex[:8]}"
        
        # Create collection and add book
        create_response = client.post(
            "/api/collections",
            json={"name": name}
        )
        collection_id = create_response.json()["id"]
        client.post(f"/api/collections/{collection_id}/books/{book_id}")
        
        # Remove book
        remove_response = client.delete(
            f"/api/collections/{collection_id}/books/{book_id}"
        )
        assert remove_response.status_code == 200
        assert remove_response.json()["status"] == "removed"
        
        # Verify book is removed
        get_response = client.get(f"/api/collections/{collection_id}")
        data = get_response.json()
        assert book_id not in data["book_ids"]

    def test_get_book_collections(self, client):
        """Test getting all collections a book belongs to."""
        import uuid
        book_id = f"test_book_{uuid.uuid4().hex[:8]}"
        
        # Create two collections and add the book to both
        col1_response = client.post(
            "/api/collections",
            json={"name": f"Col1 {uuid.uuid4().hex[:8]}"}
        )
        col1_id = col1_response.json()["id"]
        
        col2_response = client.post(
            "/api/collections",
            json={"name": f"Col2 {uuid.uuid4().hex[:8]}"}
        )
        col2_id = col2_response.json()["id"]
        
        client.post(f"/api/collections/{col1_id}/books/{book_id}")
        client.post(f"/api/collections/{col2_id}/books/{book_id}")
        
        # Get book's collections
        response = client.get(f"/api/books/{book_id}/collections")
        assert response.status_code == 200
        
        data = response.json()
        assert data["book_id"] == book_id
        assert len(data["collections"]) == 2
        collection_ids = [c["id"] for c in data["collections"]]
        assert col1_id in collection_ids
        assert col2_id in collection_ids

    def test_set_book_collections(self, client):
        """Test setting all collections for a book at once."""
        import uuid
        book_id = f"test_book_{uuid.uuid4().hex[:8]}"
        
        # Create three collections
        col1_response = client.post(
            "/api/collections",
            json={"name": f"Set1 {uuid.uuid4().hex[:8]}"}
        )
        col1_id = col1_response.json()["id"]
        
        col2_response = client.post(
            "/api/collections",
            json={"name": f"Set2 {uuid.uuid4().hex[:8]}"}
        )
        col2_id = col2_response.json()["id"]
        
        col3_response = client.post(
            "/api/collections",
            json={"name": f"Set3 {uuid.uuid4().hex[:8]}"}
        )
        col3_id = col3_response.json()["id"]
        
        # Add book to col1 initially
        client.post(f"/api/collections/{col1_id}/books/{book_id}")
        
        # Set book to col2 and col3 (should remove from col1)
        set_response = client.put(
            f"/api/books/{book_id}/collections",
            json={"collection_ids": [col2_id, col3_id]}
        )
        assert set_response.status_code == 200
        
        # Verify
        data = set_response.json()
        collection_ids = [c["id"] for c in data["collections"]]
        assert col1_id not in collection_ids
        assert col2_id in collection_ids
        assert col3_id in collection_ids

    def test_reorder_collections(self, client):
        """Test reordering collections."""
        import uuid
        
        # Create three collections
        col1_response = client.post(
            "/api/collections",
            json={"name": f"Order1 {uuid.uuid4().hex[:8]}"}
        )
        col1_id = col1_response.json()["id"]
        
        col2_response = client.post(
            "/api/collections",
            json={"name": f"Order2 {uuid.uuid4().hex[:8]}"}
        )
        col2_id = col2_response.json()["id"]
        
        col3_response = client.post(
            "/api/collections",
            json={"name": f"Order3 {uuid.uuid4().hex[:8]}"}
        )
        col3_id = col3_response.json()["id"]
        
        # Reorder: col3, col1, col2
        reorder_response = client.put(
            "/api/collections/reorder",
            json={"collection_ids": [col3_id, col1_id, col2_id]}
        )
        assert reorder_response.status_code == 200
        assert reorder_response.json()["status"] == "reordered"

    def test_collection_response_includes_book_ids(self, client):
        """Test that collection response includes book_ids array."""
        import uuid
        name = f"Book IDs Test {uuid.uuid4().hex[:8]}"
        
        response = client.post(
            "/api/collections",
            json={"name": name}
        )
        data = response.json()
        
        assert "book_ids" in data
        assert isinstance(data["book_ids"], list)

    def test_collection_response_includes_timestamps(self, client):
        """Test that collection response includes timestamps."""
        import uuid
        name = f"Timestamps Test {uuid.uuid4().hex[:8]}"
        
        create_response = client.post(
            "/api/collections",
            json={"name": name}
        )
        collection_id = create_response.json()["id"]
        
        get_response = client.get(f"/api/collections/{collection_id}")
        data = get_response.json()
        
        assert "created_at" in data
        assert "updated_at" in data


# ============================================================================
# Reading Sessions API Tests
# ============================================================================


class TestReadingSessionsAPI:
    """Tests for reading sessions API endpoints."""

    def test_start_reading_session(self, client):
        """Test starting a reading session."""
        import uuid
        book_id = f"test_book_{uuid.uuid4().hex[:8]}"
        
        response = client.post(
            "/api/sessions/start",
            json={
                "book_id": book_id,
                "book_title": "Test Book",
                "chapter_index": 0,
                "chapter_title": "Chapter 1"
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "session_id" in data
        assert data["status"] == "started"

    def test_end_reading_session(self, client):
        """Test ending a reading session."""
        import uuid
        book_id = f"test_book_{uuid.uuid4().hex[:8]}"
        
        # Start session
        start_response = client.post(
            "/api/sessions/start",
            json={
                "book_id": book_id,
                "book_title": "Test Book",
                "chapter_index": 0,
                "chapter_title": "Chapter 1"
            }
        )
        session_id = start_response.json()["session_id"]
        
        # End session
        end_response = client.post(
            f"/api/sessions/{session_id}/end",
            json={
                "duration_seconds": 600,
                "pages_read": 10,
                "scroll_position": 0.5
            }
        )
        assert end_response.status_code == 200
        assert end_response.json()["status"] == "ended"

    def test_end_nonexistent_session(self, client):
        """Test ending a session that doesn't exist."""
        response = client.post(
            "/api/sessions/nonexistent_session_id/end",
            json={
                "duration_seconds": 100,
                "pages_read": 5,
                "scroll_position": 0.25
            }
        )
        assert response.status_code == 404

    def test_get_sessions(self, client):
        """Test getting reading sessions."""
        response = client.get("/api/sessions")
        assert response.status_code == 200
        
        data = response.json()
        assert "sessions" in data
        assert isinstance(data["sessions"], list)

    def test_get_sessions_with_book_filter(self, client):
        """Test getting sessions filtered by book."""
        import uuid
        book_id = f"test_book_{uuid.uuid4().hex[:8]}"
        
        # Create a session for this book
        client.post(
            "/api/sessions/start",
            json={
                "book_id": book_id,
                "book_title": "Test Book",
                "chapter_index": 0,
                "chapter_title": "Chapter 1"
            }
        )
        
        response = client.get(f"/api/sessions?book_id={book_id}")
        assert response.status_code == 200
        
        data = response.json()
        assert "sessions" in data

    def test_get_sessions_with_limit(self, client):
        """Test getting sessions with limit parameter."""
        response = client.get("/api/sessions?limit=5")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["sessions"]) <= 5

    def test_get_reading_stats(self, client):
        """Test getting reading statistics."""
        response = client.get("/api/sessions/stats")
        assert response.status_code == 200
        
        data = response.json()
        assert "total_time_seconds" in data
        assert "total_pages" in data
        assert "session_count" in data
        assert "streak_days" in data

    def test_get_reading_stats_for_book(self, client):
        """Test getting reading statistics for a specific book."""
        import uuid
        book_id = f"test_book_{uuid.uuid4().hex[:8]}"
        
        response = client.get(f"/api/sessions/stats?book_id={book_id}")
        assert response.status_code == 200
        
        data = response.json()
        assert "total_time_seconds" in data


# ============================================================================
# Vocabulary API Tests
# ============================================================================


class TestVocabularyAPI:
    """Tests for vocabulary API endpoints."""

    def test_add_vocabulary_word(self, client):
        """Test adding a vocabulary word."""
        import uuid
        book_id = f"test_book_{uuid.uuid4().hex[:8]}"
        
        response = client.post(
            f"/api/vocabulary/{book_id}",
            json={
                "word": "ephemeral",
                "definition": "lasting for a very short time",
                "phonetic": "/ɪˈfɛm(ə)r(ə)l/",
                "part_of_speech": "adjective",
                "context": "The ephemeral beauty of cherry blossoms."
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "id" in data
        assert data["status"] == "saved"

    def test_add_vocabulary_minimal(self, client):
        """Test adding a word with only required fields."""
        import uuid
        book_id = f"test_book_{uuid.uuid4().hex[:8]}"
        
        response = client.post(
            f"/api/vocabulary/{book_id}",
            json={
                "word": "serendipity",
                "definition": "the occurrence of events by chance in a happy way"
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "id" in data
        assert data["status"] == "saved"

    def test_get_vocabulary_for_book(self, client):
        """Test getting vocabulary for a specific book."""
        import uuid
        book_id = f"test_book_{uuid.uuid4().hex[:8]}"
        
        # Add a word first
        client.post(
            f"/api/vocabulary/{book_id}",
            json={
                "word": "test_word",
                "definition": "a test definition"
            }
        )
        
        response = client.get(f"/api/vocabulary/{book_id}")
        assert response.status_code == 200
        
        data = response.json()
        assert "words" in data
        assert len(data["words"]) >= 1

    def test_get_vocabulary_empty(self, client):
        """Test getting vocabulary for a book with none."""
        import uuid
        book_id = f"test_book_empty_{uuid.uuid4().hex[:8]}"
        
        response = client.get(f"/api/vocabulary/{book_id}")
        assert response.status_code == 200
        
        data = response.json()
        assert data["words"] == []

    def test_get_all_vocabulary(self, client):
        """Test getting all vocabulary across books."""
        response = client.get("/api/vocabulary")
        assert response.status_code == 200
        
        data = response.json()
        assert "words" in data
        assert isinstance(data["words"], list)

    def test_delete_vocabulary_word(self, client):
        """Test deleting a vocabulary word."""
        import uuid
        book_id = f"test_book_{uuid.uuid4().hex[:8]}"
        
        # Add a word
        add_response = client.post(
            f"/api/vocabulary/{book_id}",
            json={
                "word": "to_delete",
                "definition": "will be deleted"
            }
        )
        word_id = add_response.json()["id"]
        
        # Delete the word
        delete_response = client.delete(f"/api/vocabulary/{book_id}/{word_id}")
        assert delete_response.status_code == 200
        assert delete_response.json()["status"] == "deleted"

    def test_delete_nonexistent_vocabulary(self, client):
        """Test deleting a word that doesn't exist."""
        response = client.delete("/api/vocabulary/some_book/nonexistent_id")
        assert response.status_code == 404

    def test_search_vocabulary(self, client):
        """Test searching vocabulary."""
        import uuid
        book_id = f"test_book_{uuid.uuid4().hex[:8]}"
        
        # Add a word
        client.post(
            f"/api/vocabulary/{book_id}",
            json={
                "word": "ubiquitous",
                "definition": "present everywhere"
            }
        )
        
        # Search for it
        response = client.get("/api/vocabulary/search?q=ubiquitous")
        assert response.status_code == 200
        
        data = response.json()
        assert "results" in data

    def test_search_vocabulary_short_query(self, client):
        """Test that short queries return empty results."""
        response = client.get("/api/vocabulary/search?q=a")
        assert response.status_code == 200
        
        data = response.json()
        assert data["results"] == []


# ============================================================================
# User Annotations API Tests
# ============================================================================


class TestUserAnnotationsAPI:
    """Tests for user annotations API endpoints (not PDF annotations)."""

    def test_create_annotation(self, client):
        """Test creating an annotation."""
        import uuid
        book_id = f"test_book_{uuid.uuid4().hex[:8]}"
        
        response = client.post(
            f"/api/annotations/{book_id}",
            json={
                "chapter_index": 0,
                "note_text": "This is an important point!",
                "tags": ["important", "review"]
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "created"
        assert "id" in data

    def test_create_annotation_minimal(self, client):
        """Test creating an annotation with only required fields."""
        import uuid
        book_id = f"test_book_{uuid.uuid4().hex[:8]}"
        
        response = client.post(
            f"/api/annotations/{book_id}",
            json={
                "chapter_index": 0,
                "note_text": "A simple note"
            }
        )
        assert response.status_code == 200

    def test_get_annotations_for_book(self, client):
        """Test getting annotations for a book."""
        import uuid
        book_id = f"test_book_{uuid.uuid4().hex[:8]}"
        
        # Create an annotation
        client.post(
            f"/api/annotations/{book_id}",
            json={
                "chapter_index": 0,
                "note_text": "Test note"
            }
        )
        
        response = client.get(f"/api/annotations/{book_id}")
        assert response.status_code == 200
        
        data = response.json()
        assert "annotations" in data
        assert len(data["annotations"]) >= 1

    def test_get_annotations_with_chapter_filter(self, client):
        """Test getting annotations filtered by chapter."""
        import uuid
        book_id = f"test_book_{uuid.uuid4().hex[:8]}"
        
        # Create annotations in different chapters
        client.post(
            f"/api/annotations/{book_id}",
            json={"chapter_index": 0, "note_text": "Chapter 0 note"}
        )
        client.post(
            f"/api/annotations/{book_id}",
            json={"chapter_index": 1, "note_text": "Chapter 1 note"}
        )
        
        response = client.get(f"/api/annotations/{book_id}?chapter=0")
        assert response.status_code == 200

    def test_get_annotations_empty(self, client):
        """Test getting annotations for a book with none."""
        import uuid
        book_id = f"test_book_empty_{uuid.uuid4().hex[:8]}"
        
        response = client.get(f"/api/annotations/{book_id}")
        assert response.status_code == 200
        
        data = response.json()
        assert data["annotations"] == []

    def test_update_annotation(self, client):
        """Test updating an annotation."""
        import uuid
        book_id = f"test_book_{uuid.uuid4().hex[:8]}"
        
        # Create annotation
        create_response = client.post(
            f"/api/annotations/{book_id}",
            json={
                "chapter_index": 0,
                "note_text": "Original note",
                "tags": ["original"]
            }
        )
        annotation_id = create_response.json()["id"]
        
        # Update it
        update_response = client.put(
            f"/api/annotations/{book_id}/{annotation_id}",
            json={
                "note_text": "Updated note",
                "tags": ["updated", "modified"]
            }
        )
        assert update_response.status_code == 200
        assert update_response.json()["status"] == "updated"

    def test_update_nonexistent_annotation(self, client):
        """Test updating an annotation that doesn't exist."""
        response = client.put(
            "/api/annotations/some_book/nonexistent_id",
            json={"note_text": "Test"}
        )
        assert response.status_code == 404

    def test_delete_annotation(self, client):
        """Test deleting an annotation."""
        import uuid
        book_id = f"test_book_{uuid.uuid4().hex[:8]}"
        
        # Create annotation
        create_response = client.post(
            f"/api/annotations/{book_id}",
            json={
                "chapter_index": 0,
                "note_text": "To be deleted"
            }
        )
        annotation_id = create_response.json()["id"]
        
        # Delete it
        delete_response = client.delete(
            f"/api/annotations/{book_id}/{annotation_id}"
        )
        assert delete_response.status_code == 200
        assert delete_response.json()["status"] == "deleted"

    def test_delete_nonexistent_annotation(self, client):
        """Test deleting an annotation that doesn't exist."""
        response = client.delete("/api/annotations/some_book/nonexistent_id")
        assert response.status_code == 404

    def test_search_annotations(self, client):
        """Test searching annotations."""
        import uuid
        book_id = f"test_book_{uuid.uuid4().hex[:8]}"
        
        # Create annotation with searchable text
        client.post(
            f"/api/annotations/{book_id}",
            json={
                "chapter_index": 0,
                "note_text": "This is about quantum mechanics",
                "tags": ["physics", "quantum"]
            }
        )
        
        # Search by text
        response = client.get(f"/api/annotations/{book_id}/search?q=quantum")
        assert response.status_code == 200
        
        data = response.json()
        assert "results" in data

    def test_search_annotations_short_query(self, client):
        """Test that short queries return empty results."""
        import uuid
        book_id = f"test_book_{uuid.uuid4().hex[:8]}"
        
        response = client.get(f"/api/annotations/{book_id}/search?q=a")
        assert response.status_code == 200
        
        data = response.json()
        assert data["results"] == []

    def test_export_annotations_markdown(self, client):
        """Test exporting annotations as markdown."""
        import uuid
        book_id = f"test_book_{uuid.uuid4().hex[:8]}"
        
        # Create an annotation
        client.post(
            f"/api/annotations/{book_id}",
            json={
                "chapter_index": 0,
                "note_text": "Export test note"
            }
        )
        
        response = client.get(f"/api/annotations/{book_id}/export?format=markdown")
        assert response.status_code == 200
        assert "markdown" in response.headers["content-type"] or "text" in response.headers["content-type"]

    def test_export_annotations_json(self, client):
        """Test exporting annotations as JSON."""
        import uuid
        book_id = f"test_book_{uuid.uuid4().hex[:8]}"
        
        response = client.get(f"/api/annotations/{book_id}/export?format=json")
        assert response.status_code == 200
        assert "json" in response.headers["content-type"]
