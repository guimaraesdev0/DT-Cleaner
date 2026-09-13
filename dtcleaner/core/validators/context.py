"""Project context validation.

This is the layer that turns "a folder named `build`" into "the build output of
the Rust project at C:\\dev\\tool". Without it, DT-Cleaner would be a
name-matching script -- exactly what the product must never be.

The validator walks UP from a candidate looking for marker files that prove a
given ecosystem exists. Results are cached per directory because a single
project can produce dozens of candidates that share the same ancestors.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dtcleaner.core.constants import (
    MAX_AMBIGUOUS_MARKER_DISTANCE,
    MAX_MARKER_DISTANCE,
    PROJECT_MARKER_SUFFIXES,
    PROJECT_MARKERS,
    Ecosystem,
)
from dtcleaner.utils import paths as P


@dataclass(frozen=True, slots=True)
class ProjectContext:
    """What the validator could prove about a candidate's surroundings."""

    root: str | None
    markers: tuple[str, ...]
    ecosystem: Ecosystem
    distance: int  # levels between the marker directory and the candidate

    @property
    def proven(self) -> bool:
        return self.root is not None and bool(self.markers)


EMPTY_CONTEXT = ProjectContext(None, (), Ecosystem.UNKNOWN, -1)


@dataclass
class ContextValidator:
    """Finds the project root that justifies a candidate.

    `_dir_cache` maps a directory to the marker names found directly inside it.
    One `os.scandir` per directory, reused by every candidate below it.
    """

    _dir_cache: dict[str, frozenset[str]] = field(default_factory=dict, repr=False)

    def markers_in(self, directory: str | os.PathLike[str]) -> frozenset[str]:
        """Names of marker-like files directly inside `directory` (cached)."""
        key = P.canonical(directory)
        cached = self._dir_cache.get(key)
        if cached is not None:
            return cached

        names: set[str] = set()
        try:
            with os.scandir(P.with_long_prefix(directory)) as it:
                for entry in it:
                    lowered = entry.name.casefold()
                    if _is_any_marker(lowered):
                        names.add(lowered)
        except OSError:
            # Unreadable directory: no markers, therefore no proof. Fail-closed.
            names = set()

        frozen = frozenset(names)
        self._dir_cache[key] = frozen
        return frozen

    def find(
        self,
        candidate_path: str | os.PathLike[str],
        ecosystem: Ecosystem,
        *,
        ambiguous: bool = False,
        max_distance: int | None = None,
    ) -> ProjectContext:
        """Walk up from the candidate looking for markers of `ecosystem`.

        The first ancestor carrying a matching marker wins -- that is the
        nearest project root, which is the one that actually owns the artifact
        in a monorepo.
        """
        limit = max_distance or (
            MAX_AMBIGUOUS_MARKER_DISTANCE if ambiguous else MAX_MARKER_DISTANCE
        )
        wanted = PROJECT_MARKERS.get(ecosystem, frozenset())
        suffixes = PROJECT_MARKER_SUFFIXES.get(ecosystem, ())

        current = Path(str(candidate_path)).parent
        for distance in range(1, limit + 1):
            found = self.markers_in(current)
            matched = tuple(sorted(_match(found, wanted, suffixes)))
            if matched:
                return ProjectContext(str(current), matched, ecosystem, distance)

            parent = current.parent
            if parent == current:  # reached the volume root
                break
            current = parent

        return EMPTY_CONTEXT

    def detect_ecosystem(self, directory: str | os.PathLike[str]) -> Ecosystem:
        """Best guess for what kind of project lives directly in `directory`."""
        found = self.markers_in(directory)
        if not found:
            return Ecosystem.UNKNOWN
        for ecosystem, markers in PROJECT_MARKERS.items():
            suffixes = PROJECT_MARKER_SUFFIXES.get(ecosystem, ())
            if _match(found, markers, suffixes):
                return ecosystem
        return Ecosystem.UNKNOWN

    def clear(self) -> None:
        self._dir_cache.clear()


def _match(
    found: frozenset[str], wanted: frozenset[str], suffixes: tuple[str, ...]
) -> set[str]:
    matched = {name for name in found if name in wanted}
    if suffixes:
        matched |= {name for name in found if name.endswith(suffixes)}
    return matched


_ALL_MARKER_NAMES: frozenset[str] = frozenset().union(*PROJECT_MARKERS.values())
_ALL_MARKER_SUFFIXES: tuple[str, ...] = tuple(
    {suffix for suffixes in PROJECT_MARKER_SUFFIXES.values() for suffix in suffixes}
)


def _is_any_marker(lowered_name: str) -> bool:
    """Cheap pre-filter so the cache only stores names that can ever matter."""
    return lowered_name in _ALL_MARKER_NAMES or lowered_name.endswith(_ALL_MARKER_SUFFIXES)
