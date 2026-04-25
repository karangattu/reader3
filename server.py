import asyncio
import hashlib
import json
import logging
import os
import pickle
import shutil
import sys
import tempfile
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime
from functools import lru_cache
from typing import Dict, Optional

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from copilot_service import CopilotSummaryError, CopilotSummaryService
from reader3 import (
    Book,
    get_pdf_page_stats,
    process_epub,
    save_to_pickle,
    search_pdf_text_positions,
    validate_pdf,
)
from semantic_search import semantic_search_books
from user_data import (
    Annotation,
    Bookmark,
    Highlight,
    ReaderPreferences,
    ReadingProgress,
    ReadingSession,
    SearchQuery,
    UserDataManager,
    VocabularyWord,
    generate_id,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("reader3")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

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

VALID_READER_THEMES = {"light", "sepia", "dark"}

VALID_READER_FONTS = {
    "Georgia", "Literata", "Merriweather", "Lora", "Source Serif 4",
    "Crimson Text", "IBM Plex Serif", "Libre Baskerville", "Vollkorn",
    "Inter",
}

PDF_COPY_IMAGE_DPI = int(os.environ.get("PDF_COPY_IMAGE_DPI", 300))
PDF_COPY_IMAGE_MAX_DPI = 600
PDF_COPY_IMAGE_DPI_OPTIONS = (150, 200, 300, 450, 600)


def _clamp_pdf_copy_image_dpi(dpi: int) -> int:
    """Clamp PDF image export DPI to a safe supported range."""
    return max(72, min(int(dpi), PDF_COPY_IMAGE_MAX_DPI))


def _pdf_copy_image_dpi_options(default_dpi: int) -> list[int]:
    """Return copy/export DPI options while preserving the configured default."""
    return sorted({*PDF_COPY_IMAGE_DPI_OPTIONS, default_dpi})


def _run_sync(fn, *args):
    """Schedule a blocking function on the I/O thread pool."""
    return asyncio.get_event_loop().run_in_executor(_io_executor, fn, *args)


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
        with open(meta_path, "w", encoding="utf-8") as handle:
            json.dump(metadata, handle, ensure_ascii=False)
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
        for upload_id, status in upload_status.items():
            if (
                status.get("filename") == filename
                and status.get("status") in {"queued", "processing"}
            ):
                return upload_id
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
    }


# ---------------------------------------------------------------------------
# Security headers middleware
# ---------------------------------------------------------------------------
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response


# ---------------------------------------------------------------------------
# Cache-Control middleware for static assets
# ---------------------------------------------------------------------------
class CacheControlMiddleware(BaseHTTPMiddleware):
    """Adds Cache-Control headers for images and thumbnails."""

    # Paths that benefit from aggressive caching (immutable book assets)
    STATIC_PREFIXES = ("/read/",)
    STATIC_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if any(path.startswith(p) for p in self.STATIC_PREFIXES) and any(
            path.endswith(s) for s in self.STATIC_SUFFIXES
        ):
            # Book images/thumbnails never change once processed
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif path.startswith("/cover/"):
            response.headers["Cache-Control"] = "public, max-age=86400"
        return response


# ---------------------------------------------------------------------------
# Lifespan: startup / shutdown hooks
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Reader3 starting up")
    startup_error = await copilot_summary_service.start()
    if startup_error:
        logger.warning("Copilot summaries unavailable: %s", startup_error)
    yield
    logger.info("Reader3 shutting down – flushing user data")
    await copilot_summary_service.stop()
    user_data_manager.flush()
    _io_executor.shutdown(wait=False)


app = FastAPI(
    lifespan=lifespan,
)

# --- Middleware (applied bottom-to-top, so GZip wraps everything) ---
app.add_middleware(CacheControlMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=500, compresslevel=6)

# Upload processing status tracking
# Keys: upload_id -> {status, progress, message, book_id, filename, started_at, completed_at}
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


# Determine base path for resources (templates)
if getattr(sys, "frozen", False):
    # If run as an executable (PyInstaller)
    base_resource_path = sys._MEIPASS
else:
    # If run as a script
    base_resource_path = os.path.dirname(os.path.abspath(__file__))

templates_dir = os.path.join(base_resource_path, "templates")
templates = Jinja2Templates(directory=templates_dir)

# Where are the book folders located?
# Use environment variable if set (by launcher.py for macOS .app bundles),
# otherwise fall back to executable directory or current directory
if os.environ.get("READER3_BOOKS_DIR"):
    BOOKS_DIR = os.environ["READER3_BOOKS_DIR"]
elif getattr(sys, "frozen", False):
    # Fallback: get the directory containing the .app bundle on macOS
    executable_path = sys.executable
    if ".app/Contents/MacOS" in executable_path:
        app_bundle_path = os.path.dirname(
            os.path.dirname(os.path.dirname(executable_path))
        )
        BOOKS_DIR = os.path.dirname(app_bundle_path)
    else:
        BOOKS_DIR = os.path.dirname(executable_path)
else:
    BOOKS_DIR = "."

# Initialize user data manager
user_data_manager = UserDataManager(BOOKS_DIR)
copilot_summary_service = CopilotSummaryService()

logger.info("Books directory: %s", BOOKS_DIR)
logger.info("Templates directory: %s", templates_dir)
logger.info("Current working directory: %s", os.getcwd())


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health")
async def health_check():
    """Health check for load balancers and monitoring."""
    return {
        "status": "ok",
        "books_dir_exists": os.path.exists(BOOKS_DIR),
    }


@app.get("/api/copilot/status")
async def get_copilot_status():
    """Return Reader3's Copilot SDK availability and model status."""
    return await copilot_summary_service.get_status()


@app.get("/api/copilot/models")
async def list_copilot_models():
    """List the Copilot models available to the signed-in user."""
    try:
        models = await copilot_summary_service.list_available_models()
    except CopilotSummaryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "models": models,
        "current_model": copilot_summary_service.model,
    }


@app.post("/api/copilot/model")
async def set_copilot_model(request: Request):
    """Switch the Copilot model used for subsequent summary requests."""
    payload = await request.json()
    model_name = str(payload.get("model", "")).strip()
    if not model_name:
        raise HTTPException(status_code=400, detail="model is required")

    try:
        copilot_summary_service.set_model(model_name)
    except CopilotSummaryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    status = await copilot_summary_service.get_status()
    return {
        "model": copilot_summary_service.model,
        "status": status,
    }


@lru_cache(maxsize=50)
def load_book_cached(folder_name: str) -> Optional[Book]:
    """
    Loads the book from the pickle file.
    Cached so we don't re-read the disk on every click.
    """
    file_path = os.path.join(BOOKS_DIR, folder_name, "book.pkl")
    if not os.path.exists(file_path):
        return None

    try:
        with open(file_path, "rb") as f:
            book = pickle.load(f)
        return book
    except Exception as e:
        logger.error("Error loading book %s: %s", folder_name, e)
        return None


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
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False)
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


def _render_pdf_page_image_bytes(
    book_id: str,
    page_num: int,
    dpi: int = PDF_COPY_IMAGE_DPI,
) -> bytes:
    """Render a PDF page on demand and return PNG bytes."""
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if not book.is_pdf:
        raise HTTPException(status_code=400, detail="Not a PDF book")

    if not book.pdf_source_path:
        raise HTTPException(status_code=404, detail="Source PDF not available")

    safe_book_id = os.path.basename(book_id)
    pdf_path = os.path.join(BOOKS_DIR, safe_book_id, book.pdf_source_path)
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="Source PDF not found")

    export_dpi = _clamp_pdf_copy_image_dpi(dpi)

    try:
        import fitz

        with fitz.open(pdf_path) as doc:
            if page_num < 0 or page_num >= len(doc):
                raise HTTPException(status_code=404, detail="Page not found")

            zoom = export_dpi / 72
            pix = doc[page_num].get_pixmap(
                matrix=fitz.Matrix(zoom, zoom),
                alpha=False,
            )
            return pix.tobytes("png")
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


@app.get("/", response_class=HTMLResponse)
async def library_view(
    request: Request,
    sort: str = "recent",
    q: str = "",
    status: str = "all",
):
    """Lists all available processed books."""
    books = []

    def _scan_books():
        """Blocking scan moved off the event loop."""
        result = []
        if os.path.exists(BOOKS_DIR):
            for item in os.listdir(BOOKS_DIR):
                item_path = os.path.join(BOOKS_DIR, item)
                if item.endswith("_data") and os.path.isdir(item_path):
                    meta = load_book_metadata(item)
                    if meta:
                        result.append(_build_library_entry(item, meta))
        return result

    books = await _run_sync(_scan_books)

    normalized_query = q.strip().lower()
    if normalized_query:
        books = [
            book for book in books
            if normalized_query in book["title"].lower()
            or normalized_query in book["author"].lower()
        ]

    if status in {"unread", "in_progress", "completed"}:
        books = [book for book in books if book["reading_status"] == status]

    # Sort books based on the sort parameter
    if sort == "recent":
        books.sort(key=lambda x: x["added_at"] or "", reverse=True)
    elif sort == "alpha":
        books.sort(key=lambda x: x["title"].lower())
    elif sort == "author":
        books.sort(key=lambda x: x["author"].lower())
    elif sort == "progress":
        books.sort(
            key=lambda x: (x["progress_percent"], x["added_at"] or ""),
            reverse=True,
        )
    else:
        sort = "recent"

    return templates.TemplateResponse(
        request,
        "library.html",
        {
            "request": request,
            "books": books,
            "sort": sort,
            "library_query": q,
            "status": status,
            "max_upload_mb": MAX_UPLOAD_MB,
        },
    )


@app.get("/cover/{book_id}")
async def get_cover_image(book_id: str):
    """Serve cover image for a book."""
    meta = load_book_metadata(book_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Book not found")

    cover_image = meta.get("cover_image")
    if not cover_image:
        raise HTTPException(status_code=404, detail="No cover image available")

    # Construct the full path to the cover image
    cover_path = os.path.join(BOOKS_DIR, book_id, cover_image)

    # Security: ensure the path is within the book directory
    safe_book_id = os.path.basename(book_id)
    expected_base = os.path.join(BOOKS_DIR, safe_book_id)
    if not os.path.abspath(cover_path).startswith(expected_base):
        raise HTTPException(status_code=403, detail="Access denied")

    if not os.path.exists(cover_path):
        raise HTTPException(status_code=404, detail="Cover image not found")

    return FileResponse(cover_path)


@app.post("/api/metadata/rebuild")
async def rebuild_metadata(force: bool = False):
    """Rebuild lightweight metadata files for all books."""
    updated = 0
    errors = []

    if os.path.exists(BOOKS_DIR):
        for item in os.listdir(BOOKS_DIR):
            item_path = os.path.join(BOOKS_DIR, item)
            if item.endswith("_data") and os.path.isdir(item_path):
                meta_path = os.path.join(item_path, "book_meta.json")
                if not force and os.path.exists(meta_path):
                    continue

                book = load_book_cached(item)
                if not book:
                    errors.append({"book_id": item, "error": "Book not found"})
                    continue

                try:
                    write_book_metadata(item, book)
                    updated += 1
                except Exception as e:
                    errors.append({"book_id": item, "error": str(e)})

    load_book_metadata.cache_clear()

    return {"status": "ok", "updated": updated, "errors": errors}


def process_book_background(
    upload_id: str,
    temp_path: str,
    suffix: str,
    full_out_dir: str,
    out_dir: str,
    source_filename: str = "",
    source_hash: str = "",
):
    """Background task to process a book (PDF or EPUB)."""
    try:
        update_upload_status(upload_id, status="processing", progress=10, message="Starting processing...")

        def progress_callback(progress: int, message: str):
            update_upload_status(
                upload_id,
                status="processing",
                progress=max(10, min(95, int(progress))),
                message=message,
            )

        if suffix == ".pdf":
            from reader3 import process_pdf
            validation = validate_pdf(temp_path)
            if not validation["valid"]:
                raise ValueError(_format_pdf_validation_error(validation["error"]))
            update_upload_status(upload_id, progress=20, message="Preparing PDF import...")
            book_obj = process_pdf(
                temp_path,
                full_out_dir,
                generate_thumbnails=_pdf_thumbnails_enabled(),
                progress_callback=progress_callback,
                source_filename=source_filename or None,
            )
        else:
            update_upload_status(upload_id, progress=20, message="Parsing EPUB structure...")
            book_obj = process_epub(temp_path, full_out_dir)

        update_upload_status(upload_id, progress=80, message="Saving book data...")
        save_to_pickle(book_obj, full_out_dir)
        if source_hash:
            _persist_upload_metadata(full_out_dir, source_hash, source_filename or book_obj.source_file)

        # Clear caches
        load_book_cached.cache_clear()
        get_cached_reading_times.cache_clear()
        load_book_metadata.cache_clear()

        update_upload_status(
            upload_id,
            status="completed",
            progress=100,
            message="Processing complete!",
            book_id=out_dir,
            completed_at=datetime.now().timestamp()
        )
        logger.info("Background processing completed for %s", out_dir)

    except Exception as e:
        logger.error("Error processing book in background: %s", e)
        # Clean up partial data if failed
        if os.path.exists(full_out_dir):
            shutil.rmtree(full_out_dir)
        update_upload_status(
            upload_id,
            status="failed",
            progress=0,
            message=f"Failed to process book: {str(e)}",
            completed_at=datetime.now().timestamp()
        )
    finally:
        # Clean up temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)


@app.post("/upload")
async def upload_book(file: UploadFile = File(...), background: bool = False, background_tasks: BackgroundTasks = None):
    """Handle EPUB/PDF file uploads. Use ?background=true for async processing."""

    suffix = os.path.splitext(file.filename)[1].lower()
    if suffix not in [".epub", ".pdf"]:
        raise HTTPException(
            status_code=400, detail="Only .epub and .pdf files are supported"
        )

    # Stream the upload to a temp file with size enforcement
    hasher = hashlib.sha256()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        bytes_written = 0
        while chunk := await file.read(1024 * 256):  # 256 KB chunks
            bytes_written += len(chunk)
            if bytes_written > MAX_UPLOAD_BYTES:
                tmp.close()
                os.remove(tmp.name)
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large. Maximum size is {MAX_UPLOAD_MB} MB.",
                )
            hasher.update(chunk)
            tmp.write(chunk)
        temp_path = tmp.name

    safe_filename = os.path.basename(file.filename)
    source_hash = hasher.hexdigest()
    out_dir = os.path.splitext(safe_filename)[0] + "_data"
    full_out_dir = os.path.join(BOOKS_DIR, out_dir)

    active_upload_id = _find_active_upload(safe_filename)
    if active_upload_id:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return JSONResponse(
            status_code=409,
            content={
                "detail": "This book is already being processed.",
                "upload_id": active_upload_id,
            },
        )

    duplicate_book = _find_duplicate_book_by_hash(source_hash)
    if duplicate_book:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(
            status_code=409,
            detail=f'{duplicate_book["title"]} is already in your library.',
        )

    if suffix == ".pdf":
        validation = validate_pdf(temp_path)
        if not validation["valid"]:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise HTTPException(
                status_code=400,
                detail=_format_pdf_validation_error(validation["error"]),
            )

    # Background processing for PDFs (they're slower) or when explicitly requested
    if background or (suffix == ".pdf" and background_tasks is not None):
        upload_id = str(uuid.uuid4())
        cleanup_old_statuses()

        with upload_status_lock:
            upload_status[upload_id] = {
                "status": "queued",
                "progress": 0,
                "message": "Upload received, queued for processing...",
                "filename": safe_filename,
                "book_id": None,
                "started_at": datetime.now().timestamp(),
                "completed_at": None,
            }

        # Run in background thread for true async processing
        thread = threading.Thread(
            target=process_book_background,
            args=(
                upload_id,
                temp_path,
                suffix,
                full_out_dir,
                out_dir,
                safe_filename,
                source_hash,
            ),
            daemon=True
        )
        thread.start()

        return JSONResponse(
            status_code=202,
            content={"upload_id": upload_id, "status": "processing", "message": "Processing started in background"}
        )

    # Synchronous processing (original behavior for EPUBs)
    try:
        logger.info("Processing %s -> %s", temp_path, full_out_dir)

        if suffix == ".pdf":
            from reader3 import process_pdf
            book_obj = process_pdf(
                temp_path,
                full_out_dir,
                generate_thumbnails=_pdf_thumbnails_enabled(),
                source_filename=safe_filename,
            )
        else:
            book_obj = process_epub(temp_path, full_out_dir)

        save_to_pickle(book_obj, full_out_dir)
        _persist_upload_metadata(full_out_dir, source_hash, safe_filename)

        load_book_cached.cache_clear()
        get_cached_reading_times.cache_clear()
        load_book_metadata.cache_clear()

    except Exception as e:
        logger.error("Error processing book: %s", e)
        if os.path.exists(full_out_dir):
            shutil.rmtree(full_out_dir)
        raise HTTPException(status_code=500, detail=f"Failed to process book: {str(e)}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    return RedirectResponse(url="/", status_code=303)


@app.get("/api/upload/status/{upload_id}")
async def get_upload_status(upload_id: str):
    """Get the status of a background upload processing job."""
    with upload_status_lock:
        status = upload_status.get(upload_id)

    if not status:
        raise HTTPException(status_code=404, detail="Upload not found")

    return status


@app.get("/api/upload/status")
async def list_upload_statuses():
    """List all recent upload processing jobs."""
    cleanup_old_statuses()
    with upload_status_lock:
        return {"uploads": list(upload_status.values())}


@app.get("/read/{book_id}", response_class=HTMLResponse)
async def redirect_to_first_chapter(request: Request, book_id: str):
    """Helper to just go to chapter 0."""
    return await read_chapter(request=request, book_id=book_id, chapter_index=0)


@app.get("/read/{book_id}/{chapter_index}", response_class=HTMLResponse)
async def read_chapter(request: Request, book_id: str, chapter_index: int):
    """The main reader interface."""
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if chapter_index < 0 or chapter_index >= len(book.spine):
        raise HTTPException(status_code=404, detail="Chapter not found")

    current_chapter = book.spine[chapter_index]

    # Calculate Prev/Next links
    prev_idx = chapter_index - 1 if chapter_index > 0 else None
    next_idx = chapter_index + 1 if chapter_index < len(book.spine) - 1 else None

    # Check if this is an old-style PDF (text-based instead of image-based)
    needs_reprocess = False
    if book.is_pdf and len(book.spine) > 0:
        # Old-style PDFs have HTML content with positioned text
        # New-style PDFs have simple img tags
        first_content = book.spine[0].content
        if '<div id="page' in first_content or 'style="top:' in first_content:
            needs_reprocess = True

    reader_preferences = user_data_manager.get_reader_preferences()
    pdf_copy_image_dpi_default = _effective_pdf_copy_image_dpi(reader_preferences)

    return templates.TemplateResponse(
        request,
        "reader.html",
        {
            "request": request,
            "book": book,
            "current_chapter": current_chapter,
            "chapter_index": chapter_index,
            "book_id": book_id,
            "prev_idx": prev_idx,
            "next_idx": next_idx,
            "is_pdf": book.is_pdf,
            "needs_reprocess": needs_reprocess,
            "reader_preferences": _serialize_reader_preferences(reader_preferences),
            "book_font": user_data_manager.get_book_font(book_id),
            "pdf_copy_image_dpi_default": pdf_copy_image_dpi_default,
            "pdf_copy_image_dpi_options": _pdf_copy_image_dpi_options(
                pdf_copy_image_dpi_default
            ),
        },
    )


@app.get("/api/reader/preferences")
async def get_reader_preferences():
    """Get persisted reader appearance preferences."""
    return _serialize_reader_preferences(user_data_manager.get_reader_preferences())


@app.put("/api/reader/preferences")
async def update_reader_preferences(request: Request):
    """Update persisted reader appearance preferences."""
    payload = await request.json()

    updates = {}
    if "theme" in payload:
        theme = str(payload["theme"])
        if theme not in VALID_READER_THEMES:
            raise HTTPException(status_code=400, detail="Invalid reader theme")
        updates["theme"] = theme

    if "font_size_px" in payload:
        value = int(payload["font_size_px"])
        if value < 14 or value > 32:
            raise HTTPException(status_code=400, detail="Font size must be between 14 and 32")
        updates["font_size_px"] = value

    if "line_height" in payload:
        value = float(payload["line_height"])
        if value < 1.3 or value > 2.4:
            raise HTTPException(status_code=400, detail="Line height must be between 1.3 and 2.4")
        updates["line_height"] = value

    if "page_width_px" in payload:
        value = int(payload["page_width_px"])
        if value < 560 or value > 960:
            raise HTTPException(status_code=400, detail="Page width must be between 560 and 960")
        updates["page_width_px"] = value

    for flag_name in ("reduced_motion", "high_contrast"):
        if flag_name in payload:
            updates[flag_name] = bool(payload[flag_name])

    if "font_family" in payload:
        font = str(payload["font_family"])
        if font not in VALID_READER_FONTS:
            raise HTTPException(status_code=400, detail="Invalid font family")
        updates["font_family"] = font

    if "pdf_copy_image_dpi" in payload:
        updates["pdf_copy_image_dpi"] = _clamp_pdf_copy_image_dpi(
            int(payload["pdf_copy_image_dpi"])
        )

    preferences = user_data_manager.update_reader_preferences(**updates)
    return _serialize_reader_preferences(preferences)


@app.get("/api/book-font/{book_id}")
async def get_book_font(book_id: str):
    """Get per-book font override."""
    font = user_data_manager.get_book_font(book_id)
    return {"font_family": font}


@app.put("/api/book-font/{book_id}")
async def set_book_font(book_id: str, request: Request):
    """Set per-book font override."""
    payload = await request.json()
    font = str(payload.get("font_family", ""))
    if font not in VALID_READER_FONTS:
        raise HTTPException(status_code=400, detail="Invalid font family")
    user_data_manager.set_book_font(book_id, font)
    return {"font_family": font}


@app.delete("/api/book-font/{book_id}")
async def clear_book_font(book_id: str):
    """Remove per-book font override (fall back to global)."""
    user_data_manager.clear_book_font(book_id)
    return {"font_family": None}


@app.get("/read/{book_id}/pages/{start}/{count}")
async def get_pages(book_id: str, start: int, count: int):
    """
    Fetches multiple pages for infinite scrolling (PDF only).
    Returns JSON with array of page content.
    """
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if not book.is_pdf:
        raise HTTPException(status_code=400, detail="Infinite scroll only for PDFs")

    total = len(book.spine)
    if start >= total:
        return {"pages": []}

    end = min(start + count, total)
    pages = []

    for i in range(start, end):
        chapter = book.spine[i]
        pages.append({
            "index": i,
            "title": chapter.title,
            "content": chapter.content
        })

    return {"pages": pages, "total": total}


@app.post("/api/chapters/text")
async def get_chapters_text(request: Request):
    """
    Fetches text content from multiple chapters for copying.
    Expects JSON body: {"book_id": "...", "chapter_hrefs": [...]}
    Returns JSON with text content for each chapter.
    """
    body = await request.json()
    book_id = body.get("book_id")
    chapter_hrefs = body.get("chapter_hrefs", [])

    if not book_id:
        raise HTTPException(status_code=400, detail="book_id is required")

    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    # Build a map of href -> chapter
    href_to_chapter = {ch.href: ch for ch in book.spine}

    # Collect text content
    chapters_data = []
    for href in chapter_hrefs:
        chapter = href_to_chapter.get(href)
        if chapter:
            chapters_data.append({
                "href": href,
                "title": chapter.title,
                "text": chapter.text
            })

    return {"chapters": chapters_data}


@app.post("/api/copilot/summarize/text")
async def summarize_text_with_copilot(request: Request):
    """Summarize chapter text or a selected passage with Copilot SDK."""
    payload = await request.json()
    source = str(payload.get("source", "")).strip().lower()
    book_id = str(payload.get("book_id", "")).strip()

    chapter_index_raw = payload.get("chapter_index")
    chapter_index = None
    if chapter_index_raw is not None:
        chapter_index = int(chapter_index_raw)

    book = load_book_cached(book_id) if book_id else None
    chapter = _chapter_or_none(book, chapter_index)
    book_title = book.metadata.title if book else None
    chapter_title = chapter.title if chapter else None

    if source == "selection":
        text = str(payload.get("selected_text", "")).strip()
        if not text:
            raise HTTPException(
                status_code=400,
                detail="Selected text is required for selection summaries",
            )
    elif source == "chapter":
        if not book:
            raise HTTPException(status_code=404, detail="Book not found")
        if chapter is None:
            raise HTTPException(status_code=404, detail="Chapter not found")
        text = str(chapter.text or "").strip()
        if not text:
            raise HTTPException(
                status_code=400,
                detail="Chapter text is empty and cannot be summarized",
            )
    else:
        raise HTTPException(status_code=400, detail="Invalid summary source")

    try:
        summary = await copilot_summary_service.summarize_text(
            text,
            scope=source,
            book_title=book_title,
            chapter_title=chapter_title,
        )
    except CopilotSummaryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "summary": summary,
        "source": source,
        "book_id": book_id or None,
        "chapter_index": chapter_index,
    }


@app.post("/api/copilot/summarize/image")
async def summarize_image_with_copilot(request: Request):
    """Summarize an EPUB image or rendered PDF page with Copilot SDK."""
    payload = await request.json()
    source = str(payload.get("source", "")).strip().lower()
    book_id = str(payload.get("book_id", "")).strip()

    if not book_id:
        raise HTTPException(status_code=400, detail="book_id is required")

    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    status = await copilot_summary_service.get_status()
    if not status.get("available"):
        raise HTTPException(
            status_code=503,
            detail=status.get("error") or "Copilot summaries are unavailable",
        )
    if status.get("supports_vision") is False:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Configured model '{status['model']}' does not support image summaries"
            ),
        )

    if source == "epub":
        image_name = str(payload.get("image_name", "")).strip()
        if not image_name:
            raise HTTPException(status_code=400, detail="image_name is required")

        chapter_index_raw = payload.get("chapter_index")
        chapter_index = int(chapter_index_raw) if chapter_index_raw is not None else None
        chapter = _chapter_or_none(book, chapter_index)
        image_path = _resolve_book_image_path(book_id, image_name)
        if not os.path.exists(image_path):
            raise HTTPException(status_code=404, detail="Image not found")

        try:
            summary = await copilot_summary_service.summarize_image_file(
                image_path,
                book_title=book.metadata.title,
                chapter_title=chapter.title if chapter else None,
            )
        except CopilotSummaryError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        return {
            "summary": summary,
            "source": source,
            "book_id": book_id,
            "image_name": os.path.basename(image_name),
        }

    if source == "pdf":
        page_index_raw = payload.get("page_index")
        if page_index_raw is None:
            raise HTTPException(status_code=400, detail="page_index is required")

        page_index = int(page_index_raw)
        image_bytes = _render_pdf_page_image_bytes(book_id, page_index)
        display_name = f"{os.path.basename(book_id)}-page-{page_index + 1}.png"

        try:
            summary = await copilot_summary_service.summarize_image_blob(
                image_bytes,
                mime_type="image/png",
                display_name=display_name,
                book_title=book.metadata.title,
                chapter_title=f"Page {page_index + 1}",
            )
        except CopilotSummaryError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        return {
            "summary": summary,
            "source": source,
            "book_id": book_id,
            "page_index": page_index,
        }

    raise HTTPException(status_code=400, detail="Invalid image summary source")


@app.get("/read/{book_id}/images/{image_name}")
async def serve_image(book_id: str, image_name: str):
    """
    Serves images specifically for a book.
    The HTML contains <img src="images/pic.jpg">.
    The browser resolves this to /read/{book_id}/images/pic.jpg.
    """
    # Security check: ensure book_id is clean
    safe_book_id = os.path.basename(book_id)
    safe_image_name = os.path.basename(image_name)

    img_path = os.path.join(BOOKS_DIR, safe_book_id, "images", safe_image_name)

    if not os.path.exists(img_path):
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(img_path)


@app.get("/api/pdf/{book_id}/page-image/{page_num}")
async def render_pdf_page_image(
    book_id: str,
    page_num: int,
    dpi: int = PDF_COPY_IMAGE_DPI,
):
    """Render a PDF page on demand as a PNG for clipboard/export workflows."""
    image_bytes = _render_pdf_page_image_bytes(book_id, page_num, dpi=dpi)
    return Response(content=image_bytes, media_type="image/png")


@app.delete("/delete/{book_id}")
async def delete_book(book_id: str):
    """
    Deletes a book folder and all its contents.
    """
    # Security: ensure book_id is clean and ends with _data
    safe_book_id = os.path.basename(book_id)
    if not safe_book_id.endswith("_data"):
        raise HTTPException(status_code=400, detail="Invalid book ID")

    book_path = os.path.join(BOOKS_DIR, safe_book_id)

    if not os.path.exists(book_path):
        raise HTTPException(status_code=404, detail="Book not found")

    try:
        # Remove the entire book directory
        shutil.rmtree(book_path)
        # Clear the cache
        load_book_cached.cache_clear()
        get_cached_reading_times.cache_clear()
        load_book_metadata.cache_clear()
        # Clean up user data for this book
        user_data_manager.cleanup_book_data(safe_book_id)
        # Remove book from all collections
        user_data_manager.cleanup_collection_books(safe_book_id)
        return {"status": "deleted"}
    except Exception as e:
        logger.error("Error deleting book %s: %s", safe_book_id, e)
        raise HTTPException(
            status_code=500, detail=f"Failed to delete book: {str(e)}"
        )


@app.post("/api/reprocess/{book_id}")
async def reprocess_pdf(book_id: str):
    """
    Reprocess a PDF book with the latest rendering method.
    This is needed for PDFs that were processed with old text-based rendering.
    """
    safe_book_id = os.path.basename(book_id)
    if not safe_book_id.endswith("_data"):
        raise HTTPException(status_code=400, detail="Invalid book ID")

    book = load_book_cached(safe_book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if not book.is_pdf:
        raise HTTPException(status_code=400, detail="Only PDF books can be reprocessed")

    # Find the original PDF file
    pdf_name = safe_book_id.replace("_data", ".pdf")
    pdf_path = os.path.join(BOOKS_DIR, pdf_name)

    if not os.path.exists(pdf_path):
        raise HTTPException(
            status_code=400,
            detail="Original PDF not found. Please re-upload the PDF."
        )

    try:
        from reader3 import process_pdf

        book_path = os.path.join(BOOKS_DIR, safe_book_id)

        # Reprocess the PDF
        book_obj = process_pdf(pdf_path, book_path)
        save_to_pickle(book_obj, book_path)

        # Clear cache
        load_book_cached.cache_clear()
        get_cached_reading_times.cache_clear()
        load_book_metadata.cache_clear()

        return {"status": "success", "message": "PDF reprocessed successfully"}
    except Exception as e:
        logger.error("Error reprocessing PDF %s: %s", safe_book_id, e)
        raise HTTPException(
            status_code=500, detail=f"Failed to reprocess PDF: {str(e)}"
        )


# ============================================================================
# Chapter Reading Time API
# ============================================================================


@app.get("/api/reading-times/{book_id}")
async def get_chapter_reading_times(book_id: str):
    """Get estimated reading times for all chapters in a book."""
    reading_times = get_cached_reading_times(book_id)
    if reading_times is None:
        raise HTTPException(status_code=404, detail="Book not found")

    return {"book_id": book_id, "reading_times": reading_times}


# ============================================================================
# Reading Progress API
# ============================================================================


@app.get("/api/recently-read")
async def get_recently_read_books(limit: int = 5):
    """Get recently read books sorted by last_read time."""
    recently_read = []
    
    # Scan all book folders
    if os.path.exists(BOOKS_DIR):
        for item in os.listdir(BOOKS_DIR):
            if item.endswith("_data") and os.path.isdir(os.path.join(BOOKS_DIR, item)):
                progress = user_data_manager.get_progress(item)
                if progress and progress.last_read:
                    meta = load_book_metadata(item)
                    if meta:
                        # Calculate progress percentage
                        chapter_progress = user_data_manager.get_chapter_progress(item)
                        overall_progress = 0.0
                        total_chapters = meta.get("chapters", 0)
                        if chapter_progress and total_chapters > 0:
                            total_progress = sum(chapter_progress.values())
                            overall_progress = total_progress / total_chapters
                        
                        recently_read.append({
                            "id": item,
                            "title": meta.get("title", "Untitled"),
                            "author": ", ".join(meta.get("authors", [])),
                            "cover_image": meta.get("cover_image"),
                            "last_read": progress.last_read,
                            "chapter_index": progress.chapter_index,
                            "progress_percent": overall_progress,
                            "reading_time_seconds": progress.reading_time_seconds,
                        })
    
    # Sort by last_read descending
    recently_read.sort(key=lambda x: x["last_read"], reverse=True)
    
    return {"books": recently_read[:limit]}


@app.get("/api/progress/{book_id}")
async def get_reading_progress(book_id: str):
    """Get reading progress for a book."""
    progress = user_data_manager.get_progress(book_id)
    chapter_progress = user_data_manager.get_chapter_progress(book_id)
    
    # Calculate overall progress percentage from chapter progress
    overall_progress = 0.0
    if chapter_progress:
        # Use metadata if available to avoid loading full book
        meta = load_book_metadata(book_id)
        total_chapters = meta.get("chapters", 0) if meta else 0
        if total_chapters > 0:
            total_progress = sum(chapter_progress.values())
            overall_progress = total_progress / total_chapters
        else:
            # Fallback: average of recorded chapters
            overall_progress = sum(chapter_progress.values()) / len(chapter_progress)
    
    if progress:
        return {
            "book_id": progress.book_id,
            "chapter_index": progress.chapter_index,
            "scroll_position": progress.scroll_position,
            "last_read": progress.last_read,
            "total_chapters": progress.total_chapters,
            "reading_time_seconds": progress.reading_time_seconds,
            "progress_percent": overall_progress,
        }
    return {
        "book_id": book_id,
        "chapter_index": 0,
        "scroll_position": 0.0,
        "progress_percent": overall_progress,
    }


@app.post("/api/progress/{book_id}")
async def save_reading_progress(book_id: str, request: Request):
    """Save reading progress for a book."""
    data = await request.json()

    progress_percent = data.get("progress_percent")

    progress = ReadingProgress(
        book_id=book_id,
        chapter_index=data.get("chapter_index", 0),
        scroll_position=data.get("scroll_position", 0.0),
        total_chapters=data.get("total_chapters", 0),
        reading_time_seconds=data.get("reading_time_seconds", 0),
    )
    user_data_manager.save_progress(progress)

    if progress_percent is not None:
        user_data_manager.save_chapter_progress(
            book_id, progress.chapter_index, progress_percent
        )
    return {"status": "saved"}


# ============================================================================
# Bookmarks API
# ============================================================================


@app.get("/api/bookmarks/{book_id}")
async def get_bookmarks(book_id: str):
    """Get all bookmarks for a book."""
    bookmarks = user_data_manager.get_bookmarks(book_id)
    return {
        "book_id": book_id,
        "bookmarks": [
            {
                "id": b.id,
                "chapter_index": b.chapter_index,
                "scroll_position": b.scroll_position,
                "title": b.title,
                "note": b.note,
                "created_at": b.created_at,
            }
            for b in bookmarks
        ],
    }


@app.post("/api/bookmarks/{book_id}")
async def add_bookmark(book_id: str, request: Request):
    """Add a bookmark."""
    data = await request.json()

    bookmark = Bookmark(
        id=generate_id(),
        book_id=book_id,
        chapter_index=data.get("chapter_index", 0),
        scroll_position=data.get("scroll_position", 0.0),
        title=data.get("title", "Bookmark"),
        note=data.get("note"),
    )
    user_data_manager.add_bookmark(bookmark)
    return {"id": bookmark.id, "status": "created"}


@app.delete("/api/bookmarks/{book_id}/{bookmark_id}")
async def delete_bookmark(book_id: str, bookmark_id: str):
    """Delete a bookmark."""
    if user_data_manager.delete_bookmark(book_id, bookmark_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Bookmark not found")


@app.put("/api/bookmarks/{book_id}/{bookmark_id}")
async def update_bookmark(book_id: str, bookmark_id: str, request: Request):
    """Update a bookmark's note."""
    data = await request.json()
    note = data.get("note", "")

    if user_data_manager.update_bookmark_note(book_id, bookmark_id, note):
        return {"status": "updated"}
    raise HTTPException(status_code=404, detail="Bookmark not found")


# ============================================================================
# Highlights API
# ============================================================================


@app.get("/api/highlights/{book_id}")
async def get_highlights(book_id: str, chapter: int = None):
    """Get highlights for a book, optionally filtered by chapter."""
    highlights = user_data_manager.get_highlights(book_id, chapter)
    return {
        "book_id": book_id,
        "highlights": [
            {
                "id": h.id,
                "chapter_index": h.chapter_index,
                "text": h.text,
                "color": h.color,
                "note": h.note,
                "start_offset": h.start_offset,
                "end_offset": h.end_offset,
                "created_at": h.created_at,
            }
            for h in highlights
        ],
    }


@app.post("/api/highlights/{book_id}")
async def add_highlight(book_id: str, request: Request):
    """Add a highlight."""
    data = await request.json()

    highlight = Highlight(
        id=generate_id(),
        book_id=book_id,
        chapter_index=data.get("chapter_index", 0),
        text=data.get("text", ""),
        color=data.get("color", "yellow"),
        note=data.get("note"),
        start_offset=data.get("start_offset", 0),
        end_offset=data.get("end_offset", 0),
    )
    user_data_manager.add_highlight(highlight)
    return {"id": highlight.id, "status": "created"}


@app.delete("/api/highlights/{book_id}/{highlight_id}")
async def delete_highlight(book_id: str, highlight_id: str):
    """Delete a highlight."""
    if user_data_manager.delete_highlight(book_id, highlight_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Highlight not found")


@app.put("/api/highlights/{book_id}/{highlight_id}")
async def update_highlight(book_id: str, highlight_id: str, request: Request):
    """Update a highlight's note."""
    data = await request.json()
    note = data.get("note", "")

    if user_data_manager.update_highlight_note(book_id, highlight_id, note):
        return {"status": "updated"}
    raise HTTPException(status_code=404, detail="Highlight not found")


@app.put("/api/highlights/{book_id}/{highlight_id}/color")
async def update_highlight_color(book_id: str, highlight_id: str, request: Request):
    """Update a highlight's color."""
    data = await request.json()
    color = data.get("color", "yellow")

    if user_data_manager.update_highlight_color(book_id, highlight_id, color):
        return {"status": "updated"}
    raise HTTPException(status_code=404, detail="Highlight not found")


# ============================================================================
# Search API
# ============================================================================


def get_all_book_ids():
    """Get list of all book IDs in the library."""
    book_ids = []
    if os.path.exists(BOOKS_DIR):
        for item in os.listdir(BOOKS_DIR):
            item_path = os.path.join(BOOKS_DIR, item)
            if item.endswith("_data") and os.path.isdir(item_path):
                pkl_path = os.path.join(item_path, "book.pkl")
                if os.path.exists(pkl_path):
                    book_ids.append(item)
    return book_ids


@app.get("/api/search")
async def search_books(q: str, book_id: str = None, mode: str = "exact"):
    """
    Search for text across all books or within a specific book.
    Supports "exact" (full-text) and "semantic" ranking modes.
    """
    if not q or len(q) < 2:
        return {"results": [], "query": q, "total": 0, "mode": mode}

    # Total results limit (allow more to show all instances)
    max_total_results = 500

    # Determine which books to search
    book_ids = [book_id] if book_id else get_all_book_ids()

    def _do_search():
        """Run the actual search off the event loop."""
        results = []
        query_lower = q.lower()

        if mode == "semantic":
            return semantic_search_books(
                query=q,
                book_ids=book_ids,
                books_dir=BOOKS_DIR,
                load_book_fn=load_book_cached,
                limit=max_total_results,
            )

        for bid in book_ids:
            if len(results) >= max_total_results:
                break

            book = load_book_cached(bid)
            if not book:
                continue

            book_title = book.metadata.title

            for idx, chapter in enumerate(book.spine):
                if len(results) >= max_total_results:
                    break

                text = getattr(chapter, "text", "") or ""
                if not text:
                    continue

                text_lower = text.lower()
                if query_lower not in text_lower:
                    continue

                start = 0
                while True:
                    pos = text_lower.find(query_lower, start)
                    if pos == -1:
                        break

                    context_start = max(0, pos - 100)
                    context_end = min(len(text), pos + len(q) + 100)
                    context = text[context_start:context_end]

                    if context_start > 0:
                        space_idx = context.find(" ")
                        if space_idx > 0 and space_idx < 30:
                            context = context[space_idx + 1:]
                        context = "..." + context
                    if context_end < len(text):
                        space_idx = context.rfind(" ")
                        if space_idx > len(context) - 30:
                            context = context[:space_idx]
                        context = context + "..."

                    results.append({
                        "book_id": bid,
                        "book_title": book_title,
                        "chapter_index": idx,
                        "chapter_href": chapter.href,
                        "chapter_title": chapter.title,
                        "context": context.strip(),
                        "position": pos,
                        "match_length": len(q),
                    })

                    if len(results) >= max_total_results:
                        break
                    start = pos + len(q)

        return results

    results = await _run_sync(_do_search)

    # Record search in history
    search_query = SearchQuery(
        query=q, book_id=book_id, results_count=len(results)
    )
    user_data_manager.add_search(search_query)

    return {"query": q, "results": results, "total": len(results), "mode": mode}


@app.get("/api/search/history")
async def get_search_history(limit: int = 20):
    """Get recent search history."""
    history = user_data_manager.get_search_history(limit)
    return {
        "history": [
            {
                "query": h.query,
                "book_id": h.book_id,
                "timestamp": h.timestamp,
                "results_count": h.results_count,
            }
            for h in history
        ]
    }


@app.delete("/api/search/history")
async def clear_search_history():
    """Clear search history."""
    user_data_manager.clear_search_history()
    return {"status": "cleared"}


# ============================================================================
# Export API
# ============================================================================


@app.get("/api/export/{book_id}")
async def export_book_data(book_id: str, format: str = "json"):
    """Export highlights and bookmarks for a book."""
    if format not in ["json", "markdown"]:
        raise HTTPException(
            status_code=400, detail="Format must be 'json' or 'markdown'"
        )

    content = user_data_manager.export_book_data(book_id, format)

    if format == "markdown":
        return PlainTextResponse(
            content,
            media_type="text/markdown",
            headers={"Content-Disposition": f"attachment; filename={book_id}_notes.md"},
        )
    else:
        return PlainTextResponse(
            content,
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename={book_id}_notes.json"
            },
        )


@app.get("/api/export")
async def export_all_data():
    """Export all user data."""
    content = user_data_manager.export_all_data()
    return PlainTextResponse(
        content,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=reader3_backup.json"},
    )


# ============================================================================
# Chapter Progress API (per-chapter tracking)
# ============================================================================


@app.get("/api/chapter-progress/{book_id}")
async def get_chapter_progress(book_id: str):
    """Get reading progress for each chapter in a book."""
    progress = user_data_manager.get_chapter_progress(book_id)
    return {"book_id": book_id, "progress": progress}


@app.post("/api/chapter-progress/{book_id}/{chapter_index}")
async def save_chapter_progress(
    book_id: str,
    chapter_index: int,
    request: Request,
    progress: Optional[float] = None
):
    """Save reading progress for a specific chapter."""
    # Support both query parameter (for sendBeacon) and JSON body
    if progress is not None:
        progress_percent = progress
    else:
        try:
            data = await request.json()
            progress_percent = data.get("progress", 0)
        except Exception:
            progress_percent = 0
    
    user_data_manager.save_chapter_progress(
        book_id, chapter_index, progress_percent
    )
    return {"status": "saved"}


@app.get("/api/copied-pages/{book_id}")
async def get_copied_pages(book_id: str):
    """Get copied page indices (PDF) or chapter hrefs (EPUB) for a book."""
    items = user_data_manager.get_copied_pages(book_id)
    return {"book_id": book_id, "items": items}


@app.post("/api/copied-pages/{book_id}")
async def save_copied_pages(book_id: str, request: Request):
    """Save copied page indices or chapter hrefs for a book."""
    data = await request.json()
    items = data.get("items", [])
    user_data_manager.save_copied_pages(book_id, items)
    return {"status": "saved"}


# ============================================================================
# PDF-Specific API Endpoints
# ============================================================================


@app.get("/api/pdf/{book_id}/stats")
async def get_pdf_stats(book_id: str):
    """
    Get comprehensive statistics about a PDF book.
    Includes page count, word count, annotations, images, reading time.
    """
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if not book.is_pdf:
        raise HTTPException(status_code=400, detail="Not a PDF book")

    stats = get_pdf_page_stats(book)
    return {"book_id": book_id, **stats}


@app.get("/api/pdf/{book_id}/thumbnails")
async def list_pdf_thumbnails(book_id: str):
    """
    List all available thumbnails for a PDF book.
    Returns array of thumbnail URLs.
    """
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if not book.is_pdf:
        raise HTTPException(status_code=400, detail="Not a PDF book")

    if not book.pdf_thumbnails_generated:
        return {"book_id": book_id, "thumbnails": [], "available": False}

    thumbnails = []
    for i in range(book.pdf_total_pages):
        thumbnails.append({
            "page": i,
            "url": f"/read/{book_id}/thumbnails/thumb_{i + 1}.png"
        })

    return {"book_id": book_id, "thumbnails": thumbnails, "available": True}


@app.get("/read/{book_id}/thumbnails/{thumb_name}")
async def serve_thumbnail(book_id: str, thumb_name: str):
    """Serve a PDF page thumbnail image."""
    safe_book_id = os.path.basename(book_id)
    safe_thumb_name = os.path.basename(thumb_name)

    thumb_path = os.path.join(
        BOOKS_DIR, safe_book_id, "thumbnails", safe_thumb_name
    )

    if not os.path.exists(thumb_path):
        raise HTTPException(status_code=404, detail="Thumbnail not found")

    return FileResponse(thumb_path, media_type="image/png")


@app.get("/api/pdf/{book_id}/annotations")
async def get_pdf_annotations(book_id: str, page: int = None):
    """
    Get annotations from a PDF book.
    Optionally filter by page number.
    """
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if not book.is_pdf:
        raise HTTPException(status_code=400, detail="Not a PDF book")

    annotations = []
    pages_to_check = (
        [page] if page is not None
        else range(book.pdf_total_pages)
    )

    for page_num in pages_to_check:
        if page_num in book.pdf_page_data:
            page_data = book.pdf_page_data[page_num]
            for annot in page_data.annotations:
                annotations.append({
                    "page": annot.page,
                    "type": annot.type,
                    "content": annot.content,
                    "rect": annot.rect,
                    "color": annot.color,
                    "author": annot.author,
                    "created": annot.created
                })

    return {
        "book_id": book_id,
        "annotations": annotations,
        "total": len(annotations)
    }


@app.get("/api/pdf/{book_id}/search-positions")
async def search_pdf_positions(book_id: str, q: str, page: int = None):
    """
    Search for text in a PDF and return positions for highlighting.
    Returns bounding box coordinates for each match.
    """
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if not book.is_pdf:
        raise HTTPException(status_code=400, detail="Not a PDF book")

    if not q or len(q) < 2:
        return {"query": q, "results": [], "total": 0}

    results = search_pdf_text_positions(book, q, page)

    return {
        "query": q,
        "book_id": book_id,
        "results": results[:100],  # Limit results
        "total": len(results)
    }


@app.get("/api/pdf/{book_id}/page/{page_num}")
async def get_pdf_page_info(book_id: str, page_num: int):
    """
    Get detailed information about a specific PDF page.
    Includes dimensions, rotation, word count, annotations.
    """
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if not book.is_pdf:
        raise HTTPException(status_code=400, detail="Not a PDF book")

    if page_num < 0 or page_num >= book.pdf_total_pages:
        raise HTTPException(status_code=404, detail="Page not found")

    if page_num not in book.pdf_page_data:
        return {
            "page": page_num,
            "available": False
        }

    page_data = book.pdf_page_data[page_num]
    return {
        "page": page_num,
        "available": True,
        "width": page_data.width,
        "height": page_data.height,
        "rotation": page_data.rotation,
        "word_count": page_data.word_count,
        "has_images": page_data.has_images,
        "annotation_count": len(page_data.annotations),
        "text_block_count": 0  # Text blocks now extracted on-demand
    }


@app.get("/api/pdf/{book_id}/outline")
async def get_pdf_outline(book_id: str):
    """
    Get the PDF's table of contents/outline structure.
    Returns the hierarchical TOC if available.
    """
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if not book.is_pdf:
        raise HTTPException(status_code=400, detail="Not a PDF book")

    def toc_to_dict(entries):
        result = []
        for entry in entries:
            item = {
                "title": entry.title,
                "href": entry.href,
                "page": int(entry.href.replace("page_", "")) - 1
                if entry.href.startswith("page_") else 0
            }
            if entry.children:
                item["children"] = toc_to_dict(entry.children)
            result.append(item)
        return result

    return {
        "book_id": book_id,
        "has_native_toc": book.pdf_has_toc,
        "outline": toc_to_dict(book.toc)
    }


@app.post("/api/pdf/{book_id}/export")
async def export_pdf_pages_endpoint(book_id: str, request: Request):
    """
    Export a range of pages from a PDF to a new PDF file.
    Request body: { "start_page": 0, "end_page": 10 }
    """
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if not book.is_pdf:
        raise HTTPException(status_code=400, detail="Not a PDF book")

    data = await request.json()
    start_page = data.get("start_page", 0)
    end_page = data.get("end_page", book.pdf_total_pages - 1)

    # Validate range
    start_page = max(0, start_page)
    end_page = min(end_page, book.pdf_total_pages - 1)

    if start_page > end_page:
        raise HTTPException(
            status_code=400,
            detail="start_page must be less than or equal to end_page"
        )

    # We need the original PDF file to export
    # Check if it exists in the uploads or can be reconstructed
    original_pdf = None
    possible_paths = [
        os.path.join(BOOKS_DIR, book.source_file),
        os.path.join(BOOKS_DIR, book_id.replace("_data", ".pdf")),
    ]

    for path in possible_paths:
        if os.path.exists(path):
            original_pdf = path
            break

    if not original_pdf:
        raise HTTPException(
            status_code=400,
            detail="Original PDF not found. Export requires the source PDF."
        )

    # Create export in a temp location
    import tempfile

    from reader3 import export_pdf_pages

    with tempfile.NamedTemporaryFile(
        delete=False, suffix=".pdf"
    ) as tmp:
        export_path = tmp.name

    success = export_pdf_pages(
        book, export_path, start_page, end_page, original_pdf
    )

    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to export PDF pages"
        )

    # Return the file
    filename = f"{book_id}_pages_{start_page + 1}-{end_page + 1}.pdf"
    return FileResponse(
        export_path,
        media_type="application/pdf",
        filename=filename,
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@app.get("/api/pdf/{book_id}/text-layer/{page_num}")
async def get_pdf_text_layer(book_id: str, page_num: int):
    """
    Get the text layer (positioned text blocks) for a PDF page.
    Useful for implementing accurate text selection and highlighting.
    
    Text blocks are now extracted on-demand from the source PDF
    to reduce pickle file size and memory usage.
    """
    from reader3 import get_pdf_text_blocks_for_page
    
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if not book.is_pdf:
        raise HTTPException(status_code=400, detail="Not a PDF book")

    if page_num < 0 or page_num >= book.pdf_total_pages:
        raise HTTPException(status_code=404, detail="Page not found")

    # Get page dimensions from stored data
    page_data = book.pdf_page_data.get(page_num)
    width = page_data.width if page_data else 0
    height = page_data.height if page_data else 0
    
    # Extract text blocks on-demand from source PDF
    book_dir = os.path.join(BOOKS_DIR, book_id)
    text_blocks = get_pdf_text_blocks_for_page(book, page_num, book_dir)
    
    blocks = [
        {
            "text": b.text,
            "x0": b.x0,
            "y0": b.y0,
            "x1": b.x1,
            "y1": b.y1,
            "block_no": b.block_no,
            "line_no": b.line_no,
            "word_no": b.word_no
        }
        for b in text_blocks
    ]

    return {
        "page": page_num,
        "width": width,
        "height": height,
        "text_blocks": blocks
    }


# ============================================================================
# Reading Sessions API
# ============================================================================


@app.post("/api/sessions/start")
async def start_reading_session(request: Request):
    """Start a new reading session."""
    data = await request.json()
    
    session = ReadingSession(
        id=generate_id(),
        book_id=data.get("book_id", ""),
        book_title=data.get("book_title", ""),
        chapter_index=data.get("chapter_index", 0),
        chapter_title=data.get("chapter_title", ""),
    )
    user_data_manager.start_reading_session(session)
    return {"session_id": session.id, "status": "started"}


@app.post("/api/sessions/{session_id}/end")
async def end_reading_session(session_id: str, request: Request):
    """End a reading session."""
    data = await request.json()
    
    success = user_data_manager.end_reading_session(
        session_id=session_id,
        duration_seconds=data.get("duration_seconds", 0),
        pages_read=data.get("pages_read", 0),
        scroll_position=data.get("scroll_position", 0.0)
    )
    
    if success:
        return {"status": "ended"}
    raise HTTPException(status_code=404, detail="Session not found")


@app.get("/api/sessions")
async def get_reading_sessions(book_id: str = None, limit: int = 20):
    """Get reading sessions."""
    sessions = user_data_manager.get_reading_sessions(book_id, limit)
    return {
        "sessions": [
            {
                "id": s.id,
                "book_id": s.book_id,
                "book_title": s.book_title,
                "chapter_index": s.chapter_index,
                "chapter_title": s.chapter_title,
                "start_time": s.start_time,
                "end_time": s.end_time,
                "duration_seconds": s.duration_seconds,
                "pages_read": s.pages_read,
            }
            for s in sessions
        ]
    }


@app.get("/api/sessions/stats")
async def get_reading_stats(book_id: str = None):
    """Get reading statistics."""
    stats = user_data_manager.get_reading_stats(book_id)
    return stats


# ============================================================================
# Vocabulary/Dictionary API
# ============================================================================


@app.get("/api/vocabulary/search")
async def search_vocabulary(q: str):
    """Search vocabulary words."""
    if not q or len(q) < 2:
        return {"results": [], "query": q}
    
    words = user_data_manager.search_vocabulary(q)
    return {
        "query": q,
        "results": [
            {
                "id": w.id,
                "book_id": w.book_id,
                "word": w.word,
                "definition": w.definition,
                "phonetic": w.phonetic,
                "part_of_speech": w.part_of_speech,
            }
            for w in words
        ]
    }


@app.post("/api/vocabulary/{book_id}")
async def add_vocabulary_word(book_id: str, request: Request):
    """Add a word to vocabulary."""
    data = await request.json()
    
    word = VocabularyWord(
        id=generate_id(),
        book_id=book_id,
        word=data.get("word", ""),
        definition=data.get("definition", ""),
        phonetic=data.get("phonetic"),
        part_of_speech=data.get("part_of_speech"),
        example=data.get("example"),
        chapter_index=data.get("chapter_index", 0),
        context=data.get("context", ""),
    )
    saved_word = user_data_manager.add_vocabulary_word(word)
    return {"id": saved_word.id, "status": "saved"}


@app.get("/api/vocabulary/{book_id}")
async def get_vocabulary(book_id: str):
    """Get vocabulary words for a book."""
    words = user_data_manager.get_vocabulary(book_id)
    return {
        "book_id": book_id,
        "words": [
            {
                "id": w.id,
                "word": w.word,
                "definition": w.definition,
                "phonetic": w.phonetic,
                "part_of_speech": w.part_of_speech,
                "example": w.example,
                "chapter_index": w.chapter_index,
                "context": w.context,
                "created_at": w.created_at,
                "reviewed_count": w.reviewed_count,
            }
            for w in words
        ]
    }


@app.get("/api/vocabulary")
async def get_all_vocabulary():
    """Get all vocabulary words across all books."""
    words = user_data_manager.get_vocabulary()
    return {
        "words": [
            {
                "id": w.id,
                "book_id": w.book_id,
                "word": w.word,
                "definition": w.definition,
                "phonetic": w.phonetic,
                "part_of_speech": w.part_of_speech,
                "example": w.example,
                "chapter_index": w.chapter_index,
                "context": w.context,
                "created_at": w.created_at,
                "reviewed_count": w.reviewed_count,
            }
            for w in words
        ]
    }


@app.delete("/api/vocabulary/{book_id}/{word_id}")
async def delete_vocabulary_word(book_id: str, word_id: str):
    """Delete a vocabulary word."""
    if user_data_manager.delete_vocabulary_word(book_id, word_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Word not found")


# ============================================================================
# Annotations API
# ============================================================================


@app.post("/api/annotations/{book_id}")
async def add_annotation(book_id: str, request: Request):
    """Add an annotation."""
    data = await request.json()
    
    annotation = Annotation(
        id=generate_id(),
        book_id=book_id,
        chapter_index=data.get("chapter_index", 0),
        note_text=data.get("note_text", ""),
        highlight_id=data.get("highlight_id"),
        bookmark_id=data.get("bookmark_id"),
        position_offset=data.get("position_offset", 0),
        tags=data.get("tags", []),
    )
    user_data_manager.add_annotation(annotation)
    return {"id": annotation.id, "status": "created"}


@app.get("/api/annotations/{book_id}")
async def get_annotations(book_id: str, chapter: int = None):
    """Get annotations for a book."""
    annotations = user_data_manager.get_annotations(book_id, chapter)
    return {
        "book_id": book_id,
        "annotations": [
            {
                "id": a.id,
                "chapter_index": a.chapter_index,
                "note_text": a.note_text,
                "highlight_id": a.highlight_id,
                "bookmark_id": a.bookmark_id,
                "position_offset": a.position_offset,
                "tags": a.tags,
                "created_at": a.created_at,
                "updated_at": a.updated_at,
            }
            for a in annotations
        ]
    }


@app.put("/api/annotations/{book_id}/{annotation_id}")
async def update_annotation(book_id: str, annotation_id: str, request: Request):
    """Update an annotation."""
    data = await request.json()
    
    success = user_data_manager.update_annotation(
        book_id=book_id,
        annotation_id=annotation_id,
        note_text=data.get("note_text", ""),
        tags=data.get("tags")
    )
    
    if success:
        return {"status": "updated"}
    raise HTTPException(status_code=404, detail="Annotation not found")


@app.delete("/api/annotations/{book_id}/{annotation_id}")
async def delete_annotation(book_id: str, annotation_id: str):
    """Delete an annotation."""
    if user_data_manager.delete_annotation(book_id, annotation_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Annotation not found")


@app.get("/api/annotations/{book_id}/search")
async def search_annotations(book_id: str, q: str):
    """Search annotations by text or tags."""
    if not q or len(q) < 2:
        return {"results": [], "query": q}
    
    annotations = user_data_manager.search_annotations(book_id, q)
    return {
        "query": q,
        "results": [
            {
                "id": a.id,
                "chapter_index": a.chapter_index,
                "note_text": a.note_text,
                "tags": a.tags,
                "created_at": a.created_at,
            }
            for a in annotations
        ]
    }


@app.get("/api/annotations/{book_id}/export")
async def export_annotations(book_id: str, format: str = "markdown"):
    """Export annotations to Markdown."""
    if format == "markdown":
        content = user_data_manager.export_annotations_markdown(book_id)
        return PlainTextResponse(
            content,
            media_type="text/markdown",
            headers={
                "Content-Disposition": 
                    f"attachment; filename={book_id}_annotations.md"
            }
        )
    else:
        # JSON export
        annotations = user_data_manager.get_annotations(book_id)
        import json
        content = json.dumps(
            {"annotations": [
                {
                    "id": a.id,
                    "chapter_index": a.chapter_index,
                    "note_text": a.note_text,
                    "tags": a.tags,
                    "created_at": a.created_at,
                }
                for a in annotations
            ]},
            indent=2
        )
        return PlainTextResponse(
            content,
            media_type="application/json",
            headers={
                "Content-Disposition":
                    f"attachment; filename={book_id}_annotations.json"
            }
        )


# ========== Collections API ==========

@app.get("/api/collections")
async def get_collections():
    """Get all collections."""
    collections = user_data_manager.get_collections()
    return {
        "collections": [
            {
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "icon": c.icon,
                "color": c.color,
                "book_count": len(c.book_ids),
                "book_ids": c.book_ids,
                "created_at": c.created_at,
                "updated_at": c.updated_at,
            }
            for c in collections
        ]
    }


@app.put("/api/collections/reorder")
async def reorder_collections(request: Request):
    """Reorder collections."""
    data = await request.json()
    collection_ids = data.get("collection_ids", [])
    
    user_data_manager.reorder_collections(collection_ids)
    return {"status": "reordered"}


@app.post("/api/collections")
async def create_collection(request: Request):
    """Create a new collection."""
    data = await request.json()
    name = data.get("name", "").strip()
    
    if not name:
        raise HTTPException(status_code=400, detail="Collection name is required")
    
    description = data.get("description", "")
    icon = data.get("icon", "folder")
    color = data.get("color", "#3498db")
    
    collection = user_data_manager.create_collection(
        name=name,
        description=description,
        icon=icon,
        color=color
    )
    
    return {
        "id": collection.id,
        "name": collection.name,
        "description": collection.description,
        "icon": collection.icon,
        "color": collection.color,
        "book_count": 0,
        "book_ids": [],
        "created_at": collection.created_at,
    }


@app.get("/api/collections/{collection_id}")
async def get_collection(collection_id: str):
    """Get a single collection."""
    collection = user_data_manager.get_collection(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
    
    return {
        "id": collection.id,
        "name": collection.name,
        "description": collection.description,
        "icon": collection.icon,
        "color": collection.color,
        "book_count": len(collection.book_ids),
        "book_ids": collection.book_ids,
        "created_at": collection.created_at,
        "updated_at": collection.updated_at,
    }


@app.put("/api/collections/{collection_id}")
async def update_collection(collection_id: str, request: Request):
    """Update a collection."""
    data = await request.json()
    
    success = user_data_manager.update_collection(
        collection_id=collection_id,
        name=data.get("name"),
        description=data.get("description"),
        icon=data.get("icon"),
        color=data.get("color")
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="Collection not found")
    
    # Return updated collection
    collection = user_data_manager.get_collection(collection_id)
    return {
        "id": collection.id,
        "name": collection.name,
        "description": collection.description,
        "icon": collection.icon,
        "color": collection.color,
        "book_count": len(collection.book_ids),
        "book_ids": collection.book_ids,
        "updated_at": collection.updated_at,
    }


@app.delete("/api/collections/{collection_id}")
async def delete_collection(collection_id: str):
    """Delete a collection."""
    if user_data_manager.delete_collection(collection_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Collection not found")


@app.post("/api/collections/{collection_id}/books/{book_id}")
async def add_book_to_collection(collection_id: str, book_id: str):
    """Add a book to a collection."""
    if user_data_manager.add_book_to_collection(collection_id, book_id):
        return {"status": "added", "collection_id": collection_id, "book_id": book_id}
    raise HTTPException(status_code=404, detail="Collection not found")


@app.delete("/api/collections/{collection_id}/books/{book_id}")
async def remove_book_from_collection(collection_id: str, book_id: str):
    """Remove a book from a collection."""
    if user_data_manager.remove_book_from_collection(collection_id, book_id):
        return {"status": "removed", "collection_id": collection_id, "book_id": book_id}
    raise HTTPException(status_code=404, detail="Collection not found")


@app.get("/api/books/{book_id}/collections")
async def get_book_collections(book_id: str):
    """Get all collections that contain a specific book."""
    collections = user_data_manager.get_book_collections(book_id)
    return {
        "book_id": book_id,
        "collections": [
            {
                "id": c.id,
                "name": c.name,
                "icon": c.icon,
                "color": c.color,
            }
            for c in collections
        ]
    }


@app.put("/api/books/{book_id}/collections")
async def set_book_collections(book_id: str, request: Request):
    """Set which collections a book belongs to."""
    data = await request.json()
    collection_ids = data.get("collection_ids", [])
    
    user_data_manager.set_book_collections(book_id, collection_ids)
    
    # Return updated list
    collections = user_data_manager.get_book_collections(book_id)
    return {
        "book_id": book_id,
        "collections": [
            {
                "id": c.id,
                "name": c.name,
                "icon": c.icon,
                "color": c.color,
            }
            for c in collections
        ]
    }


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", 8123))
    workers = int(os.environ.get("WEB_CONCURRENCY", 1))

    logger.info("Starting server at http://%s:%d (workers=%d)", host, port, workers)
    uvicorn.run(
        "server:app",
        host=host,
        port=port,
        workers=workers,
        log_level=os.environ.get("LOG_LEVEL", "info").lower(),
        timeout_keep_alive=30,
        limit_concurrency=100,
    )
