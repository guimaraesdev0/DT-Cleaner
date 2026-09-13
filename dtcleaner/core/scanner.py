"""The scanner: walks the filesystem and produces a `ScanSession`.

Design constraints, in priority order:

1. Never follow a reparse point. A junction pointing at `C:\\` would otherwise
   turn a folder scan into a full-disk scan, or produce an infinite loop.
2. Skip protected and system areas as EARLY as possible -- before descending,
   not after. That is both a safety property and the main performance win.
3. Stay cancellable. The token is checked once per directory, so ESC feels
   instant even mid-scan.
4. Never die on one bad directory. Every OSError is recorded and the walk
   continues.

Phases are reported to the UI so the progress screen can show real stages
rather than a meaningless spinner.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from dtcleaner.core.confidence import Classifier
from dtcleaner.core.config import AppConfig
from dtcleaner.core.constants import SKIP_TRAVERSE_DIR_NAMES, Category, ScanMode
from dtcleaner.core.models import ScanItem, ScanSession
from dtcleaner.core.safety import SafetyEngine
from dtcleaner.core.sizer import measure_items
from dtcleaner.core.validators.context import ContextValidator
from dtcleaner.utils import paths as P
from dtcleaner.utils.concurrency import CancelToken, Throttle


class Phase(StrEnum):
    DISCOVERY = "scan.phase.discovery"
    CLASSIFICATION = "scan.phase.classification"
    VALIDATION = "scan.phase.validation"
    SIZING = "scan.phase.sizing"
    CATEGORIZATION = "scan.phase.categorization"
    FINALIZING = "scan.phase.finalizing"


@dataclass(frozen=True, slots=True)
class Progress:
    """One progress tick handed to the UI.

    `found_name` / `found_category` carry the artifact that was just
    discovered, so the progress screen can stream a live feed of finds instead
    of only showing an abstract counter.
    """

    phase: Phase
    current_path: str = ""
    dirs_visited: int = 0
    candidates: int = 0
    done: int = 0
    total: int = 0
    found_name: str = ""
    found_category: str = ""
    found_project: str = ""

    @property
    def ratio(self) -> float:
        return (self.done / self.total) if self.total else 0.0

    @property
    def is_find(self) -> bool:
        return bool(self.found_name)


ProgressCallback = Callable[[Progress], None]


@dataclass
class Scanner:
    """Runs a scan. One instance per session; safe to use from a worker thread."""

    config: AppConfig
    safety: SafetyEngine
    token: CancelToken = field(default_factory=CancelToken)
    on_progress: ProgressCallback | None = None

    _throttle: Throttle = field(default_factory=Throttle, repr=False)
    _validator: ContextValidator = field(default_factory=ContextValidator, repr=False)
    _found: int = field(default=0, repr=False)

    def scan(self, roots: Sequence[str], mode: ScanMode = ScanMode.QUICK) -> ScanSession:
        """Full pipeline: discover, classify, size, categorize."""
        session = ScanSession(scan_mode=mode, scanned_roots=list(roots))
        self._validator.clear()
        self._found = 0
        classifier = Classifier(safety=self.safety, validator=self._validator)

        # --- phases 1-3: discovery, classification, validation --------------
        items: list[ScanItem] = []
        seen: set[str] = set()
        for root in roots:
            if self.token.cancelled:
                break
            for item in self._walk(root, classifier, session):
                canon = P.canonical(item.path)
                if canon in seen:
                    continue
                seen.add(canon)
                items.append(item)

        # --- phase 4: sizing ------------------------------------------------
        sizable = [i for i in items if self.config.show_protected_items or not i.protected]
        self._emit(Phase.SIZING, done=0, total=len(sizable))
        measure_items(
            sizable,
            workers=self.config.scan_workers,
            token=self.token,
            on_progress=lambda done, total: self._throttle.call(
                self.on_progress, Progress(Phase.SIZING, done=done, total=total)
            ),
        )

        # --- phase 5: categorization ----------------------------------------
        self._emit(Phase.CATEGORIZATION, total=len(items))
        items = self._finalize(items)

        # --- phase 6: report -------------------------------------------------
        self._emit(Phase.FINALIZING, total=len(items))
        session.items = items
        session.finished_at = datetime.now()
        session.cancelled = self.token.cancelled
        return session

    # -- walking -----------------------------------------------------------
    def _walk(
        self, root: str, classifier: Classifier, session: ScanSession
    ) -> Iterable[ScanItem]:
        """Iterative pre-order walk with early pruning.

        The stack holds `(path, depth)`. A directory that is itself a detected
        artifact is NOT descended into: once `node_modules` is found, walking
        its 30k files would be pure waste.
        """
        root_facts = P.inspect(root)
        if not root_facts.exists or not root_facts.is_dir:
            session.errors.append(f"{root}: error.not_found")
            return

        stack: list[tuple[str, int]] = [(str(root), 0)]
        max_depth = self.config.max_scan_depth

        while stack:
            if self.token.cancelled:
                return

            current, depth = stack.pop()
            session.dirs_visited += 1
            self._throttle.call(
                self.on_progress,
                Progress(
                    Phase.DISCOVERY,
                    current_path=current,
                    dirs_visited=session.dirs_visited,
                    candidates=self._found,
                ),
            )

            try:
                entries = list(os.scandir(P.with_long_prefix(current)))
            except OSError as exc:
                session.errors.append(f"{current}: {_error_key(exc)}")
                continue

            parent_name = os.path.basename(current)
            for entry in entries:
                if self.token.cancelled:
                    return
                try:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                except OSError:
                    continue

                name = entry.name
                lowered = name.casefold()
                child = entry.path
                # Strip the long-path prefix that scandir propagates, so paths
                # stored on items stay human-readable.
                child = P.strip_long_prefix(child)

                # --- prune: never traverse a reparse point -------------------
                if P.entry_is_reparse_point(entry):
                    continue

                # --- prune: user-protected subtree ---------------------------
                if self.safety.protecting_root(child) is not None:
                    continue

                candidates = classifier.detect(child, name, parent_name)
                if candidates:
                    item = classifier.classify(candidates)
                    if item is not None and self._keep(item):
                        self._found += 1
                        # Forced, not throttled: finds are rare compared to
                        # directory visits, and each one is worth showing.
                        self._throttle.force(
                            self.on_progress,
                            Progress(
                                Phase.DISCOVERY,
                                current_path=current,
                                dirs_visited=session.dirs_visited,
                                candidates=self._found,
                                found_name=item.name,
                                found_category=item.category.value,
                                found_project=(
                                    os.path.basename(item.project_root)
                                    if item.project_root
                                    else ""
                                ),
                            ),
                        )
                        yield item
                    # An artifact is a leaf for scanning purposes.
                    continue

                # --- prune: known-useless or dangerous subtrees --------------
                if lowered in SKIP_TRAVERSE_DIR_NAMES:
                    continue
                if depth >= max_depth:
                    continue

                stack.append((child, depth + 1))

    def _keep(self, item: ScanItem) -> bool:
        if item.protected and not self.config.show_protected_items:
            return False
        return item.category.value not in self.config.excluded_categories

    # -- finalization ------------------------------------------------------
    def _finalize(self, items: list[ScanItem]) -> list[ScanItem]:
        """Drop empty artifacts, pre-select, and sort for display."""
        kept: list[ScanItem] = []
        for item in items:
            # A zero-byte artifact is noise: nothing to reclaim, and offering it
            # only adds risk surface to the confirmation screen.
            if item.size_bytes == 0 and not item.protected:
                continue
            item.selected = item.should_autoselect(self.config.safe_mode)
            kept.append(item)

        kept.sort(key=lambda i: (_category_rank(i.category), -i.size_bytes))
        return kept

    # -- progress -----------------------------------------------------------
    def _emit(self, phase: Phase, **kwargs: int) -> None:
        self._throttle.force(self.on_progress, Progress(phase, **kwargs))

    def cancel(self) -> None:
        self.token.cancel()


def _category_rank(category: Category) -> int:
    from dtcleaner.core.constants import CATEGORY_ORDER

    try:
        return CATEGORY_ORDER.index(category)
    except ValueError:
        return len(CATEGORY_ORDER)


def _error_key(exc: OSError) -> str:
    winerror = getattr(exc, "winerror", None)
    if winerror == 5 or exc.errno == 13:
        return "error.access_denied"
    if winerror == 206:
        return "error.path_too_long"
    if winerror in (2, 3) or exc.errno == 2:
        return "error.not_found"
    return "error.unexpected"


def resolve_roots(config: AppConfig, mode: ScanMode, custom: Sequence[str] | None = None):
    """Turn a scan mode into the list of roots to walk."""
    if mode is ScanMode.QUICK:
        return config.resolved_quick_paths()
    if mode is ScanMode.CUSTOM:
        return [p for p in (custom or []) if os.path.isdir(p)]
    # FULL: every fixed drive, unless the caller narrowed it down.
    from dtcleaner.services.disk_service import list_scannable_roots

    return [p for p in (custom or list_scannable_roots()) if os.path.isdir(p)]
