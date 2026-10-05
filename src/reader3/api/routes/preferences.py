"""Preferences API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from reader3.api.deps import (
    user_data_manager,
    _serialize_reader_preferences,
    VALID_READER_THEMES,
    VALID_READER_FONTS,
    _clamp_pdf_copy_image_dpi
)

router = APIRouter()


@router.get("/api/v1/reader/preferences")
async def get_reader_preferences():
    """Get persisted reader appearance preferences."""
    return _serialize_reader_preferences(user_data_manager.get_reader_preferences())


@router.put("/api/v1/reader/preferences")
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

    if "text_align" in payload:
        text_align = str(payload["text_align"])
        if text_align not in {"justify", "left"}:
            raise HTTPException(status_code=400, detail="Invalid text alignment")
        updates["text_align"] = text_align

    if "pdf_copy_image_dpi" in payload:
        updates["pdf_copy_image_dpi"] = _clamp_pdf_copy_image_dpi(
            int(payload["pdf_copy_image_dpi"])
        )

    preferences = user_data_manager.update_reader_preferences(**updates)
    return _serialize_reader_preferences(preferences)


@router.get("/api/v1/book-font/{book_id}")
async def get_book_font(book_id: str):
    """Get per-book font override."""
    font = user_data_manager.get_book_font(book_id)
    return {"font_family": font}


@router.put("/api/v1/book-font/{book_id}")
async def set_book_font(book_id: str, request: Request):
    """Set per-book font override."""
    payload = await request.json()
    font = str(payload.get("font_family", ""))
    if font not in VALID_READER_FONTS:
        raise HTTPException(status_code=400, detail="Invalid font family")
    user_data_manager.set_book_font(book_id, font)
    return {"font_family": font}


@router.delete("/api/v1/book-font/{book_id}")
async def clear_book_font(book_id: str):
    """Remove per-book font override (fall back to global)."""
    user_data_manager.clear_book_font(book_id)
    return {"font_family": None}
