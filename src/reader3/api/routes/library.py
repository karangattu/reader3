"""Library API routes."""

from __future__ import annotations

import os
import shutil

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse

from reader3.api.deps import (
    logger,
    BOOKS_DIR,
    user_data_manager,
    templates,
    _run_sync,
    load_book_metadata,
    _build_library_entry,
    MAX_UPLOAD_MB,
    load_book_cached,
    write_book_metadata,
    get_cached_reading_times
)

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
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


@router.get("/cover/{book_id}")
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


@router.post("/api/v1/metadata/rebuild")
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


@router.delete("/delete/{book_id}")
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
