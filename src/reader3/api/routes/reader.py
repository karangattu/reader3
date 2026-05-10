"""Thin reader-state API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


def _app_module():
    from reader3 import app as app_module

    return app_module


@router.get("/api/progress/{book_id}")
async def get_reading_progress(book_id: str):
    app_module = _app_module()
    meta = app_module.load_book_metadata(book_id)
    total_chapters = meta.get("chapters", 0) if meta else 0
    return app_module.get_reader_service().get_progress(
        book_id,
        total_chapters,
    )


@router.post("/api/progress/{book_id}")
async def save_reading_progress(book_id: str, request: Request):
    payload = await request.json()
    _app_module().get_reader_service().save_progress(book_id, payload)
    return {"status": "saved"}


@router.get("/api/bookmarks/{book_id}")
async def get_bookmarks(book_id: str):
    service = _app_module().get_reader_service()
    return {
        "book_id": book_id,
        "bookmarks": [
            service.serialize_bookmark(bookmark)
            for bookmark in service.get_bookmarks(book_id)
        ],
    }


@router.post("/api/bookmarks/{book_id}")
async def add_bookmark(book_id: str, request: Request):
    bookmark = _app_module().get_reader_service().add_bookmark(
        book_id,
        await request.json(),
    )
    return {"id": bookmark.id, "status": "created"}


@router.delete("/api/bookmarks/{book_id}/{bookmark_id}")
async def delete_bookmark(book_id: str, bookmark_id: str):
    if _app_module().get_reader_service().delete_bookmark(book_id, bookmark_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Bookmark not found")


@router.put("/api/bookmarks/{book_id}/{bookmark_id}")
async def update_bookmark(book_id: str, bookmark_id: str, request: Request):
    payload = await request.json()
    updated = _app_module().get_reader_service().update_bookmark_note(
        book_id,
        bookmark_id,
        payload.get("note", ""),
    )
    if updated:
        return {"status": "updated"}
    raise HTTPException(status_code=404, detail="Bookmark not found")


@router.get("/api/highlights/{book_id}")
async def get_highlights(book_id: str, chapter: int | None = None):
    service = _app_module().get_reader_service()
    return {
        "book_id": book_id,
        "highlights": [
            service.serialize_highlight(highlight)
            for highlight in service.get_highlights(book_id, chapter)
        ],
    }


@router.post("/api/highlights/{book_id}")
async def add_highlight(book_id: str, request: Request):
    highlight = _app_module().get_reader_service().add_highlight(
        book_id,
        await request.json(),
    )
    return {"id": highlight.id, "status": "created"}


@router.delete("/api/highlights/{book_id}/{highlight_id}")
async def delete_highlight(book_id: str, highlight_id: str):
    if _app_module().get_reader_service().delete_highlight(book_id, highlight_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Highlight not found")


@router.put("/api/highlights/{book_id}/{highlight_id}")
async def update_highlight(book_id: str, highlight_id: str, request: Request):
    payload = await request.json()
    updated = _app_module().get_reader_service().update_highlight_note(
        book_id,
        highlight_id,
        payload.get("note", ""),
    )
    if updated:
        return {"status": "updated"}
    raise HTTPException(status_code=404, detail="Highlight not found")


@router.put("/api/highlights/{book_id}/{highlight_id}/color")
async def update_highlight_color(
    book_id: str,
    highlight_id: str,
    request: Request,
):
    payload = await request.json()
    updated = _app_module().get_reader_service().update_highlight_color(
        book_id,
        highlight_id,
        payload.get("color", "yellow"),
    )
    if updated:
        return {"status": "updated"}
    raise HTTPException(status_code=404, detail="Highlight not found")
