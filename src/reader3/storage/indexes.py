"""Search index storage interfaces and filesystem implementation."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol


class SearchIndexRepository(Protocol):
    """Storage boundary for per-book search indexes."""

    def load_index(self, book_dir: str, filename: str) -> Optional[dict[str, Any]]:
        ...

    def save_index(
        self,
        book_dir: str,
        filename: str,
        data: dict[str, Any],
    ) -> None:
        ...


@dataclass
class FileSystemSearchIndexRepository:
    """JSON-file implementation for lightweight local search indexes."""

    cache: dict[str, dict[str, Any]] = field(default_factory=dict)

    def load_index(self, book_dir: str, filename: str) -> Optional[dict[str, Any]]:
        path = os.path.join(book_dir, filename)
        if not os.path.exists(path):
            return None

        mtime = os.path.getmtime(path)
        cached = self.cache.get(path)
        if cached and cached.get("mtime") == mtime:
            return cached.get("data")

        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        self.cache[path] = {"mtime": mtime, "data": data}
        return data

    def save_index(
        self,
        book_dir: str,
        filename: str,
        data: dict[str, Any],
    ) -> None:
        path = os.path.join(book_dir, filename)
        tmp_path = f"{path}.tmp"
        os.makedirs(book_dir, exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=True)
        os.replace(tmp_path, path)
        self.cache[path] = {"mtime": os.path.getmtime(path), "data": data}
