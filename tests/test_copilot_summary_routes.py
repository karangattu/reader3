"""Tests for Copilot SDK-powered summary routes and reader controls."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import server
from reader3 import (
    Book,
    BookMetadata,
    ChapterContent,
    TOCEntry,
    save_to_pickle,
)
from server import app


def create_test_book(
    book_id: str,
    title: str,
    *,
    chapters: int = 1,
    is_pdf: bool = False,
    include_pdf_source: bool = False,
    include_inline_image: bool = False,
) -> Path:
    """Create a minimal processed book in the isolated test library."""
    added_at = datetime.now().isoformat()
    book_dir = Path(server.BOOKS_DIR) / book_id
    book_dir.mkdir(parents=True, exist_ok=True)

    spine = []
    toc = []
    images = {}

    if include_inline_image:
        image_dir = book_dir / "images"
        image_dir.mkdir(parents=True, exist_ok=True)
        (image_dir / "diagram.png").write_bytes(b"fake-png")
        images["diagram.png"] = "images/diagram.png"

    for index in range(chapters):
        href = f"chapter-{index}.html"
        if is_pdf:
            content = (
                '<div class="pdf-page-image-container">'
                f'<img class="pdf-page-image" '
                f'src="images/page-{index}.png" '
                f'alt="Page {index + 1}">'
                "</div>"
            )
        elif include_inline_image and index == 0:
            content = (
                f"<p>{title} chapter {index + 1}</p>"
                '<figure><img src="images/diagram.png" '
                'alt="Important diagram"></figure>'
            )
        else:
            content = f"<p>{title} chapter {index + 1}</p>"

        chapter_title = (
            f"Chapter {index + 1}" if not is_pdf else f"Page {index + 1}"
        )

        spine.append(
            ChapterContent(
                id=f"chapter-{index}",
                href=href,
                title=chapter_title,
                content=content,
                text=f"{title} chapter {index + 1}",
                order=index,
            )
        )
        toc.append(
            TOCEntry(
                title=chapter_title,
                href=href,
                file_href=href,
                anchor="",
            )
        )

    source_ext = ".pdf" if is_pdf else ".epub"
    book = Book(
        metadata=BookMetadata(
            title=title,
            language="en",
            authors=["Test Author"],
        ),
        spine=spine,
        toc=toc,
        images=images,
        source_file=f"{title}{source_ext}",
        processed_at=added_at,
        added_at=added_at,
        is_pdf=is_pdf,
        pdf_source_path="source.pdf" if include_pdf_source else None,
    )
    save_to_pickle(book, str(book_dir))

    if include_pdf_source:
        (book_dir / "source.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")

    server.load_book_cached.cache_clear()
    server.load_book_metadata.cache_clear()
    server.get_cached_reading_times.cache_clear()
    return book_dir


@pytest.fixture
def client():
    return TestClient(app)


class _FakeCopilotSummaryService:
    def __init__(self):
        self.text_calls = []
        self.file_calls = []
        self.blob_calls = []

    async def get_status(self):
        return {
            "available": True,
            "authenticated": True,
            "model": "gpt-4.1",
            "supports_vision": True,
            "error": None,
        }

    async def summarize_text(self, text, **kwargs):
        self.text_calls.append({"text": text, **kwargs})
        return "summary text"

    async def summarize_image_file(self, image_path, **kwargs):
        self.file_calls.append({"image_path": image_path, **kwargs})
        return "image file summary"

    async def summarize_image_blob(self, image_bytes, **kwargs):
        self.blob_calls.append({"image_bytes": image_bytes, **kwargs})
        return "image blob summary"


class TestCopilotSummaryRoutes:
    def test_status_endpoint_returns_summary_service_status(
        self,
        client,
        monkeypatch,
    ):
        fake_service = _FakeCopilotSummaryService()
        monkeypatch.setattr(
            server,
            "copilot_summary_service",
            fake_service,
            raising=False,
        )

        response = client.get("/api/copilot/status")

        assert response.status_code == 200
        assert response.json()["available"] is True
        assert response.json()["supports_vision"] is True

    def test_text_summary_endpoint_summarizes_selected_text(
        self,
        client,
        monkeypatch,
    ):
        fake_service = _FakeCopilotSummaryService()
        monkeypatch.setattr(
            server,
            "copilot_summary_service",
            fake_service,
            raising=False,
        )

        response = client.post(
            "/api/copilot/summarize/text",
            json={
                "book_id": "selection-summary-book",
                "source": "selection",
                "selected_text": "Summarize this selected passage.",
                "chapter_index": 0,
            },
        )

        assert response.status_code == 200
        assert response.json()["summary"] == "summary text"
        assert (
            fake_service.text_calls[0]["text"]
            == "Summarize this selected passage."
        )
        assert fake_service.text_calls[0]["scope"] == "selection"

    def test_text_summary_endpoint_summarizes_chapter_text(
        self,
        client,
        monkeypatch,
    ):
        fake_service = _FakeCopilotSummaryService()
        monkeypatch.setattr(
            server,
            "copilot_summary_service",
            fake_service,
            raising=False,
        )
        book_id = f"chapter_summary_{uuid.uuid4().hex[:8]}"
        create_test_book(book_id, "Chapter Summary Book", chapters=2)

        response = client.post(
            "/api/copilot/summarize/text",
            json={
                "book_id": book_id,
                "source": "chapter",
                "chapter_index": 1,
            },
        )

        assert response.status_code == 200
        assert response.json()["summary"] == "summary text"
        assert (
            fake_service.text_calls[0]["text"]
            == "Chapter Summary Book chapter 2"
        )
        assert fake_service.text_calls[0]["scope"] == "chapter"
        assert fake_service.text_calls[0]["chapter_title"] == "Chapter 2"

    def test_text_summary_endpoint_rejects_empty_selected_text(
        self,
        client,
        monkeypatch,
    ):
        fake_service = _FakeCopilotSummaryService()
        monkeypatch.setattr(
            server,
            "copilot_summary_service",
            fake_service,
            raising=False,
        )

        response = client.post(
            "/api/copilot/summarize/text",
            json={
                "book_id": "selection-summary-book",
                "source": "selection",
                "selected_text": "   ",
                "chapter_index": 0,
            },
        )

        assert response.status_code == 400
        assert "selected text" in response.json()["detail"].lower()

    def test_image_summary_endpoint_summarizes_epub_inline_image(
        self,
        client,
        monkeypatch,
    ):
        fake_service = _FakeCopilotSummaryService()
        monkeypatch.setattr(
            server,
            "copilot_summary_service",
            fake_service,
            raising=False,
        )
        book_id = f"epub_image_summary_{uuid.uuid4().hex[:8]}"
        create_test_book(book_id, "EPUB Image Book", include_inline_image=True)

        response = client.post(
            "/api/copilot/summarize/image",
            json={
                "book_id": book_id,
                "source": "epub",
                "image_name": "diagram.png",
                "chapter_index": 0,
            },
        )

        assert response.status_code == 200
        assert response.json()["summary"] == "image file summary"
        assert fake_service.file_calls[0]["image_path"].endswith("diagram.png")
        assert fake_service.file_calls[0]["chapter_title"] == "Chapter 1"

    def test_image_summary_endpoint_summarizes_pdf_page_blob(
        self,
        client,
        monkeypatch,
    ):
        fake_service = _FakeCopilotSummaryService()
        monkeypatch.setattr(
            server,
            "copilot_summary_service",
            fake_service,
            raising=False,
        )
        monkeypatch.setattr(
            server,
            "_render_pdf_page_image_bytes",
            lambda *args, **kwargs: b"png-bytes",
        )
        book_id = f"pdf_image_summary_{uuid.uuid4().hex[:8]}"
        create_test_book(
            book_id,
            "PDF Image Book",
            is_pdf=True,
            include_pdf_source=True,
        )

        response = client.post(
            "/api/copilot/summarize/image",
            json={
                "book_id": book_id,
                "source": "pdf",
                "page_index": 0,
            },
        )

        assert response.status_code == 200
        assert response.json()["summary"] == "image blob summary"
        assert fake_service.blob_calls[0]["image_bytes"] == b"png-bytes"
        assert fake_service.blob_calls[0]["mime_type"] == "image/png"
        assert fake_service.blob_calls[0]["display_name"].endswith(
            "page-1.png"
        )


class TestCopilotSummaryReaderUi:
    def test_reader_page_has_copilot_summary_controls_for_epub(self, client):
        book_id = f"epub_ui_summary_{uuid.uuid4().hex[:8]}"
        create_test_book(book_id, "EPUB UI Book", include_inline_image=True)

        response = client.get(f"/read/{book_id}/0")

        assert response.status_code == 200
        assert 'summarizeSelectedText()' in response.text
        assert 'summarizeCurrentChapter()' in response.text
        assert 'copilot-summary-panel' in response.text
        assert 'copilot-status-banner' in response.text
        assert 'fetchCopilotStatus()' in response.text
        assert 'openCopilotHelpDialog()' in response.text

    def test_reader_page_has_copilot_summary_controls_for_pdf(self, client):
        book_id = f"pdf_ui_summary_{uuid.uuid4().hex[:8]}"
        create_test_book(
            book_id,
            "PDF UI Book",
            is_pdf=True,
            include_pdf_source=True,
        )

        response = client.get(f"/read/{book_id}/0")

        assert response.status_code == 200
        assert 'summarizePdfPageImage' in response.text
        assert 'Summarize Image' in response.text

    def test_reader_template_supports_inline_image_summary_controls(self):
        template_path = (
            Path(__file__).parent.parent / "templates" / "reader.html"
        )
        content = template_path.read_text(encoding="utf-8")

        assert 'enhanceInlineImageSummaryControls' in content
        assert 'summarizeInlineImage' in content
        assert 'Copilot status: Checking sign-in' in content
        assert (
            'Reader3 uses the local GitHub Copilot sign-in on this machine.'
            in content
        )
        assert 'Type /login' in content
        assert 'Refresh status' in content
