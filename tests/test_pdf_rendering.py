"""Tests for PDF display rendering, copy caches, and reprocessing."""

import shutil
import uuid
from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient

import server
from reader3.api import deps
from reader3.services.library import (
    _pdf_page_image_settings,
    process_pdf,
    render_pdf_page_image,
    save_to_json,
)
from server import app


@pytest.fixture
def client():
    return TestClient(app)


def _write_test_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Reader3 PDF rendering test")
    doc.save(str(path))
    doc.close()


@pytest.fixture
def processed_pdf_book(tmp_path):
    """Create a real one-page PDF book in the isolated test library."""
    book_id = f"pdf_render_{uuid.uuid4().hex[:8]}_data"
    book_dir = Path(server.BOOKS_DIR) / book_id
    pdf_path = tmp_path / "source.pdf"
    _write_test_pdf(pdf_path)

    book = process_pdf(
        str(pdf_path),
        str(book_dir),
        generate_thumbnails=False,
        source_filename="source.pdf",
    )
    save_to_json(book, str(book_dir))

    server.load_book_cached.cache_clear()
    server.load_book_metadata.cache_clear()
    server.get_cached_reading_times.cache_clear()

    try:
        yield book_id, book_dir
    finally:
        shutil.rmtree(book_dir, ignore_errors=True)


class TestPdfPageImageSettings:
    def test_defaults_to_jpeg(self, monkeypatch):
        monkeypatch.setattr("reader3.services.library.PDF_PAGE_IMAGE_FORMAT", "jpeg")
        monkeypatch.setattr("reader3.services.library.PDF_PAGE_IMAGE_QUALITY", 88)
        monkeypatch.setattr("reader3.services.library.PDF_PAGE_IMAGE_DPI", 200)

        assert _pdf_page_image_settings() == (200, "jpeg", 88, "jpg")

    def test_accepts_png_and_clamps_values(self):
        assert _pdf_page_image_settings(999, "png", 200) == (600, "png", 100, "png")
        assert _pdf_page_image_settings(10, "jpg", 0) == (72, "jpeg", 1, "jpg")
        assert _pdf_page_image_settings(150, "unknown", 85) == (150, "jpeg", 85, "jpg")


class TestPdfDisplayRendering:
    def test_copy_text_keeps_columns_together(self, tmp_path):
        pdf_path = tmp_path / "reading-order.pdf"
        with fitz.open() as doc:
            page = doc.new_page()
            page.insert_text((72, 72), "Left column first")
            page.insert_text((72, 110), "Left column second")
            page.insert_text((320, 72), "Right column first")
            page.insert_text((320, 110), "Right column second")
            doc.save(pdf_path)

        book = process_pdf(str(pdf_path), str(tmp_path / "processed"), generate_thumbnails=False)
        text = book.spine[0].text
        assert text.splitlines() == [
            "Left column first", "Left column second",
            "Right column first", "Right column second",
        ]

    def test_render_pdf_page_image_writes_jpeg(self, tmp_path):
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 72), "JPEG page")

        images_dir = tmp_path / "images"
        images_dir.mkdir()
        result = render_pdf_page_image(
            page, 0, str(images_dir), dpi=100, image_format="jpeg", quality=90
        )

        image_path = images_dir / "page_1.jpg"
        assert result["path"] == "images/page_1.jpg"
        assert result["width"] > 0
        assert result["height"] > 0
        assert image_path.read_bytes().startswith(b"\xff\xd8")
        doc.close()

    def test_render_pdf_page_image_can_write_png(self, tmp_path):
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 72), "PNG page")

        images_dir = tmp_path / "images"
        images_dir.mkdir()
        result = render_pdf_page_image(
            page, 0, str(images_dir), dpi=100, image_format="png"
        )

        image_path = images_dir / "page_1.png"
        assert result["path"] == "images/page_1.png"
        assert image_path.read_bytes().startswith(b"\x89PNG")
        doc.close()

    def test_processed_book_uses_lazy_jpeg_pages(self, processed_pdf_book):
        _, book_dir = processed_pdf_book
        book = deps.load_book_cached(book_dir.name)
        content = book.spine[0].content

        assert "page_1.jpg" in content
        assert 'loading="lazy"' in content
        assert 'decoding="async"' in content
        assert "width=" in content
        assert "height=" in content
        assert (book_dir / "images" / "page_1.jpg").exists()


class TestPdfCopyImageCache:
    def test_copy_render_is_cached_on_disk(self, processed_pdf_book):
        book_id, book_dir = processed_pdf_book

        first_path, first_dpi = deps._ensure_pdf_page_image_file(book_id, 0, 300)
        first_inode = Path(first_path).stat().st_ino

        second_path, second_dpi = deps._ensure_pdf_page_image_file(book_id, 0, 300)
        second_inode = Path(second_path).stat().st_ino

        assert first_path == second_path
        assert first_dpi == second_dpi == 300
        assert first_inode == second_inode
        assert Path(first_path).is_relative_to(book_dir)
        assert Path(first_path).read_bytes().startswith(b"\x89PNG")

    def test_copy_endpoint_serves_cached_png(self, client, processed_pdf_book):
        book_id, book_dir = processed_pdf_book

        response = client.get(f"/api/v1/pdf/{book_id}/page-image/0?dpi=200")

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert response.headers["x-pdf-effective-dpi"] == "200"
        assert response.content.startswith(b"\x89PNG")
        assert (book_dir / "cache" / "pdf-pages").is_dir()


class TestPdfReaderMetadata:
    def test_pages_endpoint_returns_dimensions(self, client, processed_pdf_book):
        book_id, _ = processed_pdf_book

        response = client.get(f"/read/{book_id}/pages/0/1")

        assert response.status_code == 200
        page = response.json()["pages"][0]
        assert page["width"] > 0
        assert page["height"] > 0

    def test_reader_exposes_page_dimensions(self, client, processed_pdf_book):
        book_id, _ = processed_pdf_book

        response = client.get(f"/read/{book_id}/0")

        assert response.status_code == 200
        assert "pdfPageDimensions" in response.text
        assert "data-page-width=" in response.text
        assert "data-page-height=" in response.text


class TestPdfReprocess:
    def test_reprocess_uses_stored_source_pdf(self, client, processed_pdf_book):
        book_id, book_dir = processed_pdf_book

        # The original upload is not in BOOKS_DIR; reprocessing must use the
        # source.pdf stored inside the book directory.
        assert not (Path(server.BOOKS_DIR) / "source.pdf").exists()

        response = client.post(f"/api/v1/reprocess/{book_id}")

        assert response.status_code == 200
        assert response.json()["status"] == "success"
        assert (book_dir / "source.pdf").exists()
        assert (book_dir / "book.json").exists()
