"""Cleanup planning and execution.

This is the only module in the codebase allowed to delete anything, and it is
deliberately small and boring.

Two invariants:

1. `CleanupEngine.execute()` accepts a `CleanupPlan` and nothing else. There is
   no "delete this path" entry point anywhere in the app, so no screen, CLI
   command or future feature can bypass selection.

2. Every single item is re-validated by `SafetyEngine.final_gate()` immediately
   before its deletion -- not once for the batch. Between the scan and the
   confirmation the user may have moved folders, checked out a branch, or had a
   junction swapped underneath them. An item that fails the gate is SKIPPED and
   reported; it never aborts the run.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from dtcleaner.core.constants import RISK_ORDER, DeleteMode, RiskLevel
from dtcleaner.core.models import (
    CleanupPlan,
    CleanupResult,
    DeletionOutcome,
    ScanItem,
    ScanSession,
)
from dtcleaner.core.safety import SafetyEngine
from dtcleaner.services.recycle_bin_service import (
    SEND2TRASH_AVAILABLE,
    delete_permanently,
    move_to_recycle_bin,
)
from dtcleaner.utils.concurrency import CancelToken


def build_plan(
    session: ScanSession,
    delete_mode: DeleteMode = DeleteMode.RECYCLE_BIN,
) -> CleanupPlan:
    """Freeze the user's current selection into a plan.

    Selection is re-filtered through `is_selectable` here rather than trusted:
    an item could have been protected after it was selected.
    """
    selected = [i for i in session.selected_items if i.is_selectable]
    protected = [i for i in session.items if i.protected]
    removed = [i for i in session.items if i.removed_from_list]

    plan = CleanupPlan(
        session_id=session.id,
        delete_mode=delete_mode,
        items=selected,
        excluded_count=len(removed),
        protected_count=len(protected),
    )
    plan.warnings = _warnings_for(plan)
    return plan


def _warnings_for(plan: CleanupPlan) -> list[str]:
    """Translatable warning keys shown on the Preview screen."""
    warnings: list[str] = []
    risky = sum(
        count
        for risk, count in plan.risk_breakdown().items()
        if RISK_ORDER.get(risk, 0) > RISK_ORDER[RiskLevel.LOW]
    )
    if risky:
        warnings.append("preview.risk_warning")
    if plan.delete_mode is DeleteMode.PERMANENT:
        warnings.append("preview.permanent_warning")
    return warnings


@dataclass(frozen=True, slots=True)
class CleanupProgress:
    """One tick handed to the cleanup progress screen."""

    item: ScanItem
    done: int
    total: int
    freed_bytes: int
    failed: int
    skipped: int

    @property
    def ratio(self) -> float:
        return (self.done / self.total) if self.total else 0.0


ProgressCallback = Callable[[CleanupProgress], None]


@dataclass
class CleanupEngine:
    """Executes a plan, item by item, with a safety gate in front of each one."""

    safety: SafetyEngine
    token: CancelToken = field(default_factory=CancelToken)
    on_progress: ProgressCallback | None = None
    on_log: Callable[[str, dict], None] | None = None

    def execute(self, plan: CleanupPlan) -> CleanupResult:
        result = CleanupResult(
            plan_id=plan.id,
            session_id=plan.session_id,
            delete_mode=plan.delete_mode,
        )

        freed = 0
        failed = 0
        skipped = 0
        total = plan.item_count

        for index, item in enumerate(plan.items, start=1):
            if self.token.cancelled:
                break

            outcome = self._delete_one(item, plan.delete_mode)
            result.outcomes.append(outcome)

            if outcome.success:
                freed += outcome.freed_bytes
            elif outcome.was_skipped:
                skipped += 1
            else:
                failed += 1

            if self.on_progress is not None:
                self.on_progress(
                    CleanupProgress(
                        item=item,
                        done=index,
                        total=total,
                        freed_bytes=freed,
                        failed=failed,
                        skipped=skipped,
                    )
                )

        result.finished_at = datetime.now()
        return result

    def _delete_one(self, item: ScanItem, mode: DeleteMode) -> DeletionOutcome:
        """Gate, then delete. Never raises: a failure is data, not an exception."""
        verdict = self.safety.final_gate(
            item.path,
            expected_name=item.name,
            expected_risk=item.risk_level,
            expected_ambiguous=item.ambiguous,
            expected_project_root=item.project_root,
        )
        if verdict.blocked:
            self._log(
                "cleanup.skipped",
                {"path": item.path, "reason": verdict.reason_key},
            )
            return DeletionOutcome(
                item_id=item.id,
                path=item.path,
                success=False,
                skipped_reason_key=verdict.reason_key,
                skipped_reason_params=verdict.reason_params,
            )

        started = time.monotonic()
        if mode is DeleteMode.RECYCLE_BIN and SEND2TRASH_AVAILABLE:
            report = move_to_recycle_bin(item.path)
        else:
            report = delete_permanently(item.path)

        self._log(
            "cleanup.deleted" if report.success else "cleanup.failed",
            {
                "path": item.path,
                "method": report.method,
                "bytes": item.size_bytes,
                "seconds": round(time.monotonic() - started, 3),
                "error": report.error_detail,
            },
        )

        return DeletionOutcome(
            item_id=item.id,
            path=item.path,
            success=report.success,
            freed_bytes=item.size_bytes if report.success else 0,
            method=report.method,
            error=report.error_key,
        )

    def _log(self, event: str, payload: dict) -> None:
        if self.on_log is not None:
            try:
                self.on_log(event, payload)
            except Exception:
                pass

    def cancel(self) -> None:
        self.token.cancel()
