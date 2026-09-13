"""Detector protocol and registry.

A detector answers one narrow question: "does this directory name, at this
location, look like a disposable artifact of my ecosystem?"

Rules every detector must honor:

* It returns a `Candidate`, never a decision. Risk and confidence are assigned
  later, and the SafetyEngine can only lower them.
* It must mark `ambiguous=True` for any name that is meaningful outside its
  ecosystem (`build`, `dist`, `bin`, `obj`, `target`, ...). That flag is what
  forces proven project context downstream.
* It must never touch the filesystem beyond cheap checks. Heavy work belongs to
  the sizer, which runs later and only on survivors.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from dtcleaner.core.constants import AMBIGUOUS_DIR_NAMES, Category, Ecosystem, RiskLevel
from dtcleaner.core.models import Candidate


@dataclass(frozen=True, slots=True)
class Rule:
    """One directory name this detector recognizes."""

    name: str
    category: Category
    item_type: str
    risk: RiskLevel = RiskLevel.LOW
    base_confidence: float = 0.7
    regenerate_hint: str = ""
    #: Require the candidate's parent directory to have this name (e.g. `obj`
    #: only inside an `android` tree). None means any parent.
    parent_name: str | None = None

    @property
    def ambiguous(self) -> bool:
        return self.name in AMBIGUOUS_DIR_NAMES


@runtime_checkable
class Detector(Protocol):
    """Interface implemented by every ecosystem detector."""

    name: str
    ecosystem: Ecosystem

    def inspect(self, dir_path: str, dir_name: str, parent_name: str) -> Candidate | None:
        """Return a Candidate when `dir_name` is a known artifact, else None."""
        ...


class RuleDetector:
    """Shared implementation driven by a table of `Rule`s."""

    name: str = "rule"
    ecosystem: Ecosystem = Ecosystem.UNKNOWN
    rules: tuple[Rule, ...] = ()

    def __init__(self) -> None:
        self._by_name: dict[str, list[Rule]] = {}
        for rule in self.rules:
            self._by_name.setdefault(rule.name.casefold(), []).append(rule)

    def inspect(self, dir_path: str, dir_name: str, parent_name: str) -> Candidate | None:
        matches = self._by_name.get(dir_name.casefold())
        if not matches:
            return None

        parent = parent_name.casefold()
        # Prefer the most specific rule: one that pins the parent name.
        chosen: Rule | None = None
        for rule in matches:
            if rule.parent_name is None:
                chosen = chosen or rule
            elif rule.parent_name == parent:
                chosen = rule
                break
        if chosen is None:
            return None

        return Candidate(
            path=dir_path,
            name=dir_name,
            category=chosen.category,
            ecosystem=self.ecosystem,
            item_type=chosen.item_type,
            ambiguous=chosen.ambiguous,
            detector=self.name,
            base_confidence=chosen.base_confidence,
            regenerate_hint=chosen.regenerate_hint,
        )

    def risk_for(self, item_type: str) -> RiskLevel:
        for rule in self.rules:
            if rule.item_type == item_type:
                return rule.risk
        return RiskLevel.UNKNOWN


_REGISTRY: list[Detector] = []

# A separate flag rather than "is the registry empty?". Importing a single
# detector module (as a test or a plugin might) registers one detector and
# would otherwise make the registry look fully loaded, silently disabling every
# other ecosystem -- and a missing detector means missed artifacts, which is
# exactly the kind of quiet failure this codebase must not have.
_LOADED = False


def register(detector: Detector) -> Detector:
    _REGISTRY.append(detector)
    return detector


def all_detectors() -> tuple[Detector, ...]:
    global _LOADED
    if not _LOADED:
        _LOADED = True
        _load_builtin()
    return tuple(_REGISTRY)


def risk_for_item_type(item_type: str) -> RiskLevel:
    """Look up the risk a detector declared for an item type."""
    for detector in all_detectors():
        if isinstance(detector, RuleDetector):
            for rule in detector.rules:
                if rule.item_type == item_type:
                    return rule.risk
    return RiskLevel.UNKNOWN


def _load_builtin() -> None:
    # Imported here to avoid a circular import at module load time.
    from dtcleaner.core.detectors import (  # noqa: F401
        android,
        dotnet,
        jvm,
        node,
        python_,
        rust,
    )
