"""LAYER 1 and LAYER 2 guarantees.

These tests are the product's safety net. If any of them ever fails, the app
must not ship: it would mean a system path became deletable.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from dtcleaner.core.constants import MIN_DELETE_DEPTH, RiskLevel
from dtcleaner.core.safety import SafetyEngine
from dtcleaner.utils import paths as P

from .conftest import system_paths

pytestmark = pytest.mark.skipif(not P.IS_WINDOWS, reason="Windows-specific path rules")


@pytest.mark.parametrize("path", list(system_paths()))
def test_system_paths_are_always_blocked(engine: SafetyEngine, path: str) -> None:
    verdict = engine.check_path(path)
    assert verdict.blocked, f"{path} must never be deletable"
    assert verdict.risk is RiskLevel.PROTECTED


def test_traversal_cannot_reach_a_system_path(engine: SafetyEngine) -> None:
    """`..` must not smuggle a path past the denylist."""
    drive = os.environ.get("SystemDrive", "C:")
    sneaky = f"{drive}\\dev\\..\\Windows\\System32"
    assert engine.check_path(sneaky).blocked


def test_short_name_is_resolved_before_matching(engine: SafetyEngine) -> None:
    """8.3 short names (PROGRA~1) resolve to the real folder and stay blocked."""
    drive = os.environ.get("SystemDrive", "C:")
    short = f"{drive}\\PROGRA~1"
    if not os.path.exists(short):
        pytest.skip("8.3 short names disabled on this volume")
    assert engine.check_path(short).blocked


def test_case_does_not_bypass_the_denylist(engine: SafetyEngine) -> None:
    drive = os.environ.get("SystemDrive", "C:")
    assert engine.check_path(f"{drive}\\WiNdOwS\\SySTeM32").blocked


def test_minimum_depth_is_enforced(engine: SafetyEngine) -> None:
    """A folder bolted onto the drive root is never a legitimate artifact."""
    drive = os.environ.get("SystemDrive", "C:")
    assert engine.check_path(f"{drive}\\node_modules").blocked
    assert P.depth_from_root(f"{drive}\\node_modules") < MIN_DELETE_DEPTH


def test_user_profile_root_is_blocked(engine: SafetyEngine) -> None:
    assert engine.check_path(str(P.user_profile())).blocked


@pytest.mark.parametrize("folder", ["Desktop", "Documents", "Downloads", "AppData"])
def test_profile_folders_are_blocked(engine: SafetyEngine, folder: str) -> None:
    assert engine.check_path(str(P.user_profile() / folder)).blocked


def test_appdata_roaming_is_blocked(engine: SafetyEngine) -> None:
    target = P.user_profile() / "AppData" / "Roaming" / "SomeApp"
    assert engine.check_path(str(target)).blocked


def test_a_normal_project_artifact_passes(engine: SafetyEngine, make_tree) -> None:
    base = make_tree({"proj/package.json": "{}", "proj/node_modules/": None})
    verdict = engine.check_path(base / "proj" / "node_modules")
    assert verdict.allowed, verdict.text()


def test_protected_file_names_are_recognized(engine: SafetyEngine) -> None:
    for name in [".env", ".env.production", "package.json", "app.keystore", "data.sqlite3"]:
        assert engine.is_protected_file(Path("C:/x") / name), name


def test_sensitive_file_inside_a_folder_blocks_it(engine: SafetyEngine, make_tree) -> None:
    """A `.env` inside a folder named `dist` means it is not throwaway output."""
    base = make_tree({"proj/package.json": "{}", "proj/dist/.env": "SECRET=1"})
    assert engine.contains_protected_files(base / "proj" / "dist") == ".env"


def test_directory_names_that_are_never_targets(engine: SafetyEngine, make_tree) -> None:
    base = make_tree({"proj/package.json": "{}", "proj/src/": None, "proj/.git/": None})
    assert engine.check_path(base / "proj" / "src").blocked
    assert engine.check_path(base / "proj" / ".git").blocked


def test_reason_is_translatable(engine: SafetyEngine) -> None:
    """Block reasons carry an i18n key, not a hardcoded sentence."""
    from dtcleaner.i18n import set_language

    drive = os.environ.get("SystemDrive", "C:")
    verdict = engine.check_path(f"{drive}\\Windows\\System32")
    set_language("en")
    english = verdict.text()
    set_language("pt_br")
    portuguese = verdict.text()
    set_language("en")
    assert english != portuguese
    assert verdict.reason_key.startswith("safety.")
