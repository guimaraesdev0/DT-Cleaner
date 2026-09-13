r"""Configuration persisted at `%USERPROFILE%\.dt-cleaner\config.json`.

Safety decision: loading is tolerant but conservative. A corrupted config never
takes the app down -- it falls back to the defaults, which are the SAFEST
values (safe mode on, Recycle Bin on, confirmations on). A tampered file can
never loosen behavior by accident.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from dtcleaner.core.constants import (
    QUICK_SCAN_ABSOLUTE_ROOTS,
    QUICK_SCAN_POSIX_ROOTS,
    QUICK_SCAN_RELATIVE_ROOTS,
    DeleteMode,
)
from dtcleaner.i18n import AVAILABLE_LANGUAGES, DEFAULT_LANGUAGE, set_language
from dtcleaner.utils import paths as P

CONFIG_FILENAME = "config.json"
LOG_DIRNAME = "logs"
HISTORY_FILENAME = "history.db"


class AppConfig(BaseModel):
    """Every default is the safest available option."""

    language: str = DEFAULT_LANGUAGE
    theme: str = "byte-dark"
    safe_mode: bool = True
    animations: bool = True
    ascii_fallback: bool = False

    delete_mode: DeleteMode = DeleteMode.RECYCLE_BIN
    confirm_medium_risk: bool = True
    confirm_high_risk: bool = True
    show_protected_items: bool = True

    quick_scan_paths: list[str] = Field(default_factory=list)
    protected_paths: list[str] = Field(default_factory=list)
    excluded_categories: list[str] = Field(default_factory=list)

    max_scan_depth: int = 12
    scan_workers: int = 8
    log_level: str = "INFO"
    keep_log_files: int = 50

    @field_validator("language")
    @classmethod
    def _known_language(cls, value: str) -> str:
        code = (value or DEFAULT_LANGUAGE).lower().replace("-", "_")
        return code if code in AVAILABLE_LANGUAGES else DEFAULT_LANGUAGE

    @field_validator("scan_workers")
    @classmethod
    def _clamp_workers(cls, value: int) -> int:
        return max(1, min(32, value))

    @field_validator("max_scan_depth")
    @classmethod
    def _clamp_depth(cls, value: int) -> int:
        return max(3, min(40, value))

    def apply_language(self) -> str:
        """Push the configured language into the global translator."""
        return set_language(self.language)

    # -- Protected paths (LAYER 3) -----------------------------------------
    def add_protected(self, path: str | os.PathLike[str]) -> bool:
        """Return False when already protected (or covered by a parent entry)."""
        canon = P.canonical(path)
        for existing in self.protected_paths:
            if P.is_within(canon, existing):
                return False
        # Drop children that are now redundant.
        self.protected_paths = [p for p in self.protected_paths if not P.is_within(p, canon)]
        self.protected_paths.append(str(Path(str(path)).resolve()))
        self.protected_paths.sort(key=str.casefold)
        return True

    def remove_protected(self, path: str | os.PathLike[str]) -> bool:
        canon = P.canonical(path)
        before = len(self.protected_paths)
        self.protected_paths = [p for p in self.protected_paths if P.canonical(p) != canon]
        return len(self.protected_paths) != before

    def is_protected(self, path: str | os.PathLike[str]) -> bool:
        return any(P.is_within(path, p) for p in self.protected_paths)

    # -- Quick scan ---------------------------------------------------------
    def resolved_quick_paths(self) -> list[str]:
        """Quick Scan roots: the configured ones, or the default guesses."""
        if self.quick_scan_paths:
            return [p for p in self.quick_scan_paths if os.path.isdir(p)]

        found: list[str] = []
        home = P.user_profile()
        for rel in QUICK_SCAN_RELATIVE_ROOTS:
            candidate = home / rel
            if candidate.is_dir():
                found.append(str(candidate))
        absolute_guesses = (
            QUICK_SCAN_ABSOLUTE_ROOTS if P.IS_WINDOWS else QUICK_SCAN_POSIX_ROOTS
        )
        for absolute in absolute_guesses:
            if os.path.isdir(absolute):
                found.append(absolute)

        # Deduplicate by canonical form while preserving order.
        seen: set[str] = set()
        unique: list[str] = []
        for path in found:
            canon = P.canonical(path)
            if canon not in seen:
                seen.add(canon)
                unique.append(path)
        return unique


class ConfigStore:
    """Reads and writes the config. Atomic writes, so no half-written JSON."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or P.app_dir()
        self.config_path = self.base_dir / CONFIG_FILENAME
        self.log_dir = self.base_dir / LOG_DIRNAME
        self.history_path = self.base_dir / HISTORY_FILENAME

    def ensure_dirs(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> AppConfig:
        if not self.config_path.is_file():
            return AppConfig()
        try:
            raw: Any = json.loads(self.config_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return AppConfig()
            return AppConfig.model_validate(raw)
        except Exception:  # noqa: BLE001 - a corrupt config falls back to safe defaults
            return AppConfig()

    def save(self, config: AppConfig) -> None:
        self.ensure_dirs()
        payload = config.model_dump(mode="json")
        tmp = self.config_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.config_path)

    # -- Import / export of the protected list ------------------------------
    def export_protected(self, config: AppConfig, target: Path) -> int:
        target.write_text(
            json.dumps({"protected_paths": config.protected_paths}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return len(config.protected_paths)

    def import_protected(self, config: AppConfig, source: Path) -> int:
        data = json.loads(source.read_text(encoding="utf-8"))
        entries = data.get("protected_paths", []) if isinstance(data, dict) else data
        added = 0
        for entry in entries:
            if isinstance(entry, str) and config.add_protected(entry):
                added += 1
        return added


_store: ConfigStore | None = None
_config: AppConfig | None = None


def get_store() -> ConfigStore:
    global _store
    if _store is None:
        _store = ConfigStore()
    return _store


def get_config(reload: bool = False) -> AppConfig:
    global _config
    if _config is None or reload:
        _config = get_store().load()
        _config.apply_language()
    return _config


def save_config(config: AppConfig | None = None) -> AppConfig:
    global _config
    config = config or get_config()
    get_store().save(config)
    config.apply_language()
    _config = config
    return config


def reset_cache() -> None:
    """Used by tests, which swap DTC_HOME between cases."""
    global _store, _config
    _store = None
    _config = None
