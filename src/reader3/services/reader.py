"""Reader-state application service."""

from __future__ import annotations

from dataclasses import asdict
from reader3.storage.user_data import (
    Bookmark,
    Highlight,
    ReaderPreferences,
    ReadingProgress,
    UserStateRepository,
    generate_id,
)


class ReaderService:
    """Coordinates bookmarks, highlights, progress, and reader preferences."""

    def __init__(self, user_state: UserStateRepository):
        self.user_state = user_state

    def get_progress(self, book_id: str, total_chapters: int = 0) -> dict:
        progress = self.user_state.get_progress(book_id)
        chapter_progress = self.user_state.get_chapter_progress(book_id)
        progress_percent = self.progress_percent(chapter_progress, total_chapters)

        if not progress:
            return {
                "book_id": book_id,
                "chapter_index": 0,
                "scroll_position": 0.0,
                "progress_percent": progress_percent,
            }

        result = asdict(progress)
        result["progress_percent"] = progress_percent
        return result

    def save_progress(self, book_id: str, payload: dict) -> None:
        progress = ReadingProgress(
            book_id=book_id,
            chapter_index=payload.get("chapter_index", 0),
            scroll_position=payload.get("scroll_position", 0.0),
            total_chapters=payload.get("total_chapters", 0),
            reading_time_seconds=payload.get("reading_time_seconds", 0),
        )
        self.user_state.save_progress(progress)

        progress_percent = payload.get("progress_percent")
        if progress_percent is not None:
            self.user_state.save_chapter_progress(
                book_id,
                progress.chapter_index,
                progress_percent,
            )

    def add_bookmark(self, book_id: str, payload: dict) -> Bookmark:
        bookmark = Bookmark(
            id=generate_id(),
            book_id=book_id,
            chapter_index=payload.get("chapter_index", 0),
            scroll_position=payload.get("scroll_position", 0.0),
            title=payload.get("title", "Bookmark"),
            note=payload.get("note"),
        )
        return self.user_state.add_bookmark(bookmark)

    def get_bookmarks(self, book_id: str) -> list[Bookmark]:
        return self.user_state.get_bookmarks(book_id)

    def delete_bookmark(self, book_id: str, bookmark_id: str) -> bool:
        return self.user_state.delete_bookmark(book_id, bookmark_id)

    def update_bookmark_note(
        self,
        book_id: str,
        bookmark_id: str,
        note: str,
    ) -> bool:
        return self.user_state.update_bookmark_note(book_id, bookmark_id, note)

    def add_highlight(self, book_id: str, payload: dict) -> Highlight:
        highlight = Highlight(
            id=generate_id(),
            book_id=book_id,
            chapter_index=payload.get("chapter_index", 0),
            text=payload.get("text", ""),
            color=payload.get("color", "yellow"),
            note=payload.get("note"),
            start_offset=payload.get("start_offset", 0),
            end_offset=payload.get("end_offset", 0),
        )
        return self.user_state.add_highlight(highlight)

    def get_highlights(
        self,
        book_id: str,
        chapter_index: int | None = None,
    ) -> list[Highlight]:
        return self.user_state.get_highlights(book_id, chapter_index)

    def delete_highlight(self, book_id: str, highlight_id: str) -> bool:
        return self.user_state.delete_highlight(book_id, highlight_id)

    def update_highlight_note(
        self,
        book_id: str,
        highlight_id: str,
        note: str,
    ) -> bool:
        return self.user_state.update_highlight_note(book_id, highlight_id, note)

    def update_highlight_color(
        self,
        book_id: str,
        highlight_id: str,
        color: str,
    ) -> bool:
        return self.user_state.update_highlight_color(
            book_id,
            highlight_id,
            color,
        )

    def get_preferences(self) -> ReaderPreferences:
        return self.user_state.get_reader_preferences()

    @staticmethod
    def progress_percent(
        chapter_progress: dict[int, float],
        total_chapters: int,
    ) -> float:
        if not chapter_progress:
            return 0.0
        if total_chapters > 0:
            return sum(chapter_progress.values()) / total_chapters
        return sum(chapter_progress.values()) / len(chapter_progress)

    @staticmethod
    def serialize_bookmark(bookmark: Bookmark) -> dict:
        return {
            "id": bookmark.id,
            "chapter_index": bookmark.chapter_index,
            "scroll_position": bookmark.scroll_position,
            "title": bookmark.title,
            "note": bookmark.note,
            "created_at": bookmark.created_at,
        }

    @staticmethod
    def serialize_highlight(highlight: Highlight) -> dict:
        return {
            "id": highlight.id,
            "chapter_index": highlight.chapter_index,
            "text": highlight.text,
            "color": highlight.color,
            "note": highlight.note,
            "start_offset": highlight.start_offset,
            "end_offset": highlight.end_offset,
            "created_at": highlight.created_at,
        }


__all__ = ["ReaderService", "UserStateRepository"]
