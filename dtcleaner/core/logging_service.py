r"""Logging: a human log and a machine log, side by side.

Two outputs on purpose:

* `dtc-YYYYMMDD-HHMMSS.log` -- plain text, what the user opens from the Summary
  screen to find out why one folder failed.
* `dtc-YYYYMMDD-HHMMSS.jsonl` -- one JSON object per event, so a cleanup can be
  audited afterwards ("what exactly was deleted, and why was it allowed?").

Log files are pruned to `keep_log_files` so the app does not grow forever in
`%USERPROFILE%\.dt-cleaner\logs`.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from dtcleaner.core.config import AppConfig, ConfigStore

LOGGER_NAME = "dtcleaner"


class SessionLogger:
    """Owns the two log files for one app session."""

    def __init__(self, store: ConfigStore, config: AppConfig) -> None:
        store.ensure_dirs()
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.text_path = store.log_dir / f"dtc-{stamp}.log"
        self.json_path = store.log_dir / f"dtc-{stamp}.jsonl"
        self._config = config

        self.logger = logging.getLogger(f"{LOGGER_NAME}.{stamp}")
        self.logger.setLevel(getattr(logging, config.log_level.upper(), logging.INFO))
        self.logger.propagate = False

        handler = logging.FileHandler(self.text_path, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s", "%H:%M:%S")
        )
        self.logger.addHandler(handler)
        self._handler = handler

        _prune_old_logs(store.log_dir, config.keep_log_files)

    # -- structured events --------------------------------------------------
    def event(self, name: str, payload: dict[str, Any] | None = None) -> None:
        """Append one structured record to the JSONL log."""
        record = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "event": name,
            **(payload or {}),
        }
        try:
            with self.json_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            # A log write must never break the operation being logged.
            pass

    # -- convenience wrappers ----------------------------------------------
    def info(self, message: str, **payload: Any) -> None:
        self.logger.info(message)
        if payload:
            self.event(message, payload)

    def warning(self, message: str, **payload: Any) -> None:
        self.logger.warning(message)
        self.event(message, payload)

    def error(self, message: str, **payload: Any) -> None:
        self.logger.error(message)
        self.event(message, payload)

    def scan_started(self, mode: str, roots: list[str]) -> None:
        self.logger.info("Scan started (%s): %s", mode, ", ".join(roots) or "-")
        self.event("scan.started", {"mode": mode, "roots": roots})

    def scan_finished(self, items: int, recoverable: int, seconds: float, errors: int) -> None:
        self.logger.info(
            "Scan finished: %d items, %d bytes recoverable, %.1fs, %d errors",
            items,
            recoverable,
            seconds,
            errors,
        )
        self.event(
            "scan.finished",
            {
                "items": items,
                "recoverable_bytes": recoverable,
                "seconds": round(seconds, 2),
                "errors": errors,
            },
        )

    def cleanup_started(self, item_count: int, total_bytes: int, mode: str) -> None:
        self.logger.info("Cleanup started: %d items, %d bytes, mode=%s",
                         item_count, total_bytes, mode)
        self.event(
            "cleanup.started",
            {"items": item_count, "bytes": total_bytes, "mode": mode},
        )

    def cleanup_event(self, name: str, payload: dict[str, Any]) -> None:
        """Callback handed to the CleanupEngine."""
        path = payload.get("path", "?")
        if name == "cleanup.deleted":
            self.logger.info("Deleted %s (%s)", path, payload.get("method"))
        elif name == "cleanup.skipped":
            self.logger.warning("Skipped %s -- %s", path, payload.get("reason"))
        else:
            self.logger.error("Failed %s -- %s", path, payload.get("error"))
        self.event(name, payload)

    def cleanup_finished(self, deleted: int, failed: int, freed: int, seconds: float) -> None:
        self.logger.info(
            "Cleanup finished: %d deleted, %d failed, %d bytes freed, %.1fs",
            deleted,
            failed,
            freed,
            seconds,
        )
        self.event(
            "cleanup.finished",
            {
                "deleted": deleted,
                "failed": failed,
                "freed_bytes": freed,
                "seconds": round(seconds, 2),
            },
        )

    def close(self) -> None:
        self._handler.close()
        self.logger.removeHandler(self._handler)


def _prune_old_logs(log_dir: Path, keep: int) -> None:
    """Delete the oldest log files beyond `keep`, per extension."""
    for pattern in ("dtc-*.log", "dtc-*.jsonl"):
        try:
            files = sorted(log_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        except OSError:
            continue
        for stale in files[max(1, keep) :]:
            try:
                stale.unlink()
            except OSError:
                pass
