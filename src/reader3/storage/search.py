"""SQLite FTS5 index for fast exact substring search across book chapters."""

from __future__ import annotations

import os
import sqlite3
import threading
from functools import lru_cache
from typing import Any, Optional


class ExactSearchIndex:
    """Persistent trigram FTS index with a scan fallback when FTS5 is unavailable."""

    def __init__(self, books_dir: str):
        self.books_dir = books_dir
        self.path = os.path.join(books_dir, "reader3_search.sqlite3")
        self._lock = threading.RLock()
        self._ready = False
        self._available: Optional[bool] = None
        self._wal_configured = False

    def _connect(self) -> sqlite3.Connection:
        os.makedirs(self.books_dir, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA synchronous=NORMAL")
        with self._lock:
            if not self._wal_configured:
                conn.execute("PRAGMA journal_mode=WAL")
                self._wal_configured = True
        return conn

    def _ensure_schema(self) -> bool:
        with self._lock:
            if self._ready:
                return bool(self._available)
        conn = self._connect()
        try:
            with conn:
                conn.executescript(
                    """
                    create table if not exists search_books (
                        book_id text primary key,
                        processed_at text not null,
                        chapter_count integer not null,
                        source_mtime_ns integer not null default 0,
                        source_size integer not null default 0
                    );
                    create table if not exists search_chapters (
                        book_id text not null,
                        chapter_index integer not null,
                        chapter_href text not null,
                        chapter_title text not null,
                        book_title text not null,
                        text text not null
                    );
                    create index if not exists idx_search_chapters_book
                        on search_chapters(book_id, chapter_index);
                    create virtual table if not exists search_fts using fts5(
                        text,
                        content='search_chapters',
                        content_rowid='rowid',
                        tokenize='trigram'
                    );
                    create trigger if not exists search_chapters_ai
                    after insert on search_chapters begin
                        insert into search_fts(rowid, text)
                        values (new.rowid, new.text);
                    end;
                    create trigger if not exists search_chapters_ad
                    after delete on search_chapters begin
                        insert into search_fts(search_fts, rowid, text)
                        values ('delete', old.rowid, old.text);
                    end;
                    create trigger if not exists search_chapters_au
                    after update on search_chapters begin
                        insert into search_fts(search_fts, rowid, text)
                        values ('delete', old.rowid, old.text);
                        insert into search_fts(rowid, text)
                        values (new.rowid, new.text);
                    end;
                    """
                )
                columns = {
                    row["name"]
                    for row in conn.execute("pragma table_info(search_books)")
                }
                if "source_mtime_ns" not in columns:
                    conn.execute(
                        "alter table search_books add column "
                        "source_mtime_ns integer not null default 0"
                    )
                if "source_size" not in columns:
                    conn.execute(
                        "alter table search_books add column "
                        "source_size integer not null default 0"
                    )
        except sqlite3.OperationalError:
            with self._lock:
                self._available = False
                self._ready = True
            return False
        finally:
            conn.close()
        with self._lock:
            self._available = True
            self._ready = True
        return True

    def _source_signature(self, book_id: str) -> tuple[int, int]:
        book_dir = os.path.join(self.books_dir, book_id)
        for filename in ("book.json", "book.pkl"):
            try:
                stat = os.stat(os.path.join(book_dir, filename))
                return stat.st_mtime_ns, stat.st_size
            except OSError:
                continue
        return 0, 0

    def _index_book(self, conn: sqlite3.Connection, book_id: str, book: Any) -> None:
        processed_at = getattr(book, "processed_at", "") or ""
        chapter_count = len(getattr(book, "spine", []))
        source_mtime_ns, source_size = self._source_signature(book_id)
        existing = conn.execute(
            "select processed_at, chapter_count, source_mtime_ns, source_size "
            "from search_books where book_id = ?",
            (book_id,),
        ).fetchone()
        if (
            existing
            and existing["processed_at"] == processed_at
            and existing["chapter_count"] == chapter_count
            and existing["source_mtime_ns"] == source_mtime_ns
            and existing["source_size"] == source_size
        ):
            return

        with conn:
            conn.execute("delete from search_chapters where book_id = ?", (book_id,))
            conn.execute("delete from search_books where book_id = ?", (book_id,))
            book_title = getattr(getattr(book, "metadata", None), "title", "")
            conn.executemany(
                "insert into search_chapters "
                "(book_id, chapter_index, chapter_href, chapter_title, book_title, text) "
                "values (?, ?, ?, ?, ?, ?)",
                [
                    (
                        book_id,
                        index,
                        chapter.href,
                        chapter.title,
                        book_title,
                        getattr(chapter, "text", "") or "",
                    )
                    for index, chapter in enumerate(book.spine)
                ],
            )
            conn.execute(
                "insert into search_books "
                "(book_id, processed_at, chapter_count, source_mtime_ns, source_size) "
                "values (?, ?, ?, ?, ?)",
                (book_id, processed_at, chapter_count, source_mtime_ns, source_size),
            )

    def search(
        self,
        query: str,
        book_ids: list[str],
        load_book,
        *,
        limit: int,
        offset: int = 0,
    ) -> Optional[list[dict[str, Any]]]:
        """Return matches, or None when the caller should use its scan fallback."""
        if len(query) < 3 or not book_ids or not self._ensure_schema():
            return None

        conn = self._connect()
        try:
            for book_id in book_ids:
                source_mtime_ns, source_size = self._source_signature(book_id)
                existing = conn.execute(
                    "select source_mtime_ns, source_size from search_books "
                    "where book_id = ?",
                    (book_id,),
                ).fetchone()
                if (
                    existing
                    and existing["source_mtime_ns"] == source_mtime_ns
                    and existing["source_size"] == source_size
                    and (source_mtime_ns or source_size)
                ):
                    continue
                book = load_book(book_id)
                if book:
                    self._index_book(conn, book_id, book)

            placeholders = ",".join("?" for _ in book_ids)
            fts_query = '"' + query.replace('"', '""') + '"'
            rows = conn.execute(
                "select c.book_id, c.book_title, c.chapter_index, "
                "c.chapter_href, c.chapter_title, c.text "
                "from search_fts join search_chapters c on c.rowid = search_fts.rowid "
                f"where search_fts match ? and c.book_id in ({placeholders}) "
                "order by c.rowid",
                (fts_query, *book_ids),
            ).fetchall()
        except sqlite3.OperationalError:
            return None
        finally:
            conn.close()

        query_lower = query.lower()
        results = []
        skipped = 0
        for row in rows:
            text = row["text"]
            text_lower = text.lower()
            start = 0
            while True:
                position = text_lower.find(query_lower, start)
                if position == -1:
                    break
                if skipped < offset:
                    skipped += 1
                else:
                    results.append(
                        {
                            "book_id": row["book_id"],
                            "book_title": row["book_title"],
                            "chapter_index": int(row["chapter_index"]),
                            "chapter_href": row["chapter_href"],
                            "chapter_title": row["chapter_title"],
                            "position": position,
                            "match_length": len(query),
                            "text": text,
                        }
                    )
                    if len(results) >= limit:
                        return results
                start = position + max(1, len(query))
        return results

    def remove_book(self, book_id: str) -> None:
        if not self._ensure_schema():
            return
        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    "delete from search_chapters where book_id = ?", (book_id,)
                )
                conn.execute("delete from search_books where book_id = ?", (book_id,))
        finally:
            conn.close()


@lru_cache(maxsize=8)
def get_exact_search_index(books_dir: str) -> ExactSearchIndex:
    return ExactSearchIndex(books_dir)
