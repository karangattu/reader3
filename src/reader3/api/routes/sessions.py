"""Sessions API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from reader3.api.deps import (
    user_data_manager,
    ReadingSession,
    generate_id
)

router = APIRouter()


@router.post("/api/v1/sessions/start")
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


@router.post("/api/v1/sessions/{session_id}/end")
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


@router.get("/api/v1/sessions")
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


@router.get("/api/v1/sessions/stats")
async def get_reading_stats(book_id: str = None):
    """Get reading statistics."""
    stats = user_data_manager.get_reading_stats(book_id)
    return stats
