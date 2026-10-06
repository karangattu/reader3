"""Progress API routes."""

from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from reader3.api.deps import (
    BOOKS_DIR,
    get_cached_reading_times,
    get_reader_service,
    load_book_metadata,
    user_data_manager,
)

router = APIRouter()


@router.get("/api/v1/reading-times/{book_id}")
async def get_chapter_reading_times(book_id: str):
    """Get estimated reading times for all chapters in a book."""
    reading_times = get_cached_reading_times(book_id)
    if reading_times is None:
        raise HTTPException(status_code=404, detail="Book not found")

    return {"book_id": book_id, "reading_times": reading_times}


@router.get("/api/v1/recently-read")
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


@router.get("/api/v1/progress/{book_id}")
async def get_reading_progress(book_id: str):
    """Get reading progress for a book."""
    meta = load_book_metadata(book_id)
    total_chapters = meta.get("chapters", 0) if meta else 0
    return get_reader_service().get_progress(book_id, total_chapters)


@router.post("/api/v1/progress/{book_id}")
async def save_reading_progress(book_id: str, request: Request):
    """Save reading progress for a book."""
    data = await request.json()
    get_reader_service().save_progress(book_id, data)
    return {"status": "saved"}


@router.get("/api/v1/chapter-progress/{book_id}")
async def get_chapter_progress(book_id: str):
    """Get reading progress for each chapter in a book."""
    progress = user_data_manager.get_chapter_progress(book_id)
    return {"book_id": book_id, "progress": progress}


@router.post("/api/v1/chapter-progress/{book_id}/{chapter_index}")
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


@router.get("/api/v1/copied-pages/{book_id}")
async def get_copied_pages(book_id: str):
    """Get copied page indices (PDF) or chapter hrefs (EPUB) for a book."""
    items = user_data_manager.get_copied_pages(book_id)
    return {"book_id": book_id, "items": items}


@router.post("/api/v1/copied-pages/{book_id}")
async def save_copied_pages(book_id: str, request: Request):
    """Save copied page indices or chapter hrefs for a book."""
    data = await request.json()
    items = data.get("items", [])
    user_data_manager.save_copied_pages(book_id, items)
    return {"status": "saved"}


@router.get("/api/v1/export/{book_id}")
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


@router.get("/api/v1/export")
async def export_all_data():
    """Export all user data."""
    content = user_data_manager.export_all_data()
    return PlainTextResponse(
        content,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=reader3_backup.json"},
    )
