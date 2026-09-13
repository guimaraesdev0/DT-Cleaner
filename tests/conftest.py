"""Shared fixtures.

`make_project` builds throwaway project trees so detector and safety tests run
against a real filesystem instead of mocks -- reparse points, casing and depth
rules only behave realistically on real paths.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from pathlib import Path

import pytest

from dtcleaner.core import config as config_module
from dtcleaner.core.safety import SafetyEngine
from dtcleaner.i18n import set_language


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the app's config directory at a temp folder for every test."""
    home = tmp_path / ".dt-cleaner-home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DTC_HOME", str(home))
    config_module.reset_cache()
    set_language("en")
    yield home
    config_module.reset_cache()


@pytest.fixture
def engine() -> SafetyEngine:
    return SafetyEngine()


@pytest.fixture
def make_tree(tmp_path: Path) -> Callable[..., Path]:
    """Create a directory tree from a mapping of relative path -> content.

    A trailing "/" marks a directory; anything else becomes a file.

        make_tree({"proj/package.json": "{}", "proj/node_modules/": None})
    """

    def _make(spec: dict[str, str | None], root: Path | None = None) -> Path:
        base = root or tmp_path / "workspace"
        base.mkdir(parents=True, exist_ok=True)
        for rel, content in spec.items():
            target = base / rel
            if rel.endswith("/") or content is None:
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
        return base

    return _make


@pytest.fixture
def fill_dir() -> Callable[[Path, int, int], int]:
    """Write `count` files of `size` bytes into a directory; return total bytes."""

    def _fill(directory: Path, count: int = 3, size: int = 1024) -> int:
        directory.mkdir(parents=True, exist_ok=True)
        for idx in range(count):
            (directory / f"chunk_{idx}.bin").write_bytes(b"x" * size)
        return count * size

    return _fill


def system_paths() -> Iterable[str]:
    """Paths that must be blocked on any Windows machine."""
    drive = os.environ.get("SystemDrive", "C:")
    return (
        f"{drive}\\",
        f"{drive}\\Windows",
        f"{drive}\\Windows\\System32",
        f"{drive}\\Windows\\System32\\drivers\\etc",
        f"{drive}\\Program Files",
        f"{drive}\\Program Files (x86)",
        f"{drive}\\ProgramData",
        f"{drive}\\Users",
        f"{drive}\\$Recycle.Bin",
        f"{drive}\\Recovery",
    )
