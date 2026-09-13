"""Headless UI smoke tests.

These do not assert on pixels. They assert that every screen composes, mounts
and reacts to its key bindings without raising -- which is what actually breaks
when a widget API changes or a translation key is misspelled.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dtcleaner.core.constants import Category, Ecosystem, RiskLevel
from dtcleaner.core.models import ScanItem, ScanSession
from dtcleaner.ui.app import DTCleanerApp
from dtcleaner.ui.screens.help import HelpScreen
from dtcleaner.ui.screens.home import HomeScreen
from dtcleaner.ui.screens.protected import ProtectedScreen
from dtcleaner.ui.screens.results import ResultsScreen
from dtcleaner.ui.screens.settings import SettingsScreen

pytestmark = pytest.mark.asyncio


@pytest.fixture
def session(tmp_path: Path) -> ScanSession:
    project = tmp_path / "app"
    (project / "node_modules").mkdir(parents=True)
    (project / "package.json").write_text("{}", encoding="utf-8")

    safe = ScanItem(
        path=str(project / "node_modules"),
        name="node_modules",
        category=Category.NODE_MODULES,
        ecosystem=Ecosystem.NODE,
        item_type="node_modules",
        size_bytes=5_000_000,
        risk_level=RiskLevel.LOW,
        confidence=0.95,
        project_root=str(project),
        reason_key="detect.proven",
        reason_params={"marker": "package.json", "distance": 1, "ecosystem": "Node"},
        markers_found=("package.json",),
    )
    unknown = ScanItem(
        path=str(tmp_path / "random" / "build"),
        name="build",
        category=Category.OTHER,
        item_type="node_build",
        size_bytes=1_000_000,
        risk_level=RiskLevel.UNKNOWN,
        confidence=0.3,
        ambiguous=True,
        reason_key="safety.ambiguous_no_project",
        reason_params={"name": "build"},
    )
    return ScanSession(items=[safe, unknown], scanned_roots=[str(tmp_path)])


async def test_app_boots_to_home() -> None:
    app = DTCleanerApp(skip_splash=True)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, HomeScreen)


async def test_help_and_settings_open_and_close() -> None:
    app = DTCleanerApp(skip_splash=True)
    async with app.run_test() as pilot:
        await pilot.press("7")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)

        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, HomeScreen)

        await pilot.press("5")
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)


async def test_protected_screen_rejects_a_bogus_path() -> None:
    app = DTCleanerApp(skip_splash=True)
    async with app.run_test() as pilot:
        await pilot.press("4")
        await pilot.pause()
        assert isinstance(app.screen, ProtectedScreen)

        screen = app.screen
        screen.query_one("#path-input").value = "Z:\\nope\\nope"
        screen._add()
        await pilot.pause()
        assert app.config.protected_paths == []


async def test_results_selection_actions(session: ScanSession) -> None:
    app = DTCleanerApp(skip_splash=True)
    async with app.run_test() as pilot:
        app.push_screen(ResultsScreen(session))
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ResultsScreen)

        # 'A' selects only what is safe: the UNKNOWN item must stay untouched.
        screen.action_select_all_safe()
        await pilot.pause()
        selected = session.selected_items
        assert len(selected) == 1
        assert selected[0].name == "node_modules"

        # 'N' clears everything.
        screen.action_deselect_all()
        await pilot.pause()
        assert session.selected_items == []


async def test_removing_an_item_hides_it(session: ScanSession) -> None:
    app = DTCleanerApp(skip_splash=True)
    async with app.run_test() as pilot:
        app.push_screen(ResultsScreen(session))
        await pilot.pause()
        screen = app.screen

        before = len(session.visible_items)
        screen.action_remove()
        await pilot.pause()
        assert len(session.visible_items) == before - 1


async def test_details_modal_renders_for_both_items(session: ScanSession) -> None:
    app = DTCleanerApp(skip_splash=True)
    async with app.run_test() as pilot:
        for item in session.items:
            app.open_details(item)
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()


async def test_language_switch_is_live() -> None:
    app = DTCleanerApp(skip_splash=True)
    async with app.run_test() as pilot:
        from dtcleaner.i18n import set_language, t

        await pilot.pause()
        set_language("pt_br")
        assert t("home.quick_scan") == "Scan Rápido"
        set_language("en")
        assert t("home.quick_scan") == "Quick Scan"
