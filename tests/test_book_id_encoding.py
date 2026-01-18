from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import sys
import os
import pytest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import app

@pytest.fixture
def client():
    return TestClient(app)

def test_book_id_decoding(client):
    """
    Test that book IDs with special characters (like apostrophes) are correctly
    decoded by FastAPI before being passed to load_book_cached.
    """
    decoded_id = "Japan's Book"

    # We patch the function in 'server' module because that's where it's used/defined
    with patch("server.load_book_cached") as mock_load:
        # Structure the mock book to avoid attribute errors
        mock_book = MagicMock()
        mock_book.spine = [MagicMock()] # Needs at least one chapter
        mock_book.is_pdf = False
        mock_load.return_value = mock_book

        # Make the request
        # TestClient automatically encodes URL parameters
        response = client.get(f"/read/{decoded_id}/0")
        
        assert response.status_code == 200
        
        # Verify that the server called load_book_cached with the DECODED string
        # This confirms that if the client sends encoded "Japan%27s%20Book",
        # the server resolves it to "Japan's Book" correctly.
        mock_load.assert_called_with(decoded_id)
