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
        assert "library" in response.text.lower() or "reader" in response.text.lower()


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
