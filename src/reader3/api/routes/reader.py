"""Thin reader-state API routes."""

from __future__ import annotations

import os
import sys
from dataclasses import replace

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from reader3.api.deps import (
    BOOKS_DIR,
    _effective_pdf_copy_image_dpi,
    _pdf_copy_image_dpi_options,
    _rewrite_reader_content_asset_paths,
    _serialize_reader_preferences,
    load_book_cached,
    templates,
    user_data_manager,
)

router = APIRouter()


def _get_book(book_id: str):
    server_mod = sys.modules.get("server")
    if server_mod and hasattr(server_mod, "load_book_cached"):
        return server_mod.load_book_cached(book_id)
    return load_book_cached(book_id)


@router.get("/read/{book_id}", response_class=HTMLResponse)
async def redirect_to_first_chapter(request: Request, book_id: str):
    """Helper to just go to chapter 0."""
    return RedirectResponse(
        url=str(request.url_for("read_chapter", book_id=book_id, chapter_index=0)),
        status_code=303,
    )


@router.get("/read/{book_id}/{chapter_index}", response_class=HTMLResponse)
async def read_chapter(request: Request, book_id: str, chapter_index: int):
    """The main reader interface."""
    book = _get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if chapter_index < 0 or chapter_index >= len(book.spine):
        raise HTTPException(status_code=404, detail="Chapter not found")

    current_chapter = book.spine[chapter_index]
    current_chapter = replace(
        current_chapter,
        content=_rewrite_reader_content_asset_paths(current_chapter.content, book_id, book),
    )

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


@router.get("/read/{book_id}/pages/{start}/{count}")
async def get_pages(book_id: str, start: int, count: int):
    """
    Fetches multiple pages for infinite scrolling (PDF only).
    Returns JSON with array of page content.
    """
    book = _get_book(book_id)
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
            "content": _rewrite_reader_content_asset_paths(chapter.content, book_id, book),
        })

    return {"pages": pages, "total": total}


@router.post("/api/v1/chapters/text")
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

    book = _get_book(book_id)
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


@router.get("/read/{book_id}/images/{image_name}")
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
