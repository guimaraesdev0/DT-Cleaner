"""Cross-platform safety coverage.

The Windows denylist resolves through environment variables that do not exist
on POSIX. Without a POSIX equivalent, Layer 1 would be completely empty on
Linux and macOS -- the scanner would still mostly behave, but the structural
guarantee the product is built on would not be there.

These tests check the data, so they run on every platform, plus the live path
rules where the platform allows it.
"""

from __future__ import annotations

import sys

import pytest

from dtcleaner.core.constants import (
    PLATFORM_SUPPORT,
    POSIX_PROTECTED_HOME_DIRS,
    POSIX_SYSTEM_DIR_NAMES,
    POSIX_SYSTEM_ROOTS,
    SYSTEM_DIR_NAMES,
)
from dtcleaner.core.safety import SafetyEngine
from dtcleaner.utils import paths as P

#: Directories that must be refused on a POSIX host.
CRITICAL_POSIX = ["/etc", "/usr", "/var", "/bin", "/lib", "/boot", "/sbin", "/dev", "/proc"]

#: macOS specifics.
CRITICAL_MACOS = ["/System", "/Library", "/Applications", "/private"]


@pytest.mark.parametrize("path", CRITICAL_POSIX + CRITICAL_MACOS)
def test_critical_posix_paths_are_declared(path: str) -> None:
    """Data-level check: runs on Windows too, so the list cannot silently rot."""
    assert path in POSIX_SYSTEM_ROOTS, f"{path} missing from POSIX_SYSTEM_ROOTS"


@pytest.mark.parametrize("path", CRITICAL_POSIX + CRITICAL_MACOS)
def test_critical_posix_names_are_declared(path: str) -> None:
    name = path.strip("/").casefold()
    assert name in POSIX_SYSTEM_DIR_NAMES, f"{name} missing from POSIX_SYSTEM_DIR_NAMES"


def test_posix_and_windows_lists_do_not_collide() -> None:
    """A name in both lists would make one platform's rule silently govern the
    other's. `boot` is the one legitimate overlap."""
    assert SYSTEM_DIR_NAMES & POSIX_SYSTEM_DIR_NAMES == {"boot"}


def test_home_config_dirs_are_declared() -> None:
    for name in (".local", ".cache", ".gnupg"):
        assert name in POSIX_PROTECTED_HOME_DIRS


def test_every_supported_platform_has_a_level() -> None:
    for platform in ("win32", "linux", "darwin"):
        assert PLATFORM_SUPPORT[platform] in ("supported", "experimental")


def test_current_platform_is_known() -> None:
    """An unknown platform is not a crash, but `doctor` must be able to warn."""
    assert PLATFORM_SUPPORT.get(sys.platform) in (None, "supported", "experimental")


@pytest.mark.skipif(P.IS_WINDOWS, reason="POSIX path rules")
@pytest.mark.parametrize("path", CRITICAL_POSIX)
def test_posix_system_paths_are_blocked_live(path: str) -> None:
    """The real check, on a real POSIX host."""
    import os

    if not os.path.isdir(path):
        pytest.skip(f"{path} does not exist here")
    verdict = SafetyEngine().check_path(path)
    assert verdict.blocked, f"{path} must never be deletable"


@pytest.mark.skipif(P.IS_WINDOWS, reason="POSIX path rules")
def test_posix_system_subpaths_are_blocked_live() -> None:
    """Depth alone is not enough: `/usr/lib` is two levels down."""
    import os

    engine = SafetyEngine()
    for path in ("/usr/lib", "/etc/ssl", "/var/log"):
        if os.path.isdir(path):
            assert engine.check_path(path).blocked, path


@pytest.mark.skipif(P.IS_WINDOWS, reason="POSIX path rules")
def test_a_normal_posix_project_artifact_passes(make_tree) -> None:
    base = make_tree({"proj/package.json": "{}", "proj/node_modules/": None})
    verdict = SafetyEngine().check_path(base / "proj" / "node_modules")
    assert verdict.allowed, verdict.text()
