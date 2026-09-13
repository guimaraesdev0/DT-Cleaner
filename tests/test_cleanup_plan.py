"""CleanupPlan construction and the final safety gate.

The gate tests are the most important in the file: they prove that an item can
pass the scan and still be refused at deletion time when reality changed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dtcleaner.core.cleanup import CleanupEngine, build_plan
from dtcleaner.core.constants import Category, DeleteMode, Ecosystem, RiskLevel
from dtcleaner.core.models import ScanItem, ScanSession
from dtcleaner.core.safety import SafetyEngine


def make_item(path: Path, **overrides) -> ScanItem:
    defaults = dict(
        path=str(path),
        name=path.name,
        category=Category.NODE_MODULES,
        ecosystem=Ecosystem.NODE,
        item_type="node_modules",
        size_bytes=1024,
        risk_level=RiskLevel.LOW,
        confidence=0.95,
        project_root=str(path.parent),
    )
    defaults.update(overrides)
    return ScanItem(**defaults)


@pytest.fixture
def project(make_tree) -> Path:
    return make_tree(
        {
            "app/package.json": '{"name":"app"}',
            "app/node_modules/lib/index.js": "module.exports = 1",
        }
    )


# --- plan building ----------------------------------------------------------


def test_plan_contains_only_selected_items(project: Path) -> None:
    keep = make_item(project / "app" / "node_modules")
    drop = make_item(project / "app" / "node_modules", size_bytes=2048)
    keep.set_selected(True)

    session = ScanSession(items=[keep, drop])
    plan = build_plan(session)

    assert plan.item_count == 1
    assert plan.items[0].id == keep.id
    assert plan.total_size == 1024


def test_removed_items_never_reach_the_plan(project: Path) -> None:
    item = make_item(project / "app" / "node_modules")
    item.set_selected(True)
    item.remove_from_list()

    plan = build_plan(ScanSession(items=[item]))
    assert plan.item_count == 0
    assert plan.excluded_count == 1


def test_protected_items_never_reach_the_plan(project: Path) -> None:
    item = make_item(project / "app" / "node_modules")
    item.set_selected(True)
    item.mark_protected("safety.user_protected", root="C:/dev")

    plan = build_plan(ScanSession(items=[item]))
    assert plan.item_count == 0
    assert plan.protected_count == 1


def test_permanent_mode_requires_extra_confirmation(project: Path) -> None:
    item = make_item(project / "app" / "node_modules")
    item.set_selected(True)
    plan = build_plan(ScanSession(items=[item]), DeleteMode.PERMANENT)

    assert plan.requires_extra_confirmation is True
    assert "preview.permanent_warning" in plan.warnings


def test_high_risk_triggers_a_warning(project: Path) -> None:
    item = make_item(project / "app" / "node_modules", risk_level=RiskLevel.HIGH)
    item.set_selected(True)
    plan = build_plan(ScanSession(items=[item]))

    assert "preview.risk_warning" in plan.warnings
    assert plan.requires_extra_confirmation is True


# --- the final gate ---------------------------------------------------------


def test_gate_accepts_an_unchanged_item(engine: SafetyEngine, project: Path) -> None:
    target = project / "app" / "node_modules"
    verdict = engine.final_gate(
        target,
        expected_name="node_modules",
        expected_risk=RiskLevel.LOW,
        expected_project_root=str(project / "app"),
    )
    assert verdict.allowed, verdict.text()


def test_gate_rejects_a_vanished_path(engine: SafetyEngine, tmp_path: Path) -> None:
    verdict = engine.final_gate(
        tmp_path / "gone",
        expected_name="gone",
        expected_risk=RiskLevel.LOW,
    )
    assert verdict.blocked
    assert verdict.reason_key == "safety.gone"


def test_gate_rejects_a_renamed_target(engine: SafetyEngine, project: Path) -> None:
    """The scan saw `node_modules`; by cleanup time the folder is something else."""
    original = project / "app" / "node_modules"
    renamed = project / "app" / "important_data"
    original.rename(renamed)

    verdict = engine.final_gate(
        renamed,
        expected_name="node_modules",
        expected_risk=RiskLevel.LOW,
        expected_project_root=str(project / "app"),
    )
    assert verdict.blocked
    assert verdict.reason_key == "safety.name_changed"


def test_gate_rejects_an_ambiguous_item_whose_project_disappeared(
    engine: SafetyEngine, make_tree
) -> None:
    base = make_tree({"web/package.json": "{}", "web/dist/bundle.js": ""})
    (base / "web" / "package.json").unlink()

    verdict = engine.final_gate(
        base / "web" / "dist",
        expected_name="dist",
        expected_risk=RiskLevel.LOW,
        expected_ambiguous=True,
        expected_project_root=str(base / "web" / "nonexistent"),
    )
    assert verdict.blocked


def test_gate_rejects_unknown_and_protected_risks(engine: SafetyEngine, project: Path) -> None:
    target = project / "app" / "node_modules"
    for risk in (RiskLevel.UNKNOWN, RiskLevel.PROTECTED):
        verdict = engine.final_gate(
            target, expected_name="node_modules", expected_risk=risk
        )
        assert verdict.blocked, risk


def test_gate_rejects_when_a_sensitive_file_appears(
    engine: SafetyEngine, project: Path
) -> None:
    """Something dropped a .env into the folder between scan and cleanup."""
    target = project / "app" / "node_modules"
    (target / ".env").write_text("SECRET=1", encoding="utf-8")

    verdict = engine.final_gate(
        target,
        expected_name="node_modules",
        expected_risk=RiskLevel.LOW,
        expected_project_root=str(project / "app"),
    )
    assert verdict.blocked
    assert verdict.reason_key == "safety.sensitive_file"


# --- execution --------------------------------------------------------------


def test_blocked_item_is_skipped_not_deleted(engine: SafetyEngine, project: Path) -> None:
    """A gate failure must skip that item and leave it on disk."""
    target = project / "app" / "node_modules"
    item = make_item(target, risk_level=RiskLevel.UNKNOWN, confidence=0.95)
    plan = build_plan(ScanSession(items=[]), DeleteMode.PERMANENT)
    plan.items = [item]  # force it past selection, as a hostile caller would

    result = CleanupEngine(safety=engine).execute(plan)

    assert target.exists(), "a blocked item must never be deleted"
    assert len(result.skipped_items) == 1
    assert len(result.deleted_items) == 0


def test_permanent_delete_removes_the_tree(engine: SafetyEngine, project: Path) -> None:
    target = project / "app" / "node_modules"
    item = make_item(target)
    item.set_selected(True)

    session = ScanSession(items=[item])
    plan = build_plan(session, DeleteMode.PERMANENT)
    result = CleanupEngine(safety=engine).execute(plan)

    assert not target.exists()
    assert len(result.deleted_items) == 1
    assert result.recovered_bytes == item.size_bytes


def test_engine_never_raises_on_a_bad_item(engine: SafetyEngine, tmp_path: Path) -> None:
    """One broken item must not abort the whole run."""
    missing = make_item(tmp_path / "not-there")
    plan = build_plan(ScanSession(items=[]), DeleteMode.PERMANENT)
    plan.items = [missing]

    result = CleanupEngine(safety=engine).execute(plan)
    assert len(result.outcomes) == 1
    assert result.finished_at is not None
