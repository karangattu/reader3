"""Book storage interfaces and filesystem implementation."""

from __future__ import annotations

import json
import os
import pickle
import shutil
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional, Protocol

from reader3.domain.models import Book


class BookRepository(Protocol):
    """Storage boundary for processed books and their metadata."""

    books_dir: str

    def list_book_ids(self) -> list[str]: ...

    def load_book(self, book_id: str) -> Optional[Book]: ...

    def load_metadata(self, book_id: str) -> Optional[dict]: ...

    def write_metadata(self, book_id: str, book: Book) -> dict: ...

    def delete_book(self, book_id: str) -> None: ...


@dataclass
class FileSystemBookRepository:
    """Filesystem-backed repository for Reader3's processed book folders."""

    books_dir: str

    def list_book_ids(self) -> list[str]:
        if not os.path.exists(self.books_dir):
            return []
        return [
            item
            for item in os.listdir(self.books_dir)
            if item.endswith("_data")
            and os.path.isdir(os.path.join(self.books_dir, item))
            and os.path.exists(os.path.join(self.books_dir, item, "book.pkl"))
        ]

    @lru_cache(maxsize=50)
    def load_book(self, book_id: str) -> Optional[Book]:
        file_path = os.path.join(self.books_dir, book_id, "book.pkl")
        if not os.path.exists(file_path):
            return None
        try:
            with open(file_path, "rb") as handle:
                return pickle.load(handle)
        except Exception:
            return None

    @lru_cache(maxsize=200)
    def load_metadata(self, book_id: str) -> Optional[dict]:
        meta_path = os.path.join(self.books_dir, book_id, "book_meta.json")
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as handle:
                    return json.load(handle)
            except Exception:
                return None

        book = self.load_book(book_id)
        if not book:
            return None
        return self.write_metadata(book_id, book)

    def write_metadata(self, book_id: str, book: Book) -> dict:
        metadata = {
            "title": book.metadata.title,
            "authors": book.metadata.authors,
            "chapters": len(book.spine),
            "added_at": book.added_at or book.processed_at,
            "processed_at": book.processed_at,
            "cover_image": book.cover_image,
            "is_pdf": book.is_pdf,
            "language": book.metadata.language,
            "source_file": book.source_file,
        }
        meta_path = os.path.join(self.books_dir, book_id, "book_meta.json")
        os.makedirs(os.path.dirname(meta_path), exist_ok=True)
        with open(meta_path, "w", encoding="utf-8") as handle:
            json.dump(metadata, handle, ensure_ascii=False)
        self.load_metadata.cache_clear()
        return metadata

    def delete_book(self, book_id: str) -> None:
        safe_book_id = os.path.basename(book_id)
        shutil.rmtree(os.path.join(self.books_dir, safe_book_id))
        self.load_book.cache_clear()
        self.load_metadata.cache_clear()
