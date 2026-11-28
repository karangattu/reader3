"""Durable upload-job storage for background book imports."""

from __future__ import annotations

import os
import sqlite3
import threading
from functools import lru_cache
from typing import Any, Optional


class UploadJobStore:
    """SQLite-backed status and recovery data for background uploads."""

    def __init__(self, books_dir: str):
        self.books_dir = books_dir
        self.path = os.path.join(books_dir, "upload_jobs.sqlite3")
        self._lock = threading.RLock()
        self._ready = False
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

    def _ensure_schema(self) -> None:
        with self._lock:
            if self._ready:
                return
        conn = self._connect()
        try:
            with conn:
                conn.executescript(
                    """
                    create table if not exists upload_jobs (
                        id text primary key,
                        status text not null,
                        progress integer not null default 0,
                        message text not null default '',
                        filename text not null default '',
                        book_id text,
                        started_at real not null,
                        completed_at real,
                        temp_path text,
                        suffix text,
                        out_dir text,
                        source_filename text,
                        source_hash text
                    );
                    create index if not exists idx_upload_jobs_status
                        on upload_jobs(status, started_at);
                    """
                )
        finally:
            conn.close()
        with self._lock:
            self._ready = True

    def create(self, job: dict[str, Any]) -> None:
        self._ensure_schema()
        fields = (
            "id", "status", "progress", "message", "filename", "book_id",
            "started_at", "completed_at", "temp_path", "suffix", "out_dir",
            "source_filename", "source_hash",
        )
        values = {field: job.get(field) for field in fields}
        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    "insert or replace into upload_jobs "
                    "(id, status, progress, message, filename, book_id, "
                    "started_at, completed_at, temp_path, suffix, out_dir, "
                    "source_filename, source_hash) "
                    "values (:id, :status, :progress, :message, :filename, "
                    ":book_id, :started_at, :completed_at, :temp_path, :suffix, "
                    ":out_dir, :source_filename, :source_hash)",
                    values,
                )
        finally:
            conn.close()

    def update(self, upload_id: str, **changes: Any) -> None:
        self._ensure_schema()
        if not changes:
            return
        allowed = {
            "status", "progress", "message", "filename", "book_id",
            "completed_at",
        }
        values = {key: value for key, value in changes.items() if key in allowed}
        if not values:
            return
        assignments = ", ".join(f"{key}=:{key}" for key in values)
        values["id"] = upload_id
        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    f"update upload_jobs set {assignments} where id = :id",
                    values,
                )
        finally:
            conn.close()

    def get(self, upload_id: str) -> Optional[dict[str, Any]]:
        self._ensure_schema()
        conn = self._connect()
        try:
            row = conn.execute(
                "select * from upload_jobs where id = ?", (upload_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        self._ensure_schema()
        conn = self._connect()
        try:
            rows = conn.execute(
                "select * from upload_jobs order by started_at desc limit ?",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def active(self) -> list[dict[str, Any]]:
        self._ensure_schema()
        conn = self._connect()
        try:
            rows = conn.execute(
                "select * from upload_jobs "
                "where status in ('queued', 'processing') order by started_at"
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def cleanup_old(self, cutoff: float) -> None:
        self._ensure_schema()
        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    "delete from upload_jobs "
                    "where completed_at is not null and completed_at < ?",
                    (cutoff,),
                )
        finally:
            conn.close()

    @staticmethod
    def public(job: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": job.get("status"),
            "progress": job.get("progress", 0),
            "message": job.get("message", ""),
            "filename": job.get("filename", ""),
            "book_id": job.get("book_id"),
            "started_at": job.get("started_at"),
            "completed_at": job.get("completed_at"),
        }


@lru_cache(maxsize=8)
def get_upload_job_store(books_dir: str) -> UploadJobStore:
    return UploadJobStore(books_dir)
