from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from reader3 import Book, BookMetadata, ChapterContent
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
    mock_book = Book(
        metadata=BookMetadata(
            title="Test Book",
            language="en",
            authors=["Test Author"],
        ),
        spine=[
            ChapterContent(
                id="chapter-1",
                href="chapter-1.xhtml",
                title="Chapter 1",
                content="<p>Chapter content</p>",
                text="Chapter content",
                order=0,
            )
        ],
        toc=[],
        images={},
        source_file="test.epub",
        processed_at="2026-04-28T00:00:00",
    )

    # Patch where the route looks up the loader.
    with patch("server.load_book_cached") as mock_load:
        mock_load.return_value = mock_book

        # Make the request
        # TestClient automatically encodes URL parameters
        response = client.get(f"/read/{decoded_id}/0")

        assert response.status_code == 200

        # Verify the handler receives the decoded book id.
        # This confirms that if the client sends encoded "Japan%27s%20Book",
        # the server resolves it to "Japan's Book" correctly.
        mock_load.assert_called_with(decoded_id)
