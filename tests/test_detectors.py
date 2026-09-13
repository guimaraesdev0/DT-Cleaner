"""Detector rules and the context validator."""

from __future__ import annotations

from pathlib import Path

import pytest

from dtcleaner.core.constants import Category, Ecosystem
from dtcleaner.core.detectors.base import all_detectors
from dtcleaner.core.detectors.node import NodeDetector
from dtcleaner.core.detectors.python_ import PythonDetector
from dtcleaner.core.validators.context import ContextValidator


@pytest.fixture
def validator() -> ContextValidator:
    return ContextValidator()


# --- detectors --------------------------------------------------------------


def test_node_detector_recognizes_node_modules() -> None:
    candidate = NodeDetector().inspect("C:/dev/app/node_modules", "node_modules", "app")
    assert candidate is not None
    assert candidate.category is Category.NODE_MODULES
    assert candidate.ambiguous is False


def test_node_detector_flags_dist_as_ambiguous() -> None:
    candidate = NodeDetector().inspect("C:/dev/app/dist", "dist", "app")
    assert candidate is not None
    assert candidate.ambiguous is True
    assert candidate.base_confidence < 0.6


def test_detector_matching_is_case_insensitive() -> None:
    assert NodeDetector().inspect("C:/x/Node_Modules", "Node_Modules", "x") is not None


def test_python_detector_recognizes_egg_info() -> None:
    candidate = PythonDetector().inspect("C:/p/mypkg.egg-info", "mypkg.egg-info", "p")
    assert candidate is not None
    assert candidate.item_type == "egg_info"


def test_unknown_directory_matches_nothing() -> None:
    assert all(
        d.inspect("C:/x/my-photos", "my-photos", "x") is None for d in all_detectors()
    )


def test_ambiguous_names_are_claimed_by_several_detectors() -> None:
    """`build` belongs to no one, which is exactly why context decides."""
    claims = [d for d in all_detectors() if d.inspect("C:/x/build", "build", "x")]
    assert len(claims) >= 2


def test_android_rule_prefers_the_app_parent() -> None:
    from dtcleaner.core.detectors.android import AndroidDetector

    generic = AndroidDetector().inspect("C:/p/other/build", "build", "other")
    specific = AndroidDetector().inspect("C:/p/android/app/build", "build", "app")
    assert specific is not None
    assert specific.item_type == "android_app_build"
    # A `build` whose parent is neither `app` nor `android` is not Android output.
    assert generic is None


# --- context validator ------------------------------------------------------


def test_validator_finds_the_nearest_marker(validator: ContextValidator, make_tree) -> None:
    base = make_tree({"proj/package.json": "{}", "proj/dist/": None})
    context = validator.find(base / "proj" / "dist", Ecosystem.NODE, ambiguous=True)

    assert context.proven is True
    assert context.distance == 1
    assert Path(context.root or "").name == "proj"


def test_validator_respects_the_distance_limit(
    validator: ContextValidator, make_tree
) -> None:
    base = make_tree({"proj/Cargo.toml": "[package]", "proj/a/b/c/d/e/f/target/": None})
    context = validator.find(
        base / "proj" / "a" / "b" / "c" / "d" / "e" / "f" / "target",
        Ecosystem.RUST,
        ambiguous=True,
    )
    assert context.proven is False


def test_validator_does_not_cross_ecosystems(
    validator: ContextValidator, make_tree
) -> None:
    """A Cargo.toml does not validate a Node `dist`."""
    base = make_tree({"proj/Cargo.toml": "[package]", "proj/dist/": None})
    context = validator.find(base / "proj" / "dist", Ecosystem.NODE, ambiguous=True)
    assert context.proven is False


def test_validator_caches_directory_lookups(
    validator: ContextValidator, make_tree
) -> None:
    base = make_tree({"proj/package.json": "{}", "proj/dist/": None, "proj/build/": None})
    validator.find(base / "proj" / "dist", Ecosystem.NODE, ambiguous=True)
    before = len(validator._dir_cache)
    validator.find(base / "proj" / "build", Ecosystem.NODE, ambiguous=True)
    # The shared ancestor was already cached, so no new entry for it.
    assert len(validator._dir_cache) == before


def test_validator_survives_an_unreadable_directory(validator: ContextValidator) -> None:
    assert validator.markers_in("C:/definitely/not/here") == frozenset()


def test_detect_ecosystem(validator: ContextValidator, make_tree) -> None:
    base = make_tree({"rs/Cargo.toml": "[package]", "py/pyproject.toml": "[project]"})
    assert validator.detect_ecosystem(base / "rs") is Ecosystem.RUST
    assert validator.detect_ecosystem(base / "py") is Ecosystem.PYTHON
    assert validator.detect_ecosystem(base) is Ecosystem.UNKNOWN
