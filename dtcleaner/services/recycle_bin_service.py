"""Deletion backends: Recycle Bin and permanent removal.

Recycle Bin is the default because it is the only undo DT-Cleaner can offer. A
wrong call that lands in the bin is an inconvenience; the same call with
permanent deletion is data loss.

Permanent deletion still handles the two Windows failure modes that break naive
`shutil.rmtree`: read-only files (common in `node_modules`) and paths over
MAX_PATH (routine in nested dependency trees).
"""

from __future__ import annotations

import os
import shutil
import stat
from dataclasses import dataclass

from dtcleaner.utils import paths as P

try:  # pragma: no cover - availability depends on the environment
    from send2trash import send2trash as _send2trash

    SEND2TRASH_AVAILABLE = True
except Exception:  # noqa: BLE001
    _send2trash = None  # type: ignore[assignment]
    SEND2TRASH_AVAILABLE = False


@dataclass(frozen=True, slots=True)
class DeleteReport:
    success: bool
    method: str
    error_key: str | None = None
    error_detail: str | None = None


def move_to_recycle_bin(path: str | os.PathLike[str]) -> DeleteReport:
    """Send a directory to the Recycle Bin.

    Deliberately does NOT fall back to permanent deletion on failure. The user
    asked for a recoverable delete; silently upgrading it to an irreversible one
    would break the promise the Preview screen made.
    """
    if not SEND2TRASH_AVAILABLE or _send2trash is None:
        return DeleteReport(False, "recycle_bin", "error.unexpected", "send2trash not installed")

    try:
        # send2trash needs a plain absolute path; the long-path prefix confuses
        # the shell API it calls.
        _send2trash(os.path.abspath(str(path)))
        return DeleteReport(True, "recycle_bin")
    except Exception as exc:  # noqa: BLE001 - shell API raises many exception types
        return DeleteReport(False, "recycle_bin", _error_key(exc), str(exc))


def delete_permanently(path: str | os.PathLike[str]) -> DeleteReport:
    """Remove a directory tree for good."""
    target = P.with_long_prefix(path)
    try:
        shutil.rmtree(target, onerror=_force_writable)
        return DeleteReport(True, "permanent")
    except OSError as exc:
        return DeleteReport(False, "permanent", _error_key(exc), str(exc))
    except Exception as exc:  # noqa: BLE001
        return DeleteReport(False, "permanent", "error.unexpected", str(exc))


def _force_writable(func, path, exc_info) -> None:  # noqa: ANN001
    """rmtree error handler: clear the read-only bit and retry once.

    npm and pip both leave read-only files behind on Windows, which makes a
    plain rmtree fail on trees that are otherwise perfectly deletable.
    """
    error = exc_info[1]
    if isinstance(error, PermissionError):
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
            return
        except OSError:
            pass
    raise error


def _error_key(exc: BaseException) -> str:
    winerror = getattr(exc, "winerror", None)
    errno = getattr(exc, "errno", None)
    if winerror == 5 or errno == 13:
        return "error.access_denied"
    if winerror == 32:
        return "error.file_in_use"
    if winerror == 206:
        return "error.path_too_long"
    if winerror in (2, 3) or errno == 2:
        return "error.not_found"
    return "error.unexpected"
