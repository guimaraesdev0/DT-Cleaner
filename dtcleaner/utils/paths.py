r"""Path normalization and inspection, Windows-first.

Golden rule of this module: every security comparison runs against the
CANONICAL form of a path (fully resolved, no `..`, no 8.3 short names,
casefolded on Windows). Comparing raw strings would allow trivial bypasses
such as `C:\Windows\..\Windows\System32`.
"""

from __future__ import annotations

import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path, PurePath, PureWindowsPath

IS_WINDOWS = sys.platform == "win32"

# FILE_ATTRIBUTE_REPARSE_POINT covers junctions, symlinks and cloud placeholders.
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
FILE_ATTRIBUTE_SYSTEM = 0x4
FILE_ATTRIBUTE_HIDDEN = 0x2

LONG_PATH_PREFIX = "\\\\?\\"
UNC_LONG_PATH_PREFIX = "\\\\?\\UNC\\"

SEP = "\\" if IS_WINDOWS else "/"


def canonical(path: str | os.PathLike[str]) -> str:
    r"""Return the canonical form used by every safety rule.

    - resolves `..`, `.` and 8.3 short names (via realpath)
    - strips the long-path prefix
    - normalizes separators
    - casefolds on Windows (case-insensitive filesystem)
    - drops the trailing separator, except on a drive root (`C:\`)
    """
    raw = str(path)

    # A bare drive letter ("C:") is *per-drive CWD relative* to the OS, so
    # realpath would silently expand it to wherever the process happens to be.
    # In a tool that deletes things, reading it as the drive ROOT is the safe
    # interpretation: the root is then rejected by the depth rule.
    if IS_WINDOWS and len(raw) == 2 and raw[1] == ":" and raw[0].isalpha():
        return raw.casefold() + "\\"

    try:
        resolved = os.path.realpath(raw)
    except (OSError, ValueError):
        resolved = os.path.abspath(raw)

    resolved = strip_long_prefix(resolved)
    resolved = os.path.normpath(resolved)

    if IS_WINDOWS:
        resolved = resolved.replace("/", "\\")
        # A bare `C:` is relative to that drive's CWD; normalize it to the root.
        if len(resolved) == 2 and resolved[1] == ":":
            resolved += "\\"
        if len(resolved) > 3:
            resolved = resolved.rstrip("\\")
        resolved = resolved.casefold()
    else:
        if len(resolved) > 1:
            resolved = resolved.rstrip("/")

    return resolved


def strip_long_prefix(path: str) -> str:
    if path.startswith(UNC_LONG_PATH_PREFIX):
        return "\\\\" + path[len(UNC_LONG_PATH_PREFIX) :]
    if path.startswith(LONG_PATH_PREFIX):
        return path[len(LONG_PATH_PREFIX) :]
    return path


def with_long_prefix(path: str | os.PathLike[str]) -> str:
    r"""Prefix a path with `\\?\` so it can exceed MAX_PATH (260 chars).

    Required because nested `node_modules` blows past 260 characters easily and
    the Win32 APIs fail with ERROR_PATH_NOT_FOUND without this prefix.
    """
    raw = os.path.abspath(str(path))
    if not IS_WINDOWS:
        return raw
    if raw.startswith(LONG_PATH_PREFIX):
        return raw
    if raw.startswith("\\\\"):
        return UNC_LONG_PATH_PREFIX + raw[2:]
    return LONG_PATH_PREFIX + raw


def _pure(canon: str) -> PurePath:
    return PureWindowsPath(canon) if IS_WINDOWS else PurePath(canon)


def full_parts(path: str | os.PathLike[str]) -> tuple[str, ...]:
    """Canonical path components, anchor included."""
    return tuple(_pure(canonical(path)).parts)


def parts_of(path: str | os.PathLike[str]) -> tuple[str, ...]:
    r"""Canonical path components below the anchor (`C:\` or `/`)."""
    pure = _pure(canonical(path))
    return tuple(pure.parts[1:]) if pure.anchor and pure.parts else tuple(pure.parts)


def depth_from_root(path: str | os.PathLike[str]) -> int:
    r"""Levels below the volume root. `C:\` is 0, `C:\dev` is 1."""
    return len(parts_of(path))


def anchor_of(path: str | os.PathLike[str]) -> str:
    return _pure(canonical(path)).anchor


def is_same_path(a: str | os.PathLike[str], b: str | os.PathLike[str]) -> bool:
    return canonical(a) == canonical(b)


def is_within(child: str | os.PathLike[str], parent: str | os.PathLike[str]) -> bool:
    r"""True when `child` lives inside `parent` (or is `parent` itself).

    Compares component by component, never with a string `startswith`:
    `C:\dev-old` must NOT count as a child of `C:\dev`.
    """
    c_parts = full_parts(child)
    p_parts = full_parts(parent)
    if len(c_parts) < len(p_parts):
        return False
    return c_parts[: len(p_parts)] == p_parts


def relative_depth(child: str | os.PathLike[str], parent: str | os.PathLike[str]) -> int:
    """Distance in levels from `parent` down to `child`; -1 when unrelated."""
    if not is_within(child, parent):
        return -1
    return len(full_parts(child)) - len(full_parts(parent))


@dataclass(frozen=True, slots=True)
class PathFacts:
    """Objective facts about a path, gathered in a single syscall."""

    exists: bool
    is_dir: bool
    is_file: bool
    is_reparse_point: bool
    is_system: bool
    is_hidden: bool
    error: str | None = None


def inspect(path: str | os.PathLike[str]) -> PathFacts:
    """Collect attributes without following links (lstat)."""
    try:
        st = os.lstat(with_long_prefix(path))
    except (OSError, ValueError) as exc:
        return PathFacts(False, False, False, False, False, False, error=str(exc))

    attrs = getattr(st, "st_file_attributes", 0)
    mode = st.st_mode
    is_link = stat.S_ISLNK(mode) or bool(attrs & FILE_ATTRIBUTE_REPARSE_POINT)
    return PathFacts(
        exists=True,
        is_dir=stat.S_ISDIR(mode),
        is_file=stat.S_ISREG(mode),
        is_reparse_point=is_link,
        is_system=bool(attrs & FILE_ATTRIBUTE_SYSTEM),
        is_hidden=bool(attrs & FILE_ATTRIBUTE_HIDDEN),
    )


def is_reparse_point(path: str | os.PathLike[str]) -> bool:
    """Junction / symlink / cloud placeholder.

    Critical: deleting a junction can wipe the contents of its TARGET. The
    scanner never traverses one and the cleanup engine never removes one.
    """
    return inspect(path).is_reparse_point


def entry_is_reparse_point(entry: os.DirEntry) -> bool:
    """Cheap variant for use inside the walk (reuses the DirEntry cache)."""
    try:
        if entry.is_symlink():
            return True
        st = entry.stat(follow_symlinks=False)
        return bool(getattr(st, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT)
    except OSError:
        return True  # fail-closed: with no information, treat it as a link


def display_path(path: str | os.PathLike[str], max_len: int = 60) -> str:
    """Shorten a path in the middle, keeping the anchor and the leaf name."""
    text = str(path)
    if len(text) <= max_len:
        return text
    p = Path(text)
    head = p.anchor.rstrip("\\/") or text[:2]
    tail = p.name
    budget = max_len - len(head) - len(tail) - 5
    middle = str(p.parent)[len(p.anchor) :]
    if budget > 0 and len(middle) > budget:
        middle = "..." + middle[-budget:]
    joined = f"{head}{SEP}{middle}{SEP}{tail}"
    return joined.replace(SEP + SEP, SEP)


def user_profile() -> Path:
    return Path(os.path.expanduser("~"))


def app_dir() -> Path:
    r"""`%USERPROFILE%\.dt-cleaner` (DTC_HOME overrides it; used by tests)."""
    override = os.environ.get("DTC_HOME")
    if override:
        return Path(override)
    return user_profile() / ".dt-cleaner"
