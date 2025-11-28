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

