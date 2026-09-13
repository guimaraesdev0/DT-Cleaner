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
    POSIX_TEMP_ROOTS,
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
    assert {"boot"} == SYSTEM_DIR_NAMES & POSIX_SYSTEM_DIR_NAMES


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


# --- the temp carve-out -----------------------------------------------------
# macOS resolves /tmp and /var into /private, so every temp directory becomes
# /private/var/folders/... -- inside two system roots. The engine refused every
# path under the system temp directory, which is where the sandbox script builds
# its demo tree and where the whole test suite works. The carve-out fixes that,
# and must stay narrow enough not to unblock anything real.

#: Paths that must stay blocked even though they share a prefix with temp.
SENSITIVE_NEAR_TEMP = [
    "/private/etc",
    "/private/var/db",
    "/private/var/root",
    "/private/var/log",
    "/var/db",
    "/var/log",
    "/var/root",
    "/usr/lib",
    "/etc/ssl",
]


def _within_posix(child: str, parent: str) -> bool:
    """Component-wise containment, independent of the host platform."""
    from pathlib import PurePosixPath

    c = PurePosixPath(child).parts
    p = PurePosixPath(parent).parts
    return len(c) >= len(p) and c[: len(p)] == p


@pytest.mark.parametrize("path", SENSITIVE_NEAR_TEMP)
def test_temp_carveout_does_not_cover_system_paths(path: str) -> None:
    """Data-level, so it runs on Windows too and cannot silently rot."""
    covering = [root for root in POSIX_TEMP_ROOTS if _within_posix(path, root)]
    assert not covering, f"{path} would be exempted by {covering}"


@pytest.mark.parametrize(
    "path",
    [
        "/tmp/dtc-sandbox/web-app/node_modules",
        "/private/var/folders/ab/xyz/T/dtc-sandbox/api/__pycache__",
        "/var/folders/ab/xyz/T/pytest-of-runner/pytest-0/test_x0/workspace",
    ],
)
def test_temp_paths_are_recognised_as_scratch(path: str) -> None:
    assert any(_within_posix(path, root) for root in POSIX_TEMP_ROOTS), (
        f"{path} is scratch space and should be exempt from the system rules"
    )


def test_every_temp_root_is_absolute_and_narrow() -> None:
    """A bare '/' or a one-segment root would exempt half the filesystem."""
    for root in POSIX_TEMP_ROOTS:
        assert root.startswith("/")
        assert len(root.rstrip("/").split("/")) >= 2, root


@pytest.mark.skipif(P.IS_WINDOWS, reason="POSIX path rules")
def test_sensitive_paths_near_temp_stay_blocked_live() -> None:
    import os

    engine = SafetyEngine()
    for path in SENSITIVE_NEAR_TEMP:
        if os.path.isdir(path):
            assert engine.check_path(path).blocked, f"{path} must stay blocked"


@pytest.mark.skipif(P.IS_WINDOWS, reason="POSIX path rules")
def test_a_project_in_the_system_temp_dir_is_scannable(tmp_path) -> None:
    """This is what the sandbox script and the test suite actually do."""
    project = tmp_path / "web-app"
    (project / "node_modules").mkdir(parents=True)
    (project / "package.json").write_text("{}", encoding="utf-8")

    verdict = SafetyEngine().check_path(project / "node_modules")
    assert verdict.allowed, verdict.text()
