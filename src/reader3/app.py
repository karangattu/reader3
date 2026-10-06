import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

# ---------------------------------------------------------------------------
# Logging (must be configured before deps is imported)
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ---------------------------------------------------------------------------
# Import shared state from deps (single source of truth)
# ---------------------------------------------------------------------------
from .api.deps import (  # noqa: E402
    BOOKS_DIR,
    MAX_UPLOAD_BYTES,
    # Constants
    MAX_UPLOAD_MB,
    PDF_COPY_IMAGE_DPI,
    PDF_COPY_IMAGE_DPI_OPTIONS,
    PDF_COPY_IMAGE_MAX_DPI,
    VALID_READER_FONTS,
    VALID_READER_THEMES,
    Book,
    _book_image_exists,
    _book_image_url,
    _build_library_entry,
    _chapter_or_none,
    # Helpers
    _clamp_pdf_copy_image_dpi,
    _compute_progress_percent,
    _effective_pdf_copy_image_dpi,
    _find_active_upload,
    _find_duplicate_book_by_hash,
    _format_pdf_validation_error,
    _io_executor,
    _pdf_copy_image_dpi_options,
    _pdf_thumbnails_enabled,
    _persist_upload_metadata,
    _process_pdf,
    _progress_status_label,
    _render_pdf_page_image_bytes,
    _resolve_book_image_path,
    _rewrite_reader_content_asset_paths,
    _run_sync,
    _serialize_reader_preferences,
    _url_path_basename,
    cleanup_old_statuses,
    get_all_book_ids,
    get_cached_reading_times,
    get_reader_service,
    get_search_service,
    # Re-export commonly used names so backward-compat shims keep working
    load_book_cached,
    load_book_metadata,
    logger,
    static_dir,
    templates,
    templates_dir,
    update_upload_status,
    upload_status,
    upload_status_lock,
    user_data_manager,
    write_book_metadata,
)
from .api.routes.upload import process_book_background  # noqa: E402
from .services.library import save_to_pickle, validate_pdf  # noqa: E402

__all__ = [
    "app",
    "run",
    "SecurityHeadersMiddleware",
    "validate_pdf",
    "save_to_pickle",
    "process_book_background",
    "logger",
    "BOOKS_DIR",
    "_io_executor",
    "user_data_manager",
    "templates",
    "templates_dir",
    "static_dir",
    "load_book_cached",
    "load_book_metadata",
    "write_book_metadata",
    "get_cached_reading_times",
    "get_all_book_ids",
    "get_reader_service",
    "get_search_service",
    "_run_sync",
    "upload_status",
    "upload_status_lock",
    "update_upload_status",
    "cleanup_old_statuses",
    "_process_pdf",
    "MAX_UPLOAD_MB",
    "MAX_UPLOAD_BYTES",
    "VALID_READER_THEMES",
    "VALID_READER_FONTS",
    "PDF_COPY_IMAGE_DPI",
    "PDF_COPY_IMAGE_MAX_DPI",
    "PDF_COPY_IMAGE_DPI_OPTIONS",
    "_clamp_pdf_copy_image_dpi",
    "_pdf_copy_image_dpi_options",
    "_pdf_thumbnails_enabled",
    "_format_pdf_validation_error",
    "_compute_progress_percent",
    "_progress_status_label",
    "_persist_upload_metadata",
    "_find_duplicate_book_by_hash",
    "_find_active_upload",
    "_build_library_entry",
    "_effective_pdf_copy_image_dpi",
    "_serialize_reader_preferences",
    "_chapter_or_none",
    "_resolve_book_image_path",
    "_url_path_basename",
    "_book_image_url",
    "_book_image_exists",
    "_rewrite_reader_content_asset_paths",
    "_render_pdf_page_image_bytes",
    "Book",
]


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
# Cache-Control middleware for static assets (expanded)
# ---------------------------------------------------------------------------
class CacheControlMiddleware(BaseHTTPMiddleware):
    """Adds Cache-Control headers for images, thumbnails, and stable API data."""

    # Paths that benefit from aggressive caching (immutable book assets)
    STATIC_PREFIXES = ("/read/", "/static/")
    STATIC_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".woff2", ".woff", ".ttf", ".css")

    # API responses for data that is immutable once a book is processed
    IMMUTABLE_API_PREFIXES = (
        "/api/v1/pdf/",  # stats, outline, thumbnails list
    )
    IMMUTABLE_API_SUFFIXES = (
        "/stats",
        "/outline",
        "/thumbnails",
    )

    # API responses that change slowly (1 hour cache)
    SLOW_CHANGE_API_PREFIXES = (
        "/api/v1/reading-times/",
    )

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path

        # Book images and thumbnails — immutable, cache 1 year
        if any(path.startswith(p) for p in self.STATIC_PREFIXES) and any(
            path.endswith(s) for s in self.STATIC_SUFFIXES
        ):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        # Cover images — may change if book is reprocessed, cache 24h
        elif path.startswith("/cover/"):
            response.headers["Cache-Control"] = "public, max-age=86400"
            # Add ETag based on file mod time for conditional requests
            # (the actual file serving in the route handles this)
        # Immutable PDF API data (stats, outline, thumbnails list)
        elif any(path.startswith(p) for p in self.IMMUTABLE_API_PREFIXES) and any(
            path.endswith(s) for s in self.IMMUTABLE_API_SUFFIXES
        ):
            response.headers["Cache-Control"] = "public, max-age=3600"
        # Reading times — stable but may change if book is reprocessed
        elif any(path.startswith(p) for p in self.SLOW_CHANGE_API_PREFIXES):
            response.headers["Cache-Control"] = "public, max-age=3600"

        return response


# ---------------------------------------------------------------------------
# Lifespan: startup / shutdown hooks
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Reader3 starting up")
    yield
    logger.info("Reader3 shutting down – flushing user data")
    user_data_manager.flush()
    _io_executor.shutdown(wait=False)


app = FastAPI(
    lifespan=lifespan,
)

# --- Middleware (applied bottom-to-top, so GZip wraps everything) ---
app.add_middleware(CacheControlMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=500, compresslevel=6)

# Serve bundled static assets (self-hosted reading fonts, etc.).
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

logger.info("Current working directory: %s", os.getcwd())


# ---------------------------------------------------------------------------
# Route includes
# ---------------------------------------------------------------------------
from .api.routes import annotations as annotations_routes  # noqa: E402
from .api.routes import library as library_routes  # noqa: E402
from .api.routes import pdf as pdf_routes  # noqa: E402
from .api.routes import preferences as preferences_routes  # noqa: E402
from .api.routes import progress as progress_routes  # noqa: E402
from .api.routes import reader as reader_routes  # noqa: E402
from .api.routes import search as search_routes  # noqa: E402
from .api.routes import sessions as sessions_routes  # noqa: E402
from .api.routes import upload as upload_routes  # noqa: E402

app.include_router(library_routes.router)
app.include_router(upload_routes.router)
app.include_router(reader_routes.router)
app.include_router(search_routes.router)
app.include_router(preferences_routes.router)
app.include_router(pdf_routes.router)
app.include_router(progress_routes.router)
app.include_router(sessions_routes.router)
app.include_router(annotations_routes.router)


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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def run():
    """Run the Reader3 FastAPI app with uvicorn."""
    import uvicorn

    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", 8123))
    workers = int(os.environ.get("WEB_CONCURRENCY", 1))

    logger.info("Starting server at http://%s:%d (workers=%d)", host, port, workers)
    uvicorn.run(
        "reader3.app:app",
        host=host,
        port=port,
        workers=workers,
        log_level=os.environ.get("LOG_LEVEL", "info").lower(),
        timeout_keep_alive=30,
        limit_concurrency=100,
    )


if __name__ == "__main__":
    run()
