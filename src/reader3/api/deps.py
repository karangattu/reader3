"""Shared dependencies module for Reader3 API routes.

All route modules import shared state, helpers, and constants from here
instead of from app.py — breaking the circular-dependency chain.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import pickle
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import lru_cache
from typing import Dict, Optional
from urllib.parse import quote, unquote

from bs4 import BeautifulSoup
from fastapi import HTTPException
from fastapi.templating import Jinja2Templates

from ..services.library import Book
from ..services.reader import ReaderService
from ..services.search import SearchService
from ..storage.user_data import ReaderPreferences, UserDataManager

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("reader3")

# ---------------------------------------------------------------------------
# Thread pool for blocking I/O inside async handlers
# ---------------------------------------------------------------------------
_io_executor = ThreadPoolExecutor(
    max_workers=int(os.environ.get("IO_WORKERS", 4)),
    thread_name_prefix="reader3-io",
)

# Maximum upload size: 1024 MB by default (configurable via env)
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", 1024))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

VALID_READER_THEMES = {"light", "sepia", "dark", "auto"}

VALID_READER_FONTS = {
    "Georgia", "Literata", "Merriweather", "Lora", "Source Serif 4",
    "Crimson Text", "IBM Plex Serif", "Libre Baskerville", "Vollkorn",
    "Inter",
}

PDF_COPY_IMAGE_DPI = int(os.environ.get("PDF_COPY_IMAGE_DPI", 300))
PDF_COPY_IMAGE_MAX_DPI = 600
PDF_COPY_IMAGE_DPI_OPTIONS = (150, 200, 300, 450, 600)
PDF_RENDER_MAX_DIMENSION = int(os.environ.get("PDF_RENDER_MAX_DIMENSION", "8192"))
PDF_RENDER_MAX_PIXELS = int(os.environ.get("PDF_RENDER_MAX_PIXELS", "40000000"))


def _clamp_pdf_copy_image_dpi(dpi: int) -> int:
    """Clamp PDF image export DPI to a safe supported range."""
    return max(72, min(int(dpi), PDF_COPY_IMAGE_MAX_DPI))


def _pdf_copy_image_dpi_options(default_dpi: int) -> list[int]:
    """Return copy/export DPI options while preserving the configured default."""
    return sorted({*PDF_COPY_IMAGE_DPI_OPTIONS, default_dpi})


def _run_sync(fn, *args):
    """Schedule a blocking function on the I/O thread pool."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.get_event_loop()
    return loop.run_in_executor(_io_executor, fn, *args)


def _pdf_thumbnails_enabled() -> bool:
    """Return whether PDF thumbnail generation is enabled."""
    raw = os.environ.get("PDF_GENERATE_THUMBNAILS", "true")
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _format_pdf_validation_error(error: Optional[str]) -> str:
    """Turn low-level PDF validation failures into user-facing guidance."""
    if not error:
        return "This PDF could not be processed."

    lowered = error.lower()
    if "password-protected" in lowered:
        return (
            "This PDF is password-protected. Remove the password in Preview or "
            "another PDF app, then upload it again."
        )
    if "encrypted" in lowered:
        return (
            "This PDF is encrypted. Export or decrypt it first, then upload the "
            "unlocked copy."
        )
    if "bad header" in lowered or "not a valid pdf" in lowered:
        return "This file does not look like a valid PDF."
    return error


# ---------------------------------------------------------------------------
# Upload processing status tracking
# ---------------------------------------------------------------------------
upload_status: Dict[str, dict] = {}
upload_status_lock = threading.Lock()


def update_upload_status(upload_id: str, **kwargs):
    """Thread-safe update of upload status."""
    with upload_status_lock:
        if upload_id in upload_status:
            upload_status[upload_id].update(kwargs)


def cleanup_old_statuses():
    """Remove completed statuses older than 1 hour."""
    cutoff = datetime.now().timestamp() - 3600
    with upload_status_lock:
        to_remove = [
            uid for uid, status in upload_status.items()
            if status.get("completed_at") and status["completed_at"] < cutoff
        ]
        for uid in to_remove:
            del upload_status[uid]


# ---------------------------------------------------------------------------
# Resource paths
# ---------------------------------------------------------------------------
if getattr(sys, "frozen", False):
    # If run as an executable (PyInstaller)
    base_resource_path = sys._MEIPASS
    templates_dir = os.path.join(base_resource_path, "templates")
else:
    # If run as a script — go up one level from api/ to reader3/
    base_resource_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # The canonical templates live in the repo-root templates/ directory.
    # Fall back to a packaged copy (e.g. installed wheel) if absent.
    _repo_templates = os.path.join(
        os.path.dirname(os.path.dirname(base_resource_path)), "templates"
    )
    templates_dir = (
        _repo_templates
        if os.path.isdir(_repo_templates)
        else os.path.join(base_resource_path, "templates")
    )

templates = Jinja2Templates(directory=templates_dir)

# Static assets (fonts, etc.). Resolve like templates: prefer the repo-root
# static/ dir in a source checkout, else the packaged copy, else the bundle.
if getattr(sys, "frozen", False):
    static_dir = os.path.join(base_resource_path, "static")
else:
    _repo_static = os.path.join(
        os.path.dirname(os.path.dirname(base_resource_path)), "static"
    )
    static_dir = (
        _repo_static
        if os.path.isdir(_repo_static)
        else os.path.join(base_resource_path, "static")
    )

# Where are the book folders located?
if os.environ.get("READER3_BOOKS_DIR"):
    BOOKS_DIR = os.environ["READER3_BOOKS_DIR"]
elif getattr(sys, "frozen", False):
    executable_path = sys.executable
    if ".app/Contents/MacOS" in executable_path:
        app_bundle_path = os.path.dirname(
            os.path.dirname(os.path.dirname(executable_path))
        )
        BOOKS_DIR = os.path.dirname(app_bundle_path)
    else:
        BOOKS_DIR = os.path.dirname(executable_path)
else:
    BOOKS_DIR = os.environ.get("BOOKS_DIR", ".")

# Initialize user data manager
user_data_manager = UserDataManager(BOOKS_DIR)

logger.info("Books directory: %s", BOOKS_DIR)
logger.info("Templates directory: %s", templates_dir)


# ---------------------------------------------------------------------------
# Service factories
# ---------------------------------------------------------------------------
def get_reader_service() -> ReaderService:
    """Create a reader service bound to the current user-state repository."""
    return ReaderService(user_data_manager)


def get_search_service() -> SearchService:
    """Create a search service bound to the current books directory."""
    return SearchService(BOOKS_DIR, load_book_cached)


def _process_pdf(*args, **kwargs):
    """Call the public PDF processor so legacy monkeypatches still apply."""
    import reader3 as reader3_public

    return reader3_public.process_pdf(*args, **kwargs)


# ---------------------------------------------------------------------------
# Book loading & metadata helpers (cached)
# ---------------------------------------------------------------------------
def _compute_progress_percent(book_id: str, chapter_count: int) -> float:
    """Compute overall progress percent for a book from per-chapter progress."""
    chapter_progress = user_data_manager.get_chapter_progress(book_id)
    if not chapter_progress or chapter_count <= 0:
        return 0.0
    return round(min(100.0, sum(chapter_progress.values()) / chapter_count), 1)


def _progress_status_label(progress_percent: float) -> str:
    """Map numeric progress to a library-friendly reading status."""
    if progress_percent >= 100.0:
        return "completed"
    if progress_percent > 0:
        return "in_progress"
    return "unread"


def _persist_upload_metadata(book_dir: str, source_hash: str, source_filename: str):
    """Augment saved metadata with upload-specific fields used by the library."""
    meta_path = os.path.join(book_dir, "book_meta.json")
    if not os.path.exists(meta_path):
        return

    try:
        with open(meta_path, "r", encoding="utf-8") as handle:
            metadata = json.load(handle)
        metadata["source_hash"] = source_hash
        metadata["source_file"] = source_filename
        _atomic_write_json(meta_path, metadata)
    except Exception as exc:
        logger.error("Error updating upload metadata for %s: %s", book_dir, exc)


def _find_duplicate_book_by_hash(source_hash: str) -> Optional[dict]:
    """Find an existing library entry with the same source file hash."""
    if not os.path.exists(BOOKS_DIR):
        return None

    for item in os.listdir(BOOKS_DIR):
        item_path = os.path.join(BOOKS_DIR, item)
        if not item.endswith("_data") or not os.path.isdir(item_path):
            continue

        metadata = load_book_metadata(item)
        if metadata and metadata.get("source_hash") == source_hash:
            return {
                "book_id": item,
                "title": metadata.get("title") or item.replace("_data", ""),
            }
    return None


def _find_active_upload(filename: str) -> Optional[str]:
    """Return an active upload id for a matching filename, if any."""
    with upload_status_lock:
        for uid, status in upload_status.items():
            if (
                status.get("filename") == filename
                and status.get("status") in {"queued", "processing"}
            ):
                return uid
    return None


def _build_library_entry(folder_name: str, metadata: dict) -> dict:
    """Create the lightweight book record used by the library page."""
    progress_percent = _compute_progress_percent(folder_name, metadata.get("chapters", 0))
    return {
        "id": folder_name,
        "title": metadata.get("title", "Untitled"),
        "author": ", ".join(metadata.get("authors", [])),
        "chapters": metadata.get("chapters", 0),
        "added_at": metadata.get("added_at"),
        "cover_image": metadata.get("cover_image"),
        "progress_percent": progress_percent,
        "reading_status": _progress_status_label(progress_percent),
    }


def _effective_pdf_copy_image_dpi(preferences: Optional[ReaderPreferences] = None) -> int:
    """Return the saved PDF copy DPI or the configured default when unset."""
    if preferences is None:
        return _clamp_pdf_copy_image_dpi(PDF_COPY_IMAGE_DPI)

    preferred_dpi = getattr(preferences, "pdf_copy_image_dpi", PDF_COPY_IMAGE_DPI)
    return _clamp_pdf_copy_image_dpi(preferred_dpi)


def _serialize_reader_preferences(preferences: ReaderPreferences) -> dict:
    """Convert reader preferences to a response/template payload."""
    return {
        "theme": preferences.theme,
        "font_size_px": preferences.font_size_px,
        "line_height": preferences.line_height,
        "page_width_px": preferences.page_width_px,
        "reduced_motion": preferences.reduced_motion,
        "high_contrast": preferences.high_contrast,
        "font_family": preferences.font_family,
        "pdf_copy_image_dpi": _effective_pdf_copy_image_dpi(preferences),
        "text_align": getattr(preferences, "text_align", "justify"),
    }


@lru_cache(maxsize=50)
def load_book_cached(folder_name: str) -> Optional[Book]:
    """
    Loads the book from the pickle file.
    Cached so we don't re-read the disk on every click.
    """
    book_dir = os.path.join(BOOKS_DIR, folder_name)
    json_path = os.path.join(book_dir, "book.json")
    if os.path.exists(json_path):
        try:
            from ..services.library import load_from_json

            return load_from_json(json_path)
        except Exception as e:
            logger.error("Error loading book %s from JSON: %s", folder_name, e)
            return None

    # Backward compatibility: migrate legacy pickles to JSON on first read.
    pkl_path = os.path.join(book_dir, "book.pkl")
    if not os.path.exists(pkl_path):
        return None

    try:
        with open(pkl_path, "rb") as f:
            book = pickle.load(f)
    except Exception as e:
        logger.error("Error loading book %s: %s", folder_name, e)
        return None

    try:
        from ..services.library import save_to_json

        save_to_json(book, book_dir)
        logger.info("Migrated %s from pickle to JSON", folder_name)
    except Exception as e:
        logger.warning("Failed to auto-migrate %s to JSON: %s", folder_name, e)

    return book


@lru_cache(maxsize=200)
def load_book_metadata(folder_name: str) -> Optional[dict]:
    """Load lightweight metadata for a book without unpickling if possible."""
    meta_path = os.path.join(BOOKS_DIR, folder_name, "book_meta.json")
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Error reading metadata for %s: %s", folder_name, e)

    book = load_book_cached(folder_name)
    if not book:
        return None

    return write_book_metadata(folder_name, book)


def _atomic_write_json(path: str, payload):
    """Atomically serialize JSON so interrupted writes cannot corrupt files."""
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)
        handle.flush()
        try:
            os.fsync(handle.fileno())
        except OSError:
            pass
    os.replace(tmp_path, path)


def write_book_metadata(folder_name: str, book: Book) -> dict:
    """Write lightweight metadata to disk and return it."""
    meta_path = os.path.join(BOOKS_DIR, folder_name, "book_meta.json")
    metadata = {
        "title": book.metadata.title,
        "authors": book.metadata.authors,
        "chapters": len(book.spine),
        "added_at": book.added_at or book.processed_at,
        "processed_at": book.processed_at,
        "cover_image": book.cover_image,
        "is_pdf": book.is_pdf,
        "language": book.metadata.language,
        "source_file": book.source_file,
    }

    try:
        _atomic_write_json(meta_path, metadata)
    except Exception as e:
        logger.error("Error writing metadata for %s: %s", folder_name, e)

    return metadata


@lru_cache(maxsize=200)
def get_cached_reading_times(book_id: str) -> Optional[dict]:
    """Compute and cache per-chapter reading times for a book."""
    book = load_book_cached(book_id)
    if not book:
        return None

    # Average reading speed: ~200-250 words per minute
    words_per_minute = 225
    reading_times = {}

    for chapter in book.spine:
        text = getattr(chapter, "text", "") or ""
        if not text:
            import re

            content = chapter.content or ""
            text = re.sub(r"<[^>]+>", " ", content)

        word_count = len(text.split())
        minutes = max(1, round(word_count / words_per_minute))
        formatted = (
            f"~{minutes} min"
            if minutes < 60
            else f"~{minutes // 60}h {minutes % 60}m"
        )

        reading_times[chapter.href] = {
            "word_count": word_count,
            "minutes": minutes,
            "formatted": formatted,
        }

    return reading_times


# ---------------------------------------------------------------------------
# Content-serving helpers
# ---------------------------------------------------------------------------
def _chapter_or_none(book: Optional[Book], chapter_index: Optional[int]):
    """Return a chapter when the index is in range, otherwise None."""
    if book is None or chapter_index is None:
        return None
    if chapter_index < 0 or chapter_index >= len(book.spine):
        return None
    return book.spine[chapter_index]


def _resolve_book_image_path(book_id: str, image_name: str) -> str:
    """Resolve an EPUB image name to its on-disk path."""
    safe_book_id = os.path.basename(book_id)
    safe_image_name = os.path.basename(image_name)
    return os.path.join(BOOKS_DIR, safe_book_id, "images", safe_image_name)


def _url_path_basename(value: str) -> str:
    """Return the basename from a URL/path using EPUB-style separators."""
    clean_value = unquote(value).split("#", 1)[0].split("?", 1)[0]
    return clean_value.replace("\\", "/").rsplit("/", 1)[-1]


def _book_image_url(book_id: str, image_path: str) -> str:
    """Build an absolute reader URL for a stored book image."""
    image_name = _url_path_basename(image_path)
    return f"/read/{quote(book_id, safe='')}/images/{quote(image_name, safe='')}"


def _book_image_exists(book_id: str, image_path: str) -> bool:
    """Return whether a stored book image exists on disk."""
    image_name = _url_path_basename(image_path)
    return os.path.exists(_resolve_book_image_path(book_id, image_name))


def _rewrite_reader_content_asset_paths_impl(content: str, book_id: str, book: Book) -> str:
    """Rewrite legacy relative image paths so reader pages resolve assets reliably."""
    if not content or "<img" not in content.lower():
        return content

    soup = BeautifulSoup(content, "html.parser")
    image_map = getattr(book, "images", {}) or {}

    for img in soup.find_all("img"):
        src = img.get("src") or ""
        if not src or src.startswith(("/", "data:", "http://", "https://")):
            continue

        decoded_src = unquote(src).replace("\\", "/")
        image_name = _url_path_basename(decoded_src)
        mapped_path = (
            image_map.get(decoded_src)
            or image_map.get(image_name)
        )

        if not mapped_path and image_name:
            mapped_path = f"images/{image_name}"

        if mapped_path:
            if not _book_image_exists(book_id, mapped_path):
                cover_image = getattr(book, "cover_image", None)
                if (
                    cover_image
                    and "cover" in image_name.lower()
                    and _book_image_exists(book_id, cover_image)
                ):
                    mapped_path = cover_image
            img["src"] = _book_image_url(book_id, mapped_path)

    return str(soup)


# Cache of rewritten chapter HTML, keyed by (book_id, content length, content hash).
_REWRITE_CACHE: dict[tuple[str, int, int], str] = {}
_REWRITE_CACHE_LOCK = threading.Lock()
_REWRITE_CACHE_MAX = 4096


def _rewrite_reader_content_asset_paths(content: str, book_id: str, book: Book) -> str:
    """Cached entry point preserving the historical call signature."""
    if not content or "<img" not in content.lower():
        return content

    cache_key = (book_id, len(content), hash(content))
    with _REWRITE_CACHE_LOCK:
        cached = _REWRITE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    result = _rewrite_reader_content_asset_paths_impl(content, book_id, book)

    with _REWRITE_CACHE_LOCK:
        if len(_REWRITE_CACHE) >= _REWRITE_CACHE_MAX:
            for old_key in list(_REWRITE_CACHE.keys())[: _REWRITE_CACHE_MAX // 4]:
                _REWRITE_CACHE.pop(old_key, None)
        _REWRITE_CACHE[cache_key] = result

    return result


def clear_rewrite_cache() -> None:
    """Drop all cached rewritten chapter payloads."""
    with _REWRITE_CACHE_LOCK:
        _REWRITE_CACHE.clear()


def _pdf_page_image_cache_path(book_id: str, page_num: int, dpi: int) -> str:
    """Return the on-disk cache path for a rendered copy/export page."""
    safe_book_id = os.path.basename(book_id)
    return os.path.join(
        BOOKS_DIR,
        safe_book_id,
        "cache",
        "pdf-pages",
        f"page_{page_num + 1}_{dpi}.png",
    )


def _pdf_render_zoom(page_width: float, page_height: float, requested_dpi: int) -> float:
    """Return a zoom that respects the configured maximum render size."""
    zoom = requested_dpi / 72
    if page_width <= 0 or page_height <= 0:
        return zoom

    scale_for_dimension = min(
        PDF_RENDER_MAX_DIMENSION / page_width,
        PDF_RENDER_MAX_DIMENSION / page_height,
    )
    scale_for_area = math.sqrt(
        PDF_RENDER_MAX_PIXELS / max(page_width * page_height, 1.0)
    )
    return max(0.01, min(zoom, scale_for_dimension, scale_for_area))


def _ensure_pdf_page_image_file(
    book_id: str,
    page_num: int,
    dpi: int = PDF_COPY_IMAGE_DPI,
) -> tuple[str, int]:
    """Render a PDF page to a cached PNG and return its path and effective DPI.

    The cache lives inside the book directory so reprocessing and deleting a
    book automatically invalidate it. Disk caching avoids holding many
    full-resolution page bitmaps in process memory across requests.
    """
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if not book.is_pdf:
        raise HTTPException(status_code=400, detail="Not a PDF book")

    if not book.pdf_source_path:
        raise HTTPException(status_code=404, detail="Source PDF not available")

    safe_book_id = os.path.basename(book_id)
    pdf_name = os.path.basename(book.pdf_source_path or "")
    pdf_path = os.path.join(BOOKS_DIR, safe_book_id, pdf_name)
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="Source PDF not found")

    export_dpi = _clamp_pdf_copy_image_dpi(dpi)
    cache_path = _pdf_page_image_cache_path(safe_book_id, page_num, export_dpi)
    if os.path.exists(cache_path):
        return cache_path, export_dpi

    try:
        import fitz

        with fitz.open(pdf_path) as doc:
            if page_num < 0 or page_num >= len(doc):
                raise HTTPException(status_code=404, detail="Page not found")

            page = doc[page_num]
            try:
                rect = page.rect
                zoom = _pdf_render_zoom(rect.width, rect.height, export_dpi)
            except Exception:
                zoom = export_dpi / 72

            pix = page.get_pixmap(
                matrix=fitz.Matrix(zoom, zoom),
                alpha=False,
            )
            image_bytes = pix.tobytes("png")
            effective_dpi = max(1, round(zoom * 72))
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Failed to render PDF page image for %s page %s: %s",
            book_id,
            page_num,
            exc,
        )
        raise HTTPException(status_code=500, detail="Failed to render PDF page image")

    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    tmp_path = f"{cache_path}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        with open(tmp_path, "wb") as handle:
            handle.write(image_bytes)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
        os.replace(tmp_path, cache_path)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    return cache_path, effective_dpi


def _render_pdf_page_image_bytes(
    book_id: str,
    page_num: int,
    dpi: int = PDF_COPY_IMAGE_DPI,
) -> bytes:
    """Render a PDF page on demand and return PNG bytes (compatibility helper)."""
    cache_path, _ = _ensure_pdf_page_image_file(book_id, page_num, dpi)
    with open(cache_path, "rb") as handle:
        return handle.read()


def repair_pdf_thumbnails(book_id: str) -> dict:
    """Generate any missing thumbnails for a PDF book.

    This repairs libraries where thumbnail generation was disabled or failed
    during the original import, without reprocessing the whole PDF.
    """
    safe_book_id = os.path.basename(book_id)
    book = load_book_cached(safe_book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    if not book.is_pdf:
        raise HTTPException(status_code=400, detail="Not a PDF book")

    pdf_name = os.path.basename(book.pdf_source_path or "")
    if not pdf_name:
        raise HTTPException(status_code=404, detail="Source PDF not available")
    book_dir = os.path.join(BOOKS_DIR, safe_book_id)
    pdf_path = os.path.join(book_dir, pdf_name)
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="Source PDF not found")

    try:
        import fitz

        from ..services.library import generate_pdf_thumbnail, save_to_json
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PDF tools unavailable: {exc}") from exc

    thumbs_dir = os.path.join(book_dir, "thumbnails")
    os.makedirs(thumbs_dir, exist_ok=True)

    total_pages = int(book.pdf_total_pages or 0)
    generated = 0
    existing = 0
    failed = []

    try:
        with fitz.open(pdf_path) as doc:
            if total_pages <= 0 or total_pages > len(doc):
                total_pages = len(doc)
            for page_num in range(total_pages):
                thumb_path = os.path.join(
                    thumbs_dir, f"thumb_{page_num + 1}.png"
                )
                if os.path.exists(thumb_path):
                    existing += 1
                    continue
                try:
                    page = doc[page_num]
                    generate_pdf_thumbnail(page, page_num, thumbs_dir)
                    generated += 1
                except Exception as exc:
                    logger.error(
                        "Thumbnail generation failed for %s page %s: %s",
                        safe_book_id,
                        page_num + 1,
                        exc,
                    )
                    failed.append({"page": page_num, "error": str(exc)})
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to open PDF: {exc}") from exc

    all_present = (existing + generated) >= total_pages and total_pages > 0
    book.pdf_thumbnails_generated = all_present or book.pdf_thumbnails_generated
    book.pdf_total_pages = total_pages or book.pdf_total_pages

    try:
        save_to_json(book, book_dir)
    except Exception as exc:
        logger.error("Error saving repaired thumbnail metadata for %s: %s", safe_book_id, exc)

    # Invalidate caches after mutating book data.
    load_book_cached.cache_clear()
    load_book_metadata.cache_clear()
    get_cached_reading_times.cache_clear()

    return {
        "book_id": safe_book_id,
        "generated": generated,
        "existing": existing,
        "failed": failed,
        "total": total_pages,
        "available": all_present,
    }


def get_all_book_ids():
    """Get list of all book IDs in the library."""
    book_ids = []
    if os.path.exists(BOOKS_DIR):
        for item in os.listdir(BOOKS_DIR):
            item_path = os.path.join(BOOKS_DIR, item)
            if item.endswith("_data") and os.path.isdir(item_path):
                pkl_path = os.path.join(item_path, "book.pkl")
                json_path = os.path.join(item_path, "book.json")
                if os.path.exists(pkl_path) or os.path.exists(json_path):
                    book_ids.append(item)
    return book_ids
