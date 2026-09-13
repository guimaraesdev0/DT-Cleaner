"""Confidence scoring and the detector -> item classification step.

Confidence answers: "how sure are we that this folder is disposable build
output?" It is deliberately separate from risk, which answers a different
question: "how expensive is it if we are right but the user wanted it anyway?"

A `node_modules` next to a `package.json` scores very high. A `target` with no
`Cargo.toml` in sight scores near zero. Anything below
`MIN_CONFIDENCE_DELETABLE` becomes UNKNOWN and can never be selected.
"""

from __future__ import annotations

from dataclasses import dataclass

from dtcleaner.core.constants import (
    Category,
    MAX_AMBIGUOUS_MARKER_DISTANCE,
    Ecosystem,
    RiskLevel,
)
from dtcleaner.core.detectors.base import Detector, RuleDetector, all_detectors
from dtcleaner.core.models import Candidate, ScanItem, ValidationOutcome
from dtcleaner.core.safety import SafetyEngine
from dtcleaner.core.validators.context import ContextValidator, ProjectContext

#: A proven project marker is the single strongest signal available.
PROVEN_PROJECT_BONUS = 0.30

#: Each level between the marker and the candidate weakens the link.
DISTANCE_PENALTY = 0.06

#: An ambiguous name with no project can never rise above this.
AMBIGUOUS_UNPROVEN_CAP = 0.30

#: An unambiguous, tool-owned name still gets some credit without a project
#: (`__pycache__` means one thing and one thing only), but not enough to be
#: auto-selected in Safe Mode.
UNAMBIGUOUS_NO_PROJECT_CAP = 0.65


def score(candidate: Candidate, context: ProjectContext) -> float:
    """Return a confidence value in the range 0.0 - 1.0."""
    value = candidate.base_confidence

    if context.proven:
        value += PROVEN_PROJECT_BONUS
        value -= DISTANCE_PENALTY * max(0, context.distance - 1)
        # Several markers agreeing (package.json + lockfile + tsconfig) is
        # stronger evidence than a single loose file.
        if len(context.markers) >= 2:
            value += 0.05
    elif candidate.ambiguous:
        # No project and an ambiguous name: this is the false-positive case the
        # whole product exists to avoid.
        return min(value, AMBIGUOUS_UNPROVEN_CAP)
    else:
        value = min(value, UNAMBIGUOUS_NO_PROJECT_CAP)

    # An ambiguous name far from its marker is suspicious even when proven.
    if candidate.ambiguous and context.distance > MAX_AMBIGUOUS_MARKER_DISTANCE:
        value -= 0.20

    return max(0.0, min(1.0, round(value, 3)))


@dataclass
class Classifier:
    """Turns raw directory entries into fully classified `ScanItem`s.

    Pipeline per directory:
        detector -> Candidate -> ContextValidator -> score -> SafetyEngine
    The SafetyEngine always runs last and always has the final word.
    """

    safety: SafetyEngine
    validator: ContextValidator
    detectors: tuple[Detector, ...] = ()

    def __post_init__(self) -> None:
        if not self.detectors:
            self.detectors = all_detectors()

    def detect(self, dir_path: str, dir_name: str, parent_name: str) -> list[Candidate]:
        """Ask every detector about this directory.

        More than one can answer (`build` is claimed by Node, Python, JVM and
        Android). They are all kept; `classify` picks whichever ends up with the
        best proven context.
        """
        found: list[Candidate] = []
        for detector in self.detectors:
            candidate = detector.inspect(dir_path, dir_name, parent_name)
            if candidate is not None:
                found.append(candidate)
        return found

    def classify(self, candidates: list[Candidate]) -> ScanItem | None:
        """Resolve competing candidates into at most one ScanItem."""
        if not candidates:
            return None

        best: tuple[float, Candidate, ProjectContext] | None = None
        for candidate in candidates:
            context = self.validator.find(
                candidate.path, candidate.ecosystem, ambiguous=candidate.ambiguous
            )
            value = score(candidate, context)
            if best is None or value > best[0]:
                best = (value, candidate, context)

        assert best is not None
        confidence, candidate, context = best

        outcome = self.safety.classify(
            candidate,
            project_root=context.root,
            markers=context.markers,
            confidence=confidence,
            proposed_risk=_risk_of(candidate),
            reason_key=_reason_key(candidate, context),
            reason_params=_reason_params(candidate, context),
        )
        return self._to_item(candidate, outcome, context)

    @staticmethod
    def _to_item(
        candidate: Candidate, outcome: ValidationOutcome, context: ProjectContext
    ) -> ScanItem:
        # When nothing was proven, do not display the detector's guess as fact.
        # Labeling an unproven `build` as "JVM Build Output" would imply a
        # confidence the engine explicitly refused to grant.
        category = candidate.category
        if outcome.project_root is None and candidate.ambiguous:
            category = Category.OTHER

        item = ScanItem(
            path=candidate.path,
            name=candidate.name,
            category=category,
            ecosystem=candidate.ecosystem,
            item_type=candidate.item_type,
            ambiguous=candidate.ambiguous,
            risk_level=outcome.risk_level,
            confidence=outcome.confidence,
            project_root=outcome.project_root,
            reason_key=outcome.reason_key,
            reason_params=outcome.reason_params,
            markers_found=outcome.markers_found,
            regenerate_hint=candidate.regenerate_hint,
        )
        if outcome.is_protected:
            item.protected = True
            item.protected_reason_key = outcome.protected_reason_key
            item.protected_reason_params = outcome.protected_reason_params
        return item


def _risk_of(candidate: Candidate) -> RiskLevel:
    for detector in all_detectors():
        if not isinstance(detector, RuleDetector):
            continue
        for rule in detector.rules:
            if rule.item_type == candidate.item_type:
                return rule.risk
    # A detector that declares no risk is treated as unknown, never as safe.
    return RiskLevel.UNKNOWN


def _reason_key(candidate: Candidate, context: ProjectContext) -> str:
    if context.proven:
        return "detect.proven"
    if candidate.ambiguous:
        return "safety.ambiguous_no_project"
    return "detect.tool_owned"


def _reason_params(candidate: Candidate, context: ProjectContext) -> dict[str, object]:
    if context.proven:
        return {
            "marker": context.markers[0],
            "distance": context.distance,
            "ecosystem": _ecosystem_label(candidate.ecosystem),
        }
    if candidate.ambiguous:
        return {"name": candidate.name}
    return {"name": candidate.name}


def _ecosystem_label(ecosystem: Ecosystem) -> str:
    return {
        Ecosystem.NODE: "Node",
        Ecosystem.PYTHON: "Python",
        Ecosystem.RUST: "Rust",
        Ecosystem.DOTNET: ".NET",
        Ecosystem.JVM: "JVM",
        Ecosystem.ANDROID: "Android",
    }.get(ecosystem, "unknown")
