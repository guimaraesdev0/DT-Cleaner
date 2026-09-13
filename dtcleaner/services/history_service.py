"""Scan and cleanup history, stored in SQLite.

SQLite rather than JSON because history is append-heavy and queried by date and
by totals ("how much have I reclaimed overall?"). A growing JSON file would
have to be fully rewritten on every session.

Failures here are non-fatal by design: history is a convenience, and losing it
must never prevent a scan or a cleanup from running.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from dtcleaner.core.models import CleanupResult, HistoryEntry, ScanSession

SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    scan_mode TEXT,
    roots TEXT,
    items_found INTEGER DEFAULT 0,
    recoverable_bytes INTEGER DEFAULT 0,
    duration_seconds REAL DEFAULT 0,
    errors INTEGER DEFAULT 0,
    cancelled INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cleanups (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    delete_mode TEXT,
    deleted_items INTEGER DEFAULT 0,
    failed_items INTEGER DEFAULT 0,
    skipped_items INTEGER DEFAULT 0,
    recovered_bytes INTEGER DEFAULT 0,
    duration_seconds REAL DEFAULT 0,
    log_path TEXT
);

CREATE INDEX IF NOT EXISTS idx_scans_started ON scans(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_cleanups_started ON cleanups(started_at DESC);
"""


class HistoryService:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._ensure_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _ensure_schema(self) -> None:
        try:
            with self._connect() as conn:
                conn.executescript(SCHEMA)
        except sqlite3.Error:
            pass  # history is optional; never block the app

    # -- writes -------------------------------------------------------------
    def record_scan(self, session: ScanSession) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO scans
                       (id, started_at, finished_at, scan_mode, roots, items_found,
                        recoverable_bytes, duration_seconds, errors, cancelled)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (
                        session.id,
                        session.started_at.isoformat(),
                        session.finished_at.isoformat() if session.finished_at else None,
                        session.scan_mode.value,
                        json.dumps(session.scanned_roots),
                        session.items_found,
                        session.total_recoverable_bytes,
                        session.duration_seconds or 0.0,
                        len(session.errors),
                        int(session.cancelled),
                    ),
                )
        except sqlite3.Error:
            pass

    def record_cleanup(self, result: CleanupResult) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO cleanups
                       (id, session_id, started_at, finished_at, delete_mode,
                        deleted_items, failed_items, skipped_items,
                        recovered_bytes, duration_seconds, log_path)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        result.id,
                        result.session_id,
                        result.started_at.isoformat(),
                        result.finished_at.isoformat() if result.finished_at else None,
                        result.delete_mode.value,
                        len(result.deleted_items),
                        len(result.failed_items),
                        len(result.skipped_items),
                        result.recovered_bytes,
                        result.duration_seconds or 0.0,
                        result.log_path,
                    ),
                )
        except sqlite3.Error:
            pass

    # -- reads --------------------------------------------------------------
    def recent_scans(self, limit: int = 20) -> list[HistoryEntry]:
        rows = self._query("SELECT * FROM scans ORDER BY started_at DESC LIMIT ?", (limit,))
        return [
            HistoryEntry(
                id=row["id"],
                kind="scan",
                timestamp=_parse(row["started_at"]),
                scan_mode=row["scan_mode"],
                roots=json.loads(row["roots"] or "[]"),
                items_found=row["items_found"],
                recoverable_bytes=row["recoverable_bytes"],
                duration_seconds=row["duration_seconds"],
            )
            for row in rows
        ]

    def recent_cleanups(self, limit: int = 20) -> list[HistoryEntry]:
        rows = self._query("SELECT * FROM cleanups ORDER BY started_at DESC LIMIT ?", (limit,))
        return [
            HistoryEntry(
                id=row["id"],
                kind="cleanup",
                timestamp=_parse(row["started_at"]),
                deleted_items=row["deleted_items"],
                failed_items=row["failed_items"],
                recovered_bytes=row["recovered_bytes"],
                duration_seconds=row["duration_seconds"],
                log_path=row["log_path"],
                extra={"delete_mode": row["delete_mode"], "skipped": row["skipped_items"]},
            )
            for row in rows
        ]

    def total_recovered_bytes(self) -> int:
        rows = self._query("SELECT COALESCE(SUM(recovered_bytes), 0) AS total FROM cleanups", ())
        return int(rows[0]["total"]) if rows else 0

    def _query(self, sql: str, params: tuple) -> list[sqlite3.Row]:
        try:
            with self._connect() as conn:
                return list(conn.execute(sql, params).fetchall())
        except sqlite3.Error:
            return []


def _parse(value: str | None) -> datetime:
    try:
        return datetime.fromisoformat(value) if value else datetime.now()
    except ValueError:
        return datetime.now()
