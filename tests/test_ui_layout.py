"""Responsive layout regression tests.

The app was shipping a layout that fell apart on resize: the header and status
bar were mounted on the default screen and covered by every pushed screen, the
filter input had no `-hidden` rule so it was always visible, and the results
table used fixed columns that overflowed a narrow terminal.

These tests run every screen at a range of terminal sizes and assert the
structural invariants that were broken.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dtcleaner.core.constants import Category, Ecosystem, RiskLevel
from dtcleaner.core.models import ScanItem, ScanSession
from dtcleaner.ui.app import DTCleanerApp
from dtcleaner.ui.components import AppHeader, StatusBar
from dtcleaner.ui.screens.base import ChromeScreen
from dtcleaner.ui.screens.help import HelpScreen
from dtcleaner.ui.screens.history import HistoryScreen
from dtcleaner.ui.screens.preview import PreviewScreen
from dtcleaner.ui.screens.protected import ProtectedScreen
from dtcleaner.ui.screens.results import ResultsScreen
from dtcleaner.ui.screens.settings import SettingsScreen

pytestmark = pytest.mark.asyncio

#: Smallest is a cramped SSH window; largest is a maximized ultrawide.
SIZES = [(60, 18), (72, 22), (80, 24), (100, 30), (140, 45), (220, 60)]


@pytest.fixture
def session(tmp_path: Path) -> ScanSession:
    project = tmp_path / "app"
    (project / "node_modules").mkdir(parents=True)
    (project / "package.json").write_text("{}", encoding="utf-8")

    items = [
        ScanItem(
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
            selected=True,
        ),
        ScanItem(
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
        ),
    ]
    return ScanSession(items=items, scanned_roots=[str(tmp_path)])


def _inside_scrollable(widget) -> bool:
    """True when an ancestor scrolls, so overflowing it vertically is intended."""
    from textual.containers import ScrollableContainer, VerticalScroll

    for ancestor in widget.ancestors:
        if isinstance(ancestor, (VerticalScroll, ScrollableContainer)):
            return True
    return False


def assert_fits(app, width: int, height: int, label: str) -> None:
    """No widget may overflow the viewport.

    Horizontal overflow is never acceptable: there is no horizontal scrolling
    anywhere in this app, so anything past the right edge is simply lost.
    Vertical overflow is only acceptable inside a scrollable container.
    """
    for widget in app.screen.query("*"):
        if not widget.display:
            continue
        region = widget.region
        assert region.right <= width, (
            f"{label} @{width}x{height}: {widget.__class__.__name__}"
            f"#{widget.id or '-'} reaches column {region.right}"
        )
        if not _inside_scrollable(widget):
            assert region.bottom <= height, (
                f"{label} @{width}x{height}: {widget.__class__.__name__}"
                f"#{widget.id or '-'} reaches row {region.bottom}"
            )


@pytest.mark.parametrize("size", SIZES)
async def test_home_fits_and_shows_every_entry(size) -> None:
    from dtcleaner.ui.screens.home import MENU, MenuItem

    width, height = size
    app = DTCleanerApp(skip_splash=True)
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        assert_fits(app, width, height, "home")
        # Every menu entry must exist, at every size. Previously the bordered
        # three-row items pushed entries 6 and 7 out of a 24-row terminal.
        assert len(app.screen.query(MenuItem)) == len(MENU)


#: Opened one per test rather than in a loop: pushing and popping four screens
#: inside a single pilot run floods the message queue and times out the pause.
SECONDARY_SCREENS = ["help", "settings", "protected", "history"]


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("screen_name", SECONDARY_SCREENS)
async def test_chrome_is_visible_on_every_screen(size, screen_name: str) -> None:
    """Header and status bar belong to the screen, not the app.

    Mounted on the app they were covered by every pushed screen, so the key
    hints the app kept updating were never actually on screen.
    """
    width, height = size
    app = DTCleanerApp(skip_splash=True)
    async with app.run_test(size=size) as pilot:
        getattr(app, f"open_{screen_name}")()
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, ChromeScreen)
        assert screen.query(AppHeader), f"{screen_name} lost its header"
        assert screen.query(StatusBar), f"{screen_name} lost its status bar"
        assert_fits(app, width, height, screen_name)


@pytest.mark.parametrize("size", SIZES)
async def test_results_fits_and_keeps_the_table(size, session: ScanSession) -> None:
    width, height = size
    app = DTCleanerApp(skip_splash=True)
    async with app.run_test(size=size) as pilot:
        app.push_screen(ResultsScreen(session))
        await pilot.pause()
        await pilot.pause()
        assert_fits(app, width, height, "results")

        from textual.widgets import DataTable

        table = app.screen.query_one("#items", DataTable)
        # The table is the point of the screen: it must never be squeezed away.
        assert table.display
        assert table.size.height >= 3, "the results table collapsed"
        assert table.row_count == len(session.visible_items)


@pytest.mark.parametrize("size", SIZES)
async def test_preview_fits(size, session: ScanSession) -> None:
    width, height = size
    app = DTCleanerApp(skip_splash=True)
    async with app.run_test(size=size) as pilot:
        app.push_screen(PreviewScreen(session))
        await pilot.pause()
        await pilot.pause()
        assert_fits(app, width, height, "preview")


async def test_filter_input_is_hidden_until_requested(session: ScanSession) -> None:
    """The `-hidden` class had no CSS rule, so the filter was always on screen."""
    from textual.widgets import Input

    app = DTCleanerApp(skip_splash=True)
    async with app.run_test(size=(100, 30)) as pilot:
        app.push_screen(ResultsScreen(session))
        await pilot.pause()
        field = app.screen.query_one("#filter-input", Input)
        assert field.display is False

        app.screen.action_filter()
        await pilot.pause()
        assert field.display is True


async def test_table_columns_adapt_to_width(session: ScanSession) -> None:
    """Narrow terminals drop columns instead of overflowing them off screen."""
    narrow = DTCleanerApp(skip_splash=True)
    async with narrow.run_test(size=(60, 20)) as pilot:
        narrow.push_screen(ResultsScreen(session))
        await pilot.pause()
        await pilot.pause()
        narrow_columns = narrow.screen._columns

    wide = DTCleanerApp(skip_splash=True)
    async with wide.run_test(size=(200, 50)) as pilot:
        wide.push_screen(ResultsScreen(session))
        await pilot.pause()
        await pilot.pause()
        wide_columns = wide.screen._columns

    assert len(narrow_columns) < len(wide_columns)
    # Whatever is dropped, the user must still see what is selected and how big.
    for essential in ("sel", "name", "size"):
        assert essential in narrow_columns


async def test_breakpoint_classes_are_applied() -> None:
    app = DTCleanerApp(skip_splash=True)
    async with app.run_test(size=(60, 20)) as pilot:
        await pilot.pause()
        assert "-compact" in app.screen.classes
    app = DTCleanerApp(skip_splash=True)
    async with app.run_test(size=(200, 60)) as pilot:
        await pilot.pause()
        assert "-wide" in app.screen.classes


async def test_resizing_a_live_screen_does_not_break_it(session: ScanSession) -> None:
    """Resize while a screen is mounted, which is what the user actually does."""
    app = DTCleanerApp(skip_splash=True)
    async with app.run_test(size=(140, 45)) as pilot:
        app.push_screen(ResultsScreen(session))
        await pilot.pause()
        for size in [(60, 18), (200, 60), (80, 24), (100, 30)]:
            await pilot.resize_terminal(*size)
            await pilot.pause()
            await pilot.pause()
            assert_fits(app, size[0], size[1], "results after resize")
            assert app.screen.query_one("#items").row_count == len(session.visible_items)


# --- discoverability --------------------------------------------------------
# The results screen listed eight key hints with "C  Confirm cleanup" second
# from the end. The status bar drops hints from the right, so C was truncated
# away at EVERY terminal width and users could not find how to start a cleanup.


@pytest.mark.parametrize("size", SIZES)
async def test_continue_key_is_always_visible(size, session: ScanSession) -> None:
    from dtcleaner.ui.components import StatusBar

    app = DTCleanerApp(skip_splash=True)
    async with app.run_test(size=size) as pilot:
        app.push_screen(ResultsScreen(session))
        await pilot.pause()
        await pilot.pause()

        bar = app.screen.query_one(StatusBar).render().plain
        assert " C " in bar, f"the continue key vanished at {size}: {bar!r}"
        assert bar.lstrip().startswith("C"), "the primary action must lead the bar"


@pytest.mark.parametrize("size", SIZES)
async def test_summary_states_the_next_step(size, session: ScanSession) -> None:
    """The counts alone never told the user the screen went anywhere."""
    from textual.widgets import Static

    app = DTCleanerApp(skip_splash=True)
    async with app.run_test(size=size) as pilot:
        app.push_screen(ResultsScreen(session))
        await pilot.pause()
        await pilot.pause()

        summary = app.screen.query_one("#selection-summary", Static).render().plain
        assert " C " in summary, f"no call to action at {size}: {summary!r}"
        # It leads the line, so a narrow terminal truncates the counts instead.
        assert summary.index(" C ") < 30


async def test_call_to_action_adapts_to_an_empty_selection(session: ScanSession) -> None:
    from textual.widgets import Static

    for item in session.items:
        item.selected = False

    app = DTCleanerApp(skip_splash=True)
    async with app.run_test(size=(110, 30)) as pilot:
        app.push_screen(ResultsScreen(session))
        await pilot.pause()
        await pilot.pause()

        summary = app.screen.query_one("#selection-summary", Static).render().plain
        assert " C " in summary
        assert "select" in summary.lower() or "selecione" in summary.lower()


async def test_primary_hint_survives_a_resize(session: ScanSession) -> None:
    from dtcleaner.ui.components import StatusBar

    app = DTCleanerApp(skip_splash=True)
    async with app.run_test(size=(140, 45)) as pilot:
        app.push_screen(ResultsScreen(session))
        await pilot.pause()
        for width, height in [(60, 18), (200, 60), (80, 24)]:
            await pilot.resize_terminal(width, height)
            await pilot.pause()
            await pilot.pause()
            bar = app.screen.query_one(StatusBar).render().plain
            assert " C " in bar, f"continue key lost after resizing to {width}x{height}"
