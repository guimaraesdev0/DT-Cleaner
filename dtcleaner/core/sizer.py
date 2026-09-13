"""Directory size calculation.

Sizing is the expensive part of a scan (`node_modules` routinely holds 30k+
files), so it runs only on candidates that already survived detection and
safety classification -- never on the whole tree.

Two rules matter for correctness:

* reparse points are counted as zero and never traversed, otherwise a junction
  pointing at `C:\\` would make the scan walk the whole disk;
* errors are swallowed per entry, so one Access Denied deep inside does not
  lose the size of everything else.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime

from dtcleaner.core.models import ScanItem
from dtcleaner.utils import paths as P
from dtcleaner.utils.concurrency import CancelToken


@dataclass(frozen=True, slots=True)
class SizeReport:
    total_bytes: int
    file_count: int
    last_modified: datetime | None
    error: str | None = None


def measure(
    path: str | os.PathLike[str], token: CancelToken | None = None
) -> SizeReport:
    """Walk a directory iteratively and sum the size of every regular file.

    Iterative rather than recursive: deep `node_modules` trees can exceed
    Python's recursion limit, and an explicit stack is also faster.
    """
    total = 0
    files = 0
    newest: float | None = None
    error: str | None = None

    stack: list[str] = [str(path)]
    while stack:
        if token is not None and token.cancelled:
            break
        current = stack.pop()
        try:
            with os.scandir(P.with_long_prefix(current)) as it:
                for entry in it:
                    try:
                        if P.entry_is_reparse_point(entry):
                            # Never follow: a junction could point anywhere.
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                            continue
                        st = entry.stat(follow_symlinks=False)
                        total += st.st_size
                        files += 1
                        if newest is None or st.st_mtime > newest:
                            newest = st.st_mtime
                    except OSError as exc:
                        error = error or _describe(exc)
        except OSError as exc:
            error = error or _describe(exc)

    modified = datetime.fromtimestamp(newest) if newest is not None else None
    return SizeReport(total, files, modified, error)


def measure_items(
    items: list[ScanItem],
    *,
    workers: int = 8,
    token: CancelToken | None = None,
    on_progress=None,
) -> None:
    """Fill in size fields for every item, in parallel.

    Threads are the right tool here despite the GIL: this is I/O bound on disk
    metadata, and `os.scandir` releases the GIL while it waits.
    """
    if not items:
        return

    done = 0
    total = len(items)

    def work(item: ScanItem) -> None:
        report = measure(item.path, token)
        item.size_bytes = report.total_bytes
        item.file_count = report.file_count
        item.last_modified = report.last_modified
        item.size_error = report.error

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for _ in pool.map(work, items):
            done += 1
            if token is not None and token.cancelled:
                break
            if on_progress is not None:
                on_progress(done, total)


def _describe(exc: OSError) -> str:
    """Map an OSError onto a translatable error key."""
    winerror = getattr(exc, "winerror", None)
    if winerror == 5 or exc.errno == 13:
        return "error.access_denied"
    if winerror == 206 or exc.errno == 36:
        return "error.path_too_long"
    if winerror == 32:
        return "error.file_in_use"
    if winerror in (2, 3) or exc.errno == 2:
        return "error.not_found"
    return "error.unexpected"
