"""Regression tests for infrastructure and performance optimizations."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from reader3.api import deps
from reader3.api.routes import upload as upload_routes
from reader3.services.library import (
    Book,
    BookMetadata,
    ChapterContent,
    save_to_json,
)
from reader3.storage.jobs import UploadJobStore
from reader3.storage.search import get_exact_search_index
from reader3.storage.user_data import Bookmark, Highlight, UserDataManager, generate_id


ROOT = Path(__file__).resolve().parents[1]


def test_deployment_uses_one_worker() -> None:
    render = (ROOT / "render.yaml").read_text()
    dockerfile = (ROOT / "Dockerfile").read_text()

    assert "--workers ${WEB_CONCURRENCY:-1}" in render
    assert 'key: WEB_CONCURRENCY\n        value: "1"' in render
    assert '"--workers", "1"' in dockerfile
    assert "WEB_CONCURRENCY=1" in dockerfile


def test_targeted_writes_preserve_other_manager_updates(tmp_path) -> None:
    first = UserDataManager(str(tmp_path))
    stale_second = UserDataManager(str(tmp_path))
    stale_second.load()

    first.add_highlight(
        Highlight(
            id=generate_id(),
            book_id="book",
            chapter_index=0,
            text="highlight",
            color="yellow",
        )
    )
    stale_second.add_bookmark(
        Bookmark(
            id=generate_id(),
            book_id="book",
            chapter_index=0,
            scroll_position=0.5,
            title="bookmark",
        )
    )

    reloaded = UserDataManager(str(tmp_path))
    assert len(reloaded.get_highlights("book")) == 1
    assert len(reloaded.get_bookmarks("book")) == 1


def test_upload_job_store_is_durable_and_hides_internal_fields(tmp_path) -> None:
    job = {
        "id": "upload-1",
        "status": "queued",
        "progress": 0,
        "message": "queued",
        "filename": "book.pdf",
        "book_id": None,
        "started_at": 1.0,
        "completed_at": None,
        "temp_path": "/tmp/book.pdf",
        "suffix": ".pdf",
        "out_dir": "book_data",
        "source_filename": "book.pdf",
        "source_hash": "hash",
    }
    UploadJobStore(str(tmp_path)).create(job)

    reopened = UploadJobStore(str(tmp_path))
    stored = reopened.get("upload-1")
    assert stored["temp_path"] == "/tmp/book.pdf"
    assert "temp_path" not in reopened.public(stored)

    reopened.update("upload-1", status="completed", progress=100)
    assert reopened.get("upload-1")["status"] == "completed"


def test_submit_upload_job_returns_false_when_queue_is_full(monkeypatch) -> None:
    class FullSlots:
        def acquire(self, blocking=False):
            return False

    monkeypatch.setattr(upload_routes, "_upload_slots", FullSlots())
    assert upload_routes.submit_upload_job({"id": "unused"}) is False


def test_signature_cache_is_byte_bounded(tmp_path) -> None:
    loads = []

    def loader(key):
        loads.append(key)
        return {"value": key}

    cache = deps._SignatureCache(
        loader,
        lambda key: str(tmp_path / key),
        max_bytes=40,
        max_entries=10,
    )
    for name in ("a", "b"):
        (tmp_path / name).write_bytes(b"12345678")

    assert cache("a") == {"value": "a"}
    assert cache("b") == {"value": "b"}
    assert cache.cache_info().currsize == 1
    assert loads == ["a", "b"]


def test_pdf_copy_cache_evicts_oldest_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(deps, "BOOKS_DIR", str(tmp_path))
    monkeypatch.setattr(deps, "PDF_COPY_CACHE_MAX_MB", 1)

    old_dir = tmp_path / "old_data" / "cache" / "pdf-pages"
    new_dir = tmp_path / "new_data" / "cache" / "pdf-pages"
    old_dir.mkdir(parents=True)
    new_dir.mkdir(parents=True)
    old_path = old_dir / "page_1_300.png"
    new_path = new_dir / "page_1_300.png"
    old_path.write_bytes(b"a" * 700_000)
    new_path.write_bytes(b"b" * 700_000)
    os.utime(old_path, (time.time() - 60, time.time() - 60))

    deps._trim_pdf_page_cache(str(new_path))

    assert not old_path.exists()
    assert new_path.exists()


def test_fts_index_reuses_book_and_supports_offsets(tmp_path) -> None:
    book_dir = tmp_path / "book_data"
    book_dir.mkdir()
    book = Book(
        metadata=BookMetadata(title="Search demo", language="en"),
        spine=[
            ChapterContent(
                id="chapter-1",
                href="chapter-1.html",
                title="Chapter 1",
                content="<p>alpha beta alpha</p>",
                text="alpha beta alpha",
                order=0,
            )
        ],
        toc=[],
        images={},
        source_file="demo.epub",
        processed_at="2026-01-01T00:00:00",
        content_sanitized_version=2,
    )
    save_to_json(book, str(book_dir))

    loads = []

    def load_book(book_id):
        loads.append(book_id)
        return book

    index = get_exact_search_index(str(tmp_path))
    if not index._ensure_schema():
        pytest.skip("SQLite FTS5 trigram tokenizer is unavailable")

    first = index.search("alpha", ["book_data"], load_book, limit=10)
    second = index.search("alpha", ["book_data"], load_book, limit=10)
    offset = index.search(
        "alpha", ["book_data"], load_book, limit=1, offset=1
    )

    assert [match["position"] for match in first] == [0, 11]
    assert second == first
    assert [match["position"] for match in offset] == [11]
    assert loads == ["book_data"]

    book.spine[0].text = "gamma beta gamma"
    book.processed_at = "2026-01-02T00:00:00"
    save_to_json(book, str(book_dir))
    updated = index.search("gamma", ["book_data"], load_book, limit=10)
    assert [match["position"] for match in updated] == [0, 11]
    assert loads == ["book_data", "book_data"]
