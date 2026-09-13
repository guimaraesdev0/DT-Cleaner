"""Windows path parsing and normalization."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from dtcleaner.utils import paths as P

pytestmark = pytest.mark.skipif(not P.IS_WINDOWS, reason="Windows path semantics")


def test_canonical_is_casefolded() -> None:
    assert P.canonical("C:\\Dev\\App") == P.canonical("c:\\DEV\\app")


def test_canonical_resolves_dot_dot() -> None:
    assert P.canonical("C:\\dev\\app\\..\\lib") == P.canonical("C:\\dev\\lib")


def test_canonical_normalizes_forward_slashes() -> None:
    assert P.canonical("C:/dev/app") == P.canonical("C:\\dev\\app")


def test_bare_drive_becomes_root() -> None:
    assert P.canonical("C:") == "c:\\"


def test_drive_root_keeps_its_separator() -> None:
    assert P.canonical("C:\\") == "c:\\"
    assert P.depth_from_root("C:\\") == 0


def test_depth_counting() -> None:
    assert P.depth_from_root("C:\\dev") == 1
    assert P.depth_from_root("C:\\dev\\app\\node_modules") == 3


def test_is_within_uses_components_not_prefixes() -> None:
    assert P.is_within("C:\\dev\\app", "C:\\dev") is True
    assert P.is_within("C:\\dev-old\\app", "C:\\dev") is False
    assert P.is_within("C:\\dev", "C:\\dev") is True
    assert P.is_within("C:\\dev", "C:\\dev\\app") is False


def test_relative_depth() -> None:
    assert P.relative_depth("C:\\dev\\app\\dist", "C:\\dev\\app") == 1
    assert P.relative_depth("C:\\other", "C:\\dev") == -1


def test_long_path_prefix_roundtrip() -> None:
    raw = "C:\\dev\\app"
    prefixed = P.with_long_prefix(raw)
    assert prefixed.startswith(P.LONG_PATH_PREFIX)
    assert P.strip_long_prefix(prefixed).casefold() == raw.casefold()


def test_long_path_is_usable(tmp_path: Path) -> None:
    """A path beyond MAX_PATH must still be stat-able through the prefix."""
    deep = tmp_path
    for _ in range(15):
        deep = deep / ("segment_" + "x" * 15)
    os.makedirs(P.with_long_prefix(deep), exist_ok=True)
    assert len(str(deep)) > 260
    assert P.inspect(deep).is_dir is True


def test_inspect_reports_missing_paths(tmp_path: Path) -> None:
    facts = P.inspect(tmp_path / "does-not-exist")
    assert facts.exists is False
    assert facts.error is not None


def test_junction_is_detected_as_reparse_point(tmp_path: Path) -> None:
    target = tmp_path / "real"
    target.mkdir()
    (target / "keep.txt").write_text("important", encoding="utf-8")
    link = tmp_path / "link"

    result = os.system(f'mklink /J "{link}" "{target}" >nul 2>&1')
    if result != 0 or not link.exists():
        pytest.skip("could not create a junction on this system")

    assert P.is_reparse_point(link) is True
    assert P.is_reparse_point(target) is False


def test_display_path_shortens_the_middle() -> None:
    long_path = "C:\\dev\\" + "\\".join(["folder"] * 12) + "\\node_modules"
    shortened = P.display_path(long_path, max_len=45)
    assert len(shortened) <= 48
    assert shortened.endswith("node_modules")
    assert shortened.lower().startswith("c:")
