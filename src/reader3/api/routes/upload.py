"""Upload API routes."""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
import threading
import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse

from reader3.api.deps import (
    BOOKS_DIR,
    MAX_UPLOAD_BYTES,
    MAX_UPLOAD_MB,
    _find_active_upload,
    _find_duplicate_book_by_hash,
    _format_pdf_validation_error,
    _pdf_thumbnails_enabled,
    _persist_upload_metadata,
    _process_pdf,
    clear_rewrite_cache,
    cleanup_old_statuses,
    get_cached_reading_times,
    load_book_cached,
    load_book_metadata,
    logger,
    update_upload_status,
    upload_status,
    upload_status_lock,
)
from reader3.services.library import (
    process_epub,
    save_to_json,
    validate_pdf,
)

router = APIRouter()

# Tracks in-flight background processing threads so shutdown can wait for them.
_background_threads: set[threading.Thread] = set()
_background_threads_lock = threading.Lock()


def get_active_background_threads() -> list[threading.Thread]:
    """Return the currently live background processing threads."""
    with _background_threads_lock:
        return [thread for thread in _background_threads if thread.is_alive()]


def _call_validate_pdf(temp_path: str):
    server_mod = sys.modules.get("server")
    if server_mod and hasattr(server_mod, "validate_pdf"):
        return server_mod.validate_pdf(temp_path)
    return validate_pdf(temp_path)


def _call_save_to_json(book_obj, full_out_dir):
    server_mod = sys.modules.get("server")
    if server_mod and hasattr(server_mod, "save_to_json"):
        return server_mod.save_to_json(book_obj, full_out_dir)
    return save_to_json(book_obj, full_out_dir)


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
        def progress_callback(progress: float, message: str = ""):
            if not upload_id:
                return
            update_upload_status(
                upload_id,
                status="processing",
                progress=max(10, min(95, int(progress))),
                message=message,
            )

        if suffix == ".pdf":
            validation = _call_validate_pdf(temp_path)
            if not validation["valid"]:
                raise ValueError(_format_pdf_validation_error(validation["error"]))
            update_upload_status(upload_id, progress=20, message="Preparing PDF import...")
            book_obj = _process_pdf(
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
        _call_save_to_json(book_obj, full_out_dir)
        if source_hash:
            _persist_upload_metadata(full_out_dir, source_hash, source_filename or book_obj.source_file)

        # Clear caches
        load_book_cached.cache_clear()
        get_cached_reading_times.cache_clear()
        load_book_metadata.cache_clear()
        clear_rewrite_cache()

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
        with _background_threads_lock:
            _background_threads.discard(threading.current_thread())


@router.post("/upload")
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
        validation = _call_validate_pdf(temp_path)
        if not validation["valid"]:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise HTTPException(
                status_code=400,
                detail=_format_pdf_validation_error(validation["error"]),
            )
    elif suffix == ".epub":
        import zipfile

        if not zipfile.is_zipfile(temp_path):
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise HTTPException(
                status_code=400,
                detail="This file does not look like a valid EPUB (not a ZIP archive).",
            )
        try:
            with zipfile.ZipFile(temp_path) as archive:
                if archive.testzip() is not None:
                    raise zipfile.BadZipFile("corrupt archive member")
        except (zipfile.BadZipFile, OSError) as exc:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise HTTPException(
                status_code=400,
                detail=f"This EPUB archive is corrupt: {exc}",
            ) from exc

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
        with _background_threads_lock:
            _background_threads.add(thread)
        thread.start()

        return JSONResponse(
            status_code=202,
            content={"upload_id": upload_id, "status": "processing", "message": "Processing started in background"}
        )

    # Synchronous processing (original behavior for EPUBs)
    try:
        logger.info("Processing %s -> %s", temp_path, full_out_dir)

        if suffix == ".pdf":
            book_obj = _process_pdf(
                temp_path,
                full_out_dir,
                generate_thumbnails=_pdf_thumbnails_enabled(),
                source_filename=safe_filename,
            )
        else:
            book_obj = process_epub(temp_path, full_out_dir)

        save_to_json(book_obj, full_out_dir)
        _persist_upload_metadata(full_out_dir, source_hash, safe_filename)

        load_book_cached.cache_clear()
        get_cached_reading_times.cache_clear()
        load_book_metadata.cache_clear()
        clear_rewrite_cache()

    except Exception as e:
        logger.error("Error processing book: %s", e)
        if os.path.exists(full_out_dir):
            shutil.rmtree(full_out_dir)
        raise HTTPException(status_code=500, detail=f"Failed to process book: {str(e)}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    return RedirectResponse(url="/", status_code=303)


@router.get("/api/v1/upload/status/{upload_id}")
async def get_upload_status(upload_id: str):
    """Get the status of a background upload processing job."""
    with upload_status_lock:
        status = upload_status.get(upload_id)

    if not status:
        raise HTTPException(status_code=404, detail="Upload not found")

    return status


@router.get("/api/v1/upload/status")
async def list_upload_statuses():
    """List all recent upload processing jobs."""
    cleanup_old_statuses()
    with upload_status_lock:
        return {"uploads": list(upload_status.values())}


@router.post("/api/v1/reprocess/{book_id}")
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

    # Prefer the source PDF stored inside the book directory; the original
    # upload may have been removed after processing.
    book_path = os.path.join(BOOKS_DIR, safe_book_id)
    source_candidates = []
    if book.pdf_source_path:
        source_candidates.append(
            os.path.join(book_path, os.path.basename(book.pdf_source_path))
        )
    source_candidates.extend([
        os.path.join(BOOKS_DIR, safe_book_id.replace("_data", ".pdf")),
        os.path.join(BOOKS_DIR, book.source_file),
    ])
    pdf_path = next(
        (path for path in dict.fromkeys(source_candidates) if os.path.exists(path)),
        None,
    )

    if not pdf_path:
        raise HTTPException(
            status_code=400,
            detail="Original PDF not found. Please re-upload the PDF."
        )

    temp_pdf = None
    try:
        # Copy the source outside the book directory: process_pdf swaps the
        # destination atomically, which would invalidate an open source path.
        fd, temp_pdf = tempfile.mkstemp(
            prefix="reader3_reprocess_", suffix=".pdf", dir=BOOKS_DIR
        )
        os.close(fd)
        shutil.copy2(pdf_path, temp_pdf)

        # Reprocess the PDF
        book_obj = _process_pdf(
            temp_pdf, book_path, source_filename=book.source_file
        )
        save_to_json(book_obj, book_path)

        # Clear cache
        load_book_cached.cache_clear()
        get_cached_reading_times.cache_clear()
        load_book_metadata.cache_clear()
        clear_rewrite_cache()

        return {"status": "success", "message": "PDF reprocessed successfully"}
    except Exception as e:
        logger.error("Error reprocessing PDF %s: %s", safe_book_id, e)
        raise HTTPException(
            status_code=500, detail=f"Failed to reprocess PDF: {str(e)}"
        )
    finally:
        if temp_pdf and os.path.exists(temp_pdf):
            try:
                os.remove(temp_pdf)
            except OSError:
                pass
