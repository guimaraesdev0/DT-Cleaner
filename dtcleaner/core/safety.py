r"""SAFETY ENGINE -- the final authority on what may be deleted.

Contract of this module (binding for the whole product):

1. The Safety Engine only has VETO power. It never promotes an item to a lower
   risk. Detectors propose; this engine blocks. A buggy new detector can, at
   worst, fail to find things -- it can never open a path to deletion.

2. Fail-closed. Any error, doubt, exception or missing information results in
   PROTECTED or UNKNOWN, never in "safe to delete".

3. A name is never enough. A path only passes with proven project context.

4. Rules run TWICE: during the scan (`classify`) and immediately before each
   deletion (`final_gate`), with the path re-resolved from scratch. That covers
   TOCTOU -- the user may have moved the folder, or a symlink may have been
   swapped, between the scan and the confirmation.

Block reasons are returned as i18n keys plus parameters, never as prebuilt
sentences, so the UI can render them in the user's chosen language.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dtcleaner.core.constants import (
    AMBIGUOUS_DIR_NAMES,
    APPDATA_BLOCKED_SEGMENTS,
    FORBIDDEN_ENV_VARS,
    MIN_CONFIDENCE_DELETABLE,
    MIN_DELETE_DEPTH,
    POSIX_PROTECTED_HOME_DIRS,
    POSIX_SYSTEM_DIR_NAMES,
    POSIX_SYSTEM_ROOTS,
    POSIX_TEMP_ROOTS,
    PROTECTED_DIR_NAMES,
    PROTECTED_FILE_NAMES,
    PROTECTED_FILE_PREFIXES,
    PROTECTED_FILE_SUFFIXES,
    PROTECTED_PROFILE_DIRS,
    SYSTEM_DIR_NAMES,
    RiskLevel,
)
from dtcleaner.core.models import Candidate, ValidationOutcome
from dtcleaner.i18n import t
from dtcleaner.utils import paths as P


@dataclass(frozen=True, slots=True)
class Verdict:
    """The engine's decision about a path.

    `reason_key` is an i18n key; `reason_params` feeds its placeholders.
    Call `text()` to render it in the active language.
    """

    allowed: bool
    risk: RiskLevel
    reason_key: str
    reason_params: dict[str, Any] = field(default_factory=dict)

    @property
    def blocked(self) -> bool:
        return not self.allowed

    def text(self) -> str:
        return t(self.reason_key, **self.reason_params)


def _block(reason_key: str, **params: Any) -> Verdict:
    return Verdict(False, RiskLevel.PROTECTED, reason_key, params)


@dataclass
class SafetyEngine:
    """Evaluates paths against the five protection layers.

    `user_protected` holds the paths registered by the user (LAYER 3).
    """

    user_protected: list[str] = field(default_factory=list)
    _system_roots: tuple[str, ...] = field(default=(), init=False, repr=False)
    _protected_canon: tuple[str, ...] = field(default=(), init=False, repr=False)

    def __post_init__(self) -> None:
        self._system_roots = _collect_system_roots()
        self.reload_protected(self.user_protected)

    # -- LAYER 3 -----------------------------------------------------------
    def reload_protected(self, protected: list[str]) -> None:
        canon: list[str] = []
        for entry in protected:
            try:
                canon.append(P.canonical(entry))
            except Exception:
                continue
        self.user_protected = list(protected)
        self._protected_canon = tuple(canon)

    def protecting_root(self, path: str | os.PathLike[str]) -> str | None:
        """Which user-protected path covers this item, if any."""
        for protected in self._protected_canon:
            if P.is_within(path, protected):
                return protected
        return None

    # -- LAYERS 1 and 2 ----------------------------------------------------
    def check_path(self, path: str | os.PathLike[str]) -> Verdict:
        """Structural verdict, independent of any detector or project context.

        This function alone prevents catastrophe: it refuses drive roots,
        system folders, user profile folders and anything too shallow.
        """
        try:
            canon = P.canonical(path)
        except Exception as exc:
            return _block("safety.unresolvable", error=str(exc))

        if not canon:
            return _block("safety.empty_path")

        parts = P.parts_of(canon)
        anchor = P.anchor_of(canon)

        # --- volume root ---------------------------------------------------
        if not parts:
            return _block("safety.volume_root", anchor=anchor)

        # --- minimum depth -------------------------------------------------
        if len(parts) < MIN_DELETE_DEPTH:
            return _block("safety.too_shallow", depth=len(parts), minimum=MIN_DELETE_DEPTH)

        # --- system directories, matched by top-level name -----------------
        # Both name sets are consulted on both platforms. They do not overlap in
        # any harmful way, and checking both means a mounted or copied tree from
        # the other OS is still refused.
        #
        # Temp directories are exempt from the system rules only. On macOS the
        # system temp directory resolves to `/private/var/folders/...`, which
        # sits inside two system roots; without this the engine refused every
        # path under it. Every other layer below still applies.
        in_temp = _is_temp(canon)
        first = parts[0]
        if not in_temp:
            if first in SYSTEM_DIR_NAMES:
                return _block("safety.system_dir", name=first)
            if not P.IS_WINDOWS and first in POSIX_SYSTEM_DIR_NAMES:
                return _block("safety.system_dir", name=first)

            # --- system paths resolved from environment variables ----------
            for root in self._system_roots:
                if P.is_within(canon, root):
                    return _block("safety.inside_system", root=root)

        # --- current user profile ------------------------------------------
        # Checked before the generic rule below so the current user gets the
        # precise reason ("your profile root") instead of "another user's".
        verdict = self._check_user_profile(canon)
        if verdict is not None:
            return verdict

        # --- any other user's profile root (`C:\Users\someone`) -------------
        # `C:\Users` on its own is already caught by the minimum depth rule.
        if first == "users" and len(parts) == 2:
            return _block("safety.other_profile", name=parts[1])

        # --- directory protected by name -----------------------------------
        leaf = parts[-1]
        if leaf in PROTECTED_DIR_NAMES:
            return _block("safety.protected_dir_name", name=leaf)

        # --- user protected list (LAYER 3) ---------------------------------
        protecting = self.protecting_root(canon)
        if protecting is not None:
            return _block("safety.user_protected", root=protecting)

        # --- reparse point --------------------------------------------------
        facts = P.inspect(canon)
        if facts.is_reparse_point:
            return _block("safety.reparse_point")

        return Verdict(True, RiskLevel.UNKNOWN, "safety.no_block")

    def _check_user_profile(self, canon: str) -> Verdict | None:
        home = P.canonical(P.user_profile())
        if not P.is_within(canon, home):
            return None

        rel = P.full_parts(canon)[len(P.full_parts(home)) :]
        if not rel:
            return _block("safety.profile_root")

        top = rel[0]
        # The first-level profile folder is untouchable; its contents may not be.
        if top in PROTECTED_PROFILE_DIRS and len(rel) == 1:
            return _block("safety.profile_dir", name=top)

        if top == "appdata" and len(rel) >= 2 and rel[1] in APPDATA_BLOCKED_SEGMENTS:
            return _block("safety.appdata_segment", segment=rel[1])

        # A dot-directory sitting directly in the profile (e.g. ~\.aws).
        if top.startswith(".") and len(rel) == 1:
            return _block("safety.profile_config", name=top)

        if top in POSIX_PROTECTED_HOME_DIRS and len(rel) == 1:
            return _block("safety.profile_dir", name=top)

        return None

    # -- LAYER 2 (files) ---------------------------------------------------
    @staticmethod
    def is_protected_file(path: str | os.PathLike[str]) -> bool:
        """A file that must never be deleted automatically."""
        name = Path(str(path)).name.casefold()
        if name in PROTECTED_FILE_NAMES:
            return True
        if any(name.startswith(prefix) for prefix in PROTECTED_FILE_PREFIXES):
            return True
        return Path(name).suffix in PROTECTED_FILE_SUFFIXES

    def contains_protected_files(
        self, path: str | os.PathLike[str], max_entries: int = 400
    ) -> str | None:
        """Scan the first level looking for a sensitive file.

        Deliberately shallow: it is a cheap sanity check against the classic
        case of someone keeping a `.env` inside a folder that happens to be
        named `dist`.
        """
        try:
            with os.scandir(P.with_long_prefix(path)) as it:
                for idx, entry in enumerate(it):
                    if idx >= max_entries:
                        break
                    if entry.is_file(follow_symlinks=False) and self.is_protected_file(entry.name):
                        return entry.name
        except OSError:
            return None
        return None

    # -- Full classification (used by the scanner) -------------------------
    def classify(
        self,
        candidate: Candidate,
        *,
        project_root: str | None,
        markers: tuple[str, ...],
        confidence: float,
        proposed_risk: RiskLevel,
        reason_key: str,
        reason_params: dict[str, Any] | None = None,
    ) -> ValidationOutcome:
        """Decide the final risk. It can only WORSEN the detector's proposal."""
        params = reason_params or {}
        verdict = self.check_path(candidate.path)
        if verdict.blocked:
            return ValidationOutcome(
                risk_level=RiskLevel.PROTECTED,
                confidence=0.0,
                reason_key=reason_key,
                reason_params=params,
                project_root=project_root,
                markers_found=markers,
                protected_reason_key=verdict.reason_key,
                protected_reason_params=verdict.reason_params,
            )

        # An ambiguous name with no proven project never passes.
        if candidate.ambiguous and project_root is None:
            return ValidationOutcome(
                risk_level=RiskLevel.UNKNOWN,
                confidence=min(confidence, 0.3),
                reason_key="safety.ambiguous_no_project",
                reason_params={"name": candidate.name},
                project_root=None,
                markers_found=markers,
            )

        # A sensitive file at the first level means this is not a throwaway dir.
        sensitive = self.contains_protected_files(candidate.path)
        if sensitive is not None:
            return ValidationOutcome(
                risk_level=RiskLevel.PROTECTED,
                confidence=0.0,
                reason_key=reason_key,
                reason_params=params,
                project_root=project_root,
                markers_found=markers,
                protected_reason_key="safety.sensitive_file",
                protected_reason_params={"name": sensitive},
            )

        if confidence < MIN_CONFIDENCE_DELETABLE:
            return ValidationOutcome(
                risk_level=RiskLevel.UNKNOWN,
                confidence=confidence,
                reason_key="safety.low_confidence",
                reason_params={"confidence": f"{confidence:.0%}"},
                project_root=project_root,
                markers_found=markers,
            )

        return ValidationOutcome(
            risk_level=proposed_risk,
            confidence=confidence,
            reason_key=reason_key,
            reason_params=params,
            project_root=project_root,
            markers_found=markers,
        )

    # -- Final gate, immediately before deletion ---------------------------
    def final_gate(
        self,
        path: str | os.PathLike[str],
        *,
        expected_name: str,
        expected_risk: RiskLevel,
        expected_ambiguous: bool = False,
        expected_project_root: str | None = None,
    ) -> Verdict:
        """Re-validate at deletion time. Runs for every item, always.

        Everything here is re-derived from disk rather than read off the
        ScanItem: the whole point is to detect that reality changed since the
        scan.
        """
        if expected_risk is RiskLevel.PROTECTED:
            return _block("safety.already_protected")
        if expected_risk is RiskLevel.UNKNOWN:
            return Verdict(False, RiskLevel.UNKNOWN, "safety.unknown_risk")

        verdict = self.check_path(path)
        if verdict.blocked:
            return verdict

        facts = P.inspect(path)
        if not facts.exists:
            return Verdict(False, RiskLevel.UNKNOWN, "safety.gone")
        if not facts.is_dir:
            return _block("safety.not_a_dir")

        actual_name = Path(P.canonical(path)).name
        if actual_name != expected_name.casefold():
            return _block("safety.name_changed", expected=expected_name, actual=actual_name)

        # An ambiguous name requires its project to still be there.
        if expected_ambiguous or actual_name in AMBIGUOUS_DIR_NAMES:
            if expected_project_root is None:
                return Verdict(False, RiskLevel.UNKNOWN, "safety.ambiguous_no_project",
                               {"name": actual_name})
            if not P.is_within(path, expected_project_root):
                return _block("safety.left_project")
            if not Path(expected_project_root).exists():
                return _block("safety.project_gone")

        sensitive = self.contains_protected_files(path)
        if sensitive is not None:
            return _block("safety.sensitive_file", name=sensitive)

        return Verdict(True, expected_risk, "safety.gate_passed")


def _is_temp(canon: str) -> bool:
    """True when the path lives in OS scratch space.

    Narrow by design: only the directories the operating system itself empties.
    `/private/etc` and `/private/var/db` are not temp and stay blocked.
    """
    if P.IS_WINDOWS:
        return False
    return any(P.is_within(canon, root) for root in POSIX_TEMP_ROOTS)


def _collect_system_roots() -> tuple[str, ...]:
    """Real system paths of this machine, resolved from environment variables.

    Using the variables (instead of hardcoded strings) covers installs outside
    C: and localized Windows builds.
    """
    roots: list[str] = []

    if P.IS_WINDOWS:
        for var in FORBIDDEN_ENV_VARS:
            value = os.environ.get(var)
            if not value:
                continue
            try:
                roots.append(P.canonical(value))
            except Exception:
                continue
    else:
        # None of the Windows variables exist here, so without this branch
        # Layer 1 would be completely empty on Linux and macOS.
        for root in POSIX_SYSTEM_ROOTS:
            if os.path.isdir(root):
                try:
                    roots.append(P.canonical(root))
                except Exception:
                    continue

    # Deliberate note: volume roots (`C:\`) and `C:\Users` are NOT listed here.
    # `is_within` would treat them as ancestors of everything and block the
    # whole drive. They are already refused by the minimum depth rule
    # (`MIN_DELETE_DEPTH`) and by the profile rules in `_check_user_profile`.
    return tuple(dict.fromkeys(roots))
