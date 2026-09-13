"""Disk enumeration and capacity reporting.

Uses only the standard library so DT-Cleaner has no hard dependency on psutil.
`pywin32` is used when available to tell fixed drives from removable and
network ones -- scanning a network share by accident would be slow and
surprising -- but its absence only costs accuracy, never correctness.
"""

from __future__ import annotations

import os
import shutil
import string

from dtcleaner.core.models import DiskInfo
from dtcleaner.utils import paths as P

# GetDriveType return values (winbase.h).
_DRIVE_TYPES = {
    0: "unknown",
    1: "no_root",
    2: "removable",
    3: "fixed",
    4: "network",
    5: "cdrom",
    6: "ramdisk",
}


def drive_type(root: str) -> str:
    """Best-effort drive classification."""
    if not P.IS_WINDOWS:
        return "fixed"
    try:
        import ctypes

        value = ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(root))
        return _DRIVE_TYPES.get(int(value), "unknown")
    except Exception:
        return "unknown"


def list_disks(include_all: bool = False) -> list[DiskInfo]:
    """Enumerate mounted volumes with capacity figures.

    By default only fixed drives are returned: removable media and network
    shares are rarely where dev artifacts pile up, and scanning them is slow.
    """
    disks: list[DiskInfo] = []

    roots = [f"{letter}:\\" for letter in string.ascii_uppercase] if P.IS_WINDOWS else ["/"]

    for root in roots:
        if not os.path.exists(root):
            continue
        kind = drive_type(root)
        if not include_all and kind != "fixed":
            continue
        try:
            usage = shutil.disk_usage(root)
        except OSError:
            continue
        disks.append(
            DiskInfo(
                device=root.rstrip("\\/") or root,
                mountpoint=root,
                total_bytes=usage.total,
                used_bytes=usage.used,
                free_bytes=usage.free,
                drive_type=kind,
            )
        )

    return disks


def list_scannable_roots() -> list[str]:
    """Mount points a Full Scan may walk."""
    return [d.mountpoint for d in list_disks()]


def disk_for_path(path: str | os.PathLike[str]) -> DiskInfo | None:
    """The volume a given path lives on."""
    anchor = P.anchor_of(path)
    if not anchor:
        return None
    for disk in list_disks(include_all=True):
        if P.canonical(disk.mountpoint) == P.canonical(anchor):
            return disk
    return None


def disks_for_paths(paths: list[str]) -> list[DiskInfo]:
    """Deduplicated volumes covering every given path, for the dashboard."""
    seen: set[str] = set()
    found: list[DiskInfo] = []
    for path in paths:
        disk = disk_for_path(path)
        if disk is None:
            continue
        key = P.canonical(disk.mountpoint)
        if key not in seen:
            seen.add(key)
            found.append(disk)
    return found
