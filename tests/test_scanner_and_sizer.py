"""Scanner walk behavior, size calculation and i18n."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from dtcleaner.core.config import AppConfig
from dtcleaner.core.constants import ScanMode
from dtcleaner.core.safety import SafetyEngine
from dtcleaner.core.scanner import Scanner
from dtcleaner.core.sizer import measure
from dtcleaner.i18n import AVAILABLE_LANGUAGES, set_language, t
from dtcleaner.utils.concurrency import CancelToken, Throttle


@pytest.fixture
def workspace(make_tree, fill_dir) -> Path:
    base = make_tree(
        {
            "web/package.json": '{"name":"web"}',
            "web/yarn.lock": "",
            "api/pyproject.toml": "[project]",
            "orphan/build/readme.txt": "not a project",
        }
    )
    fill_dir(base / "web" / "node_modules" / "react", 4, 2048)
    fill_dir(base / "api" / "__pycache__", 3, 1024)
    fill_dir(base / "orphan" / "build", 2, 512)
    return base


def run_scan(base: Path, **config_overrides) -> object:
    config = AppConfig(**config_overrides)
    scanner = Scanner(config=config, safety=SafetyEngine())
    return scanner.scan([str(base)], ScanMode.CUSTOM)


# --- sizing -----------------------------------------------------------------


def test_measure_sums_files(tmp_path: Path, fill_dir) -> None:
    expected = fill_dir(tmp_path / "data", 5, 1000)
    report = measure(tmp_path / "data")
    assert report.total_bytes == expected
    assert report.file_count == 5
    assert report.last_modified is not None


def test_measure_handles_a_missing_path(tmp_path: Path) -> None:
    report = measure(tmp_path / "nope")
    assert report.total_bytes == 0
    assert report.error is not None


def test_measure_does_not_follow_junctions(tmp_path: Path, fill_dir) -> None:
    """A junction must contribute zero, or sizes would be double counted."""
    real = tmp_path / "real"
    fill_dir(real, 3, 1000)
    container = tmp_path / "container"
    container.mkdir()
    link = container / "link"

    if os.system(f'mklink /J "{link}" "{real}" >nul 2>&1') != 0 or not link.exists():
        pytest.skip("could not create a junction on this system")

    assert measure(container).total_bytes == 0


def test_measure_stops_when_cancelled(tmp_path: Path, fill_dir) -> None:
    fill_dir(tmp_path / "data", 3, 100)
    token = CancelToken()
    token.cancel()
    assert measure(tmp_path / "data", token).file_count == 0


# --- scanning ---------------------------------------------------------------


def test_scan_finds_the_expected_artifacts(workspace: Path) -> None:
    session = run_scan(workspace)
    names = {item.name for item in session.items}
    assert "node_modules" in names
    assert "__pycache__" in names


def test_scan_marks_the_orphan_build_as_unselectable(workspace: Path) -> None:
    session = run_scan(workspace)
    # Match on the item name, not on a substring of the path: pytest's temp
    # directory names embed the test name and would match "orphan" themselves.
    orphan = next(i for i in session.items if i.name == "build")
    assert orphan.is_selectable is False
    assert orphan.selected is False
    assert orphan.project_root is None


def test_safe_mode_preselects_only_high_confidence_low_risk(workspace: Path) -> None:
    session = run_scan(workspace, safe_mode=True)
    for item in session.selected_items:
        assert item.risk_level.value == "LOW"
        assert item.confidence >= 0.85


def test_scan_skips_user_protected_subtrees(workspace: Path) -> None:
    config = AppConfig()
    config.add_protected(workspace / "web")
    scanner = Scanner(
        config=config, safety=SafetyEngine(user_protected=config.protected_paths)
    )
    session = scanner.scan([str(workspace)], ScanMode.CUSTOM)
    assert not any("web" in item.path for item in session.items)


def test_scan_does_not_descend_into_node_modules(workspace: Path) -> None:
    """Finding the top is enough; walking 30k nested files is pure waste."""
    nested = workspace / "web" / "node_modules" / "react" / "node_modules"
    nested.mkdir(parents=True)
    (nested / "dep.js").write_text("x", encoding="utf-8")

    session = run_scan(workspace)
    assert not any(
        item.path.count("node_modules") > 1 for item in session.items
    )


def test_scan_is_cancellable(workspace: Path) -> None:
    config = AppConfig()
    scanner = Scanner(config=config, safety=SafetyEngine())
    scanner.cancel()
    session = scanner.scan([str(workspace)], ScanMode.CUSTOM)
    assert session.cancelled is True


def test_scan_records_missing_roots_without_crashing(tmp_path: Path) -> None:
    session = run_scan(tmp_path / "does-not-exist")
    assert session.errors
    assert session.items == []


def test_scan_session_aggregates(workspace: Path) -> None:
    session = run_scan(workspace)
    assert session.total_recoverable_bytes > 0
    assert session.project_count >= 2
    assert session.duration_seconds is not None


# --- i18n -------------------------------------------------------------------


def test_every_key_exists_in_every_locale() -> None:
    """A missing translation would silently render an English string."""
    from dtcleaner.i18n import _load_locale

    english = set(_load_locale("en"))
    for code in AVAILABLE_LANGUAGES:
        other = set(_load_locale(code))
        assert english - other == set(), f"{code} is missing keys"


def test_language_switch_changes_output() -> None:
    set_language("en")
    english = t("home.quick_scan")
    set_language("pt_br")
    portuguese = t("home.quick_scan")
    set_language("en")
    assert english != portuguese


def test_unknown_language_falls_back_to_english() -> None:
    set_language("klingon")
    assert t("common.yes") == "Yes"


def test_missing_key_renders_as_itself() -> None:
    assert t("this.key.does.not.exist") == "this.key.does.not.exist"


def test_throttle_limits_calls() -> None:
    calls: list[int] = []
    throttle = Throttle(interval=10.0)
    for _ in range(5):
        throttle.call(calls.append, 1)
    assert len(calls) == 1


def test_throttle_force_always_calls() -> None:
    calls: list[int] = []
    throttle = Throttle(interval=10.0)
    throttle.force(calls.append, 1)
    throttle.force(calls.append, 1)
    assert len(calls) == 2
