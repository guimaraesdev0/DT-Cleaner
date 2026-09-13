"""The tests that justify the product's existence.

Every case here is a folder whose NAME matches a known artifact but whose
CONTEXT says otherwise. All of them must end up non-deletable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dtcleaner.core.confidence import Classifier
from dtcleaner.core.constants import RiskLevel
from dtcleaner.core.safety import SafetyEngine
from dtcleaner.core.validators.context import ContextValidator


@pytest.fixture
def classifier(engine: SafetyEngine) -> Classifier:
    return Classifier(safety=engine, validator=ContextValidator())


def classify_dir(classifier: Classifier, path: Path):
    """Run the full detector -> context -> safety pipeline on one directory."""
    candidates = classifier.detect(str(path), path.name, path.parent.name)
    return classifier.classify(candidates)


# --- ambiguous names with no project ---------------------------------------


def test_bare_build_folder_is_not_deletable(classifier: Classifier, make_tree) -> None:
    """A folder called `build` with no project marker anywhere near it."""
    base = make_tree({"random/build/notes.txt": "just some files"})
    item = classify_dir(classifier, base / "random" / "build")

    assert item is not None
    assert item.risk_level is RiskLevel.UNKNOWN
    assert item.is_selectable is False


def test_bare_dist_folder_is_not_deletable(classifier: Classifier, make_tree) -> None:
    base = make_tree({"archive/dist/photo.jpg": "binary-ish"})
    item = classify_dir(classifier, base / "archive" / "dist")

    assert item is not None
    assert item.is_selectable is False


def test_target_without_cargo_toml_is_not_deletable(classifier: Classifier, make_tree) -> None:
    """`target` is meaningless outside a Rust project."""
    base = make_tree({"shooting-range/target/scores.csv": "10,9,8"})
    item = classify_dir(classifier, base / "shooting-range" / "target")

    assert item is not None
    assert item.risk_level is RiskLevel.UNKNOWN
    assert item.is_selectable is False


def test_bin_without_a_dotnet_project_is_not_deletable(classifier: Classifier, make_tree) -> None:
    base = make_tree({"scripts/bin/deploy.sh": "#!/bin/sh"})
    item = classify_dir(classifier, base / "scripts" / "bin")

    assert item is not None
    assert item.is_selectable is False


# --- the same names WITH proven context ------------------------------------


def test_target_with_cargo_toml_is_deletable(classifier: Classifier, make_tree) -> None:
    base = make_tree(
        {
            "mytool/Cargo.toml": '[package]\nname = "mytool"',
            "mytool/src/main.rs": "fn main() {}",
            "mytool/target/debug/": None,
        }
    )
    item = classify_dir(classifier, base / "mytool" / "target")

    assert item is not None
    assert item.is_selectable is True
    assert item.project_root is not None
    assert "cargo.toml" in item.markers_found


def test_dist_with_package_json_is_deletable(classifier: Classifier, make_tree) -> None:
    base = make_tree(
        {
            "web/package.json": '{"name":"web"}',
            "web/package-lock.json": "{}",
            "web/dist/index.js": "console.log(1)",
        }
    )
    item = classify_dir(classifier, base / "web" / "dist")

    assert item is not None
    assert item.is_selectable is True
    assert item.confidence >= 0.6


def test_node_modules_next_to_package_json_scores_high(
    classifier: Classifier, make_tree
) -> None:
    base = make_tree(
        {
            "app/package.json": '{"name":"app"}',
            "app/yarn.lock": "",
            "app/node_modules/react/index.js": "",
        }
    )
    item = classify_dir(classifier, base / "app" / "node_modules")

    assert item is not None
    assert item.risk_level is RiskLevel.LOW
    assert item.confidence >= 0.85
    assert item.should_autoselect(safe_mode=True) is True


# --- distance and containment ----------------------------------------------


def test_ambiguous_name_far_from_its_marker_loses_confidence(
    classifier: Classifier, make_tree
) -> None:
    """A `dist` buried six levels below package.json is not obviously output."""
    base = make_tree(
        {
            "mono/package.json": '{"name":"mono"}',
            "mono/a/b/c/d/e/dist/file.txt": "x",
        }
    )
    item = classify_dir(classifier, base / "mono" / "a" / "b" / "c" / "d" / "e" / "dist")

    assert item is not None
    assert item.is_selectable is False


def test_nearest_project_wins_in_a_monorepo(classifier: Classifier, make_tree) -> None:
    base = make_tree(
        {
            "mono/package.json": '{"name":"root"}',
            "mono/packages/ui/package.json": '{"name":"ui"}',
            "mono/packages/ui/dist/bundle.js": "",
        }
    )
    item = classify_dir(classifier, base / "mono" / "packages" / "ui" / "dist")

    assert item is not None
    assert Path(item.project_root or "").name == "ui"


# --- sensitive content overrides everything --------------------------------


def test_env_file_inside_dist_blocks_it(classifier: Classifier, make_tree) -> None:
    """Even with a perfect Node project, a `.env` inside makes it untouchable."""
    base = make_tree(
        {
            "web/package.json": '{"name":"web"}',
            "web/dist/.env": "API_KEY=secret",
        }
    )
    item = classify_dir(classifier, base / "web" / "dist")

    assert item is not None
    assert item.protected is True
    assert item.is_selectable is False
    assert item.protected_reason_key == "safety.sensitive_file"


def test_user_protected_path_beats_a_perfect_detection(make_tree) -> None:
    base = make_tree(
        {
            "client/package.json": '{"name":"client"}',
            "client/node_modules/lib/index.js": "",
        }
    )
    engine = SafetyEngine()
    engine.reload_protected([str(base / "client")])
    classifier = Classifier(safety=engine, validator=ContextValidator())

    item = classify_dir(classifier, base / "client" / "node_modules")
    assert item is not None
    assert item.protected is True
    assert item.is_selectable is False


# --- tool-owned names without a project ------------------------------------


def test_pycache_without_a_project_is_detected_but_not_autoselected(
    classifier: Classifier, make_tree
) -> None:
    """`__pycache__` means one thing, but no project still means no auto-select."""
    base = make_tree({"loose/scripts/__pycache__/mod.cpython-312.pyc": "x"})
    item = classify_dir(classifier, base / "loose" / "scripts" / "__pycache__")

    assert item is not None
    assert item.should_autoselect(safe_mode=True) is False


def test_venv_is_never_detected(classifier: Classifier, make_tree) -> None:
    """Virtual environments are deliberately out of scope."""
    base = make_tree({"proj/pyproject.toml": "[project]", "proj/.venv/pyvenv.cfg": ""})
    assert classify_dir(classifier, base / "proj" / ".venv") is None


def test_selection_of_a_blocked_item_is_refused(classifier: Classifier, make_tree) -> None:
    """The model itself refuses to be selected, not just the UI."""
    base = make_tree({"random/build/x.txt": "x"})
    item = classify_dir(classifier, base / "random" / "build")

    assert item is not None
    assert item.set_selected(True) is False
    assert item.selected is False
