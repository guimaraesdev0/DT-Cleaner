"""Domain models.

Immutable where it matters for safety: `risk_level`, `confidence` and
`protected` are never edited by the UI. The UI only touches `selected`, and
even that goes through `ScanItem.set_selected()`, which refuses any item that
is not selectable.

User-facing explanations are stored as i18n keys plus parameters, so the same
ScanItem renders in English or Portuguese without being re-scanned.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, computed_field

from dtcleaner.core.constants import (
    MIN_CONFIDENCE_AUTOSELECT,
    MIN_CONFIDENCE_DELETABLE,
    SELECTABLE_RISKS,
    Category,
    DeleteMode,
    Ecosystem,
    RiskLevel,
    ScanMode,
)
from dtcleaner.i18n import t
from dtcleaner.utils.formatting import human_bytes


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> datetime:
    return datetime.now()


class Candidate(BaseModel):
    """Raw output of a detector, before any validation.

    A Candidate is NOT deletable. It only means "this looks like an artifact".
    """

    model_config = ConfigDict(frozen=True)

    path: str
    name: str
    category: Category
    ecosystem: Ecosystem
    item_type: str
    ambiguous: bool = False
    detector: str = ""
    base_confidence: float = 0.5
    regenerate_hint: str = ""


class ValidationOutcome(BaseModel):
    """Result of the ContextValidator plus the SafetyEngine for one Candidate."""

    model_config = ConfigDict(frozen=True)

    risk_level: RiskLevel
    confidence: float
    reason_key: str
    reason_params: dict[str, Any] = Field(default_factory=dict)
    project_root: str | None = None
    markers_found: tuple[str, ...] = ()
    protected_reason_key: str | None = None
    protected_reason_params: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_protected(self) -> bool:
        return self.risk_level is RiskLevel.PROTECTED

    def reason_text(self) -> str:
        return t(self.reason_key, **self.reason_params)

    def protected_reason_text(self) -> str | None:
        if self.protected_reason_key is None:
            return None
        return t(self.protected_reason_key, **self.protected_reason_params)


class ScanItem(BaseModel):
    """A classified artifact. The unit shared by the UI and the cleanup engine."""

    id: str = Field(default_factory=_new_id)
    path: str
    name: str
    category: Category
    ecosystem: Ecosystem = Ecosystem.UNKNOWN
    item_type: str = ""
    size_bytes: int = 0
    file_count: int = 0
    risk_level: RiskLevel = RiskLevel.UNKNOWN
    confidence: float = 0.0
    project_root: str | None = None
    ambiguous: bool = False
    reason_key: str = ""
    reason_params: dict[str, Any] = Field(default_factory=dict)
    markers_found: tuple[str, ...] = ()
    regenerate_hint: str = ""
    last_modified: datetime | None = None
    size_error: str | None = None

    selected: bool = False
    protected: bool = False
    protected_reason_key: str | None = None
    protected_reason_params: dict[str, Any] = Field(default_factory=dict)
    removed_from_list: bool = False

    @computed_field  # type: ignore[prop-decorator]
    @property
    def size_human(self) -> str:
        return human_bytes(self.size_bytes)

    #: How many trailing path components a display name may show.
    #: ClassVar, not a field -- Pydantic would otherwise treat it as model data.
    MAX_DISPLAY_PARTS: ClassVar[int] = 4

    @property
    def display_name(self) -> str:
        """`project/relative/path` when known, otherwise the bare folder name.

        Trimmed to the last few components: a deeply nested artifact would
        otherwise render a full path in a column sized for a short label.
        """
        if self.project_root:
            try:
                rel = Path(self.path).relative_to(self.project_root)
                parts = (Path(self.project_root).name, *rel.parts)
                if len(parts) > self.MAX_DISPLAY_PARTS:
                    parts = ("...", *parts[-(self.MAX_DISPLAY_PARTS - 1) :])
                return "/".join(parts)
            except ValueError:
                pass
        return self.name

    def reason_text(self) -> str:
        return t(self.reason_key, **self.reason_params) if self.reason_key else ""

    def protected_reason_text(self) -> str | None:
        if self.protected_reason_key is None:
            return None
        return t(self.protected_reason_key, **self.protected_reason_params)

    @property
    def is_selectable(self) -> bool:
        """The single gate the UI consults. Fail-closed on every condition."""
        if self.protected or self.removed_from_list:
            return False
        if self.risk_level not in SELECTABLE_RISKS:
            return False
        return self.confidence >= MIN_CONFIDENCE_DELETABLE

    def should_autoselect(self, safe_mode: bool = True) -> bool:
        """Pre-selection rule. In Safe Mode: LOW risk with high confidence only."""
        if not self.is_selectable:
            return False
        if not safe_mode:
            return self.risk_level is not RiskLevel.HIGH
        return self.risk_level is RiskLevel.LOW and self.confidence >= MIN_CONFIDENCE_AUTOSELECT

    def set_selected(self, value: bool) -> bool:
        """Return whether the change was applied. Selecting a blocked item fails."""
        if value and not self.is_selectable:
            return False
        self.selected = value
        return True

    def mark_protected(self, reason_key: str, **params: Any) -> None:
        self.protected = True
        self.protected_reason_key = reason_key
        self.protected_reason_params = params
        self.risk_level = RiskLevel.PROTECTED
        self.selected = False

    def remove_from_list(self) -> None:
        """The 'R' action in the UI: drop it from this cleanup session."""
        self.removed_from_list = True
        self.selected = False


class ScanSession(BaseModel):
    id: str = Field(default_factory=_new_id)
    started_at: datetime = Field(default_factory=_now)
    finished_at: datetime | None = None
    scan_mode: ScanMode = ScanMode.QUICK
    scanned_roots: list[str] = Field(default_factory=list)
    items: list[ScanItem] = Field(default_factory=list)
    dirs_visited: int = 0
    errors: list[str] = Field(default_factory=list)
    cancelled: bool = False

    @property
    def duration_seconds(self) -> float | None:
        if self.finished_at is None:
            return None
        return (self.finished_at - self.started_at).total_seconds()

    @property
    def visible_items(self) -> list[ScanItem]:
        return [i for i in self.items if not i.removed_from_list]

    @property
    def items_found(self) -> int:
        return len(self.visible_items)

    @property
    def total_recoverable_bytes(self) -> int:
        return sum(i.size_bytes for i in self.visible_items if not i.protected)

    @property
    def selected_items(self) -> list[ScanItem]:
        return [i for i in self.visible_items if i.selected]

    @property
    def selected_bytes(self) -> int:
        return sum(i.size_bytes for i in self.selected_items)

    @property
    def project_count(self) -> int:
        return len({i.project_root for i in self.visible_items if i.project_root})

    def by_category(self) -> dict[Category, list[ScanItem]]:
        grouped: dict[Category, list[ScanItem]] = {}
        for item in self.visible_items:
            grouped.setdefault(item.category, []).append(item)
        for items in grouped.values():
            items.sort(key=lambda i: i.size_bytes, reverse=True)
        return grouped

    def top_items(self, limit: int = 10) -> list[ScanItem]:
        return sorted(self.visible_items, key=lambda i: i.size_bytes, reverse=True)[:limit]

    def risk_counts(self) -> dict[RiskLevel, int]:
        counts: dict[RiskLevel, int] = {}
        for item in self.visible_items:
            counts[item.risk_level] = counts.get(item.risk_level, 0) + 1
        return counts


class CleanupPlan(BaseModel):
    """A frozen snapshot of the user's intent, produced by the Preview screen.

    The CleanupEngine only accepts a plan. That guarantees the UI can never ask
    for a path that did not go through explicit selection.
    """

    id: str = Field(default_factory=_new_id)
    session_id: str
    created_at: datetime = Field(default_factory=_now)
    delete_mode: DeleteMode = DeleteMode.RECYCLE_BIN
    items: list[ScanItem] = Field(default_factory=list)
    excluded_count: int = 0
    protected_count: int = 0
    warnings: list[str] = Field(default_factory=list)

    @property
    def total_size(self) -> int:
        return sum(i.size_bytes for i in self.items)

    @property
    def item_count(self) -> int:
        return len(self.items)

    def risk_breakdown(self) -> dict[RiskLevel, int]:
        counts: dict[RiskLevel, int] = {}
        for item in self.items:
            counts[item.risk_level] = counts.get(item.risk_level, 0) + 1
        return counts

    def categories(self) -> list[Category]:
        return sorted({i.category for i in self.items}, key=lambda c: c.value)

    @property
    def requires_extra_confirmation(self) -> bool:
        breakdown = self.risk_breakdown()
        return bool(breakdown.get(RiskLevel.HIGH)) or self.delete_mode is DeleteMode.PERMANENT


class DeletionOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    item_id: str
    path: str
    success: bool
    freed_bytes: int = 0
    method: str = ""
    error: str | None = None
    skipped_reason_key: str | None = None
    skipped_reason_params: dict[str, Any] = Field(default_factory=dict)

    @property
    def was_skipped(self) -> bool:
        return self.skipped_reason_key is not None

    def skipped_reason_text(self) -> str | None:
        if self.skipped_reason_key is None:
            return None
        return t(self.skipped_reason_key, **self.skipped_reason_params)


class CleanupResult(BaseModel):
    id: str = Field(default_factory=_new_id)
    plan_id: str
    session_id: str
    started_at: datetime = Field(default_factory=_now)
    finished_at: datetime | None = None
    delete_mode: DeleteMode = DeleteMode.RECYCLE_BIN
    outcomes: list[DeletionOutcome] = Field(default_factory=list)
    log_path: str | None = None

    @property
    def deleted_items(self) -> list[DeletionOutcome]:
        return [o for o in self.outcomes if o.success]

    @property
    def failed_items(self) -> list[DeletionOutcome]:
        return [o for o in self.outcomes if not o.success and not o.was_skipped]

    @property
    def skipped_items(self) -> list[DeletionOutcome]:
        return [o for o in self.outcomes if o.was_skipped]

    @property
    def recovered_bytes(self) -> int:
        return sum(o.freed_bytes for o in self.deleted_items)

    @property
    def duration_seconds(self) -> float | None:
        if self.finished_at is None:
            return None
        return (self.finished_at - self.started_at).total_seconds()


class DiskInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    device: str
    mountpoint: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    drive_type: str = "fixed"

    @property
    def used_percent(self) -> float:
        return (self.used_bytes / self.total_bytes * 100) if self.total_bytes else 0.0


class HistoryEntry(BaseModel):
    """One row of the History screen, hydrated from SQLite."""

    id: str
    kind: str  # "scan" | "cleanup"
    timestamp: datetime
    scan_mode: str | None = None
    roots: list[str] = Field(default_factory=list)
    items_found: int = 0
    recoverable_bytes: int = 0
    deleted_items: int = 0
    failed_items: int = 0
    recovered_bytes: int = 0
    duration_seconds: float = 0.0
    log_path: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
