"""Home screen: the app's menu.

Each entry carries a number key so the whole app is reachable without arrows --
important for people who run this over SSH or in a constrained console.
"""

from __future__ import annotations

from dataclasses import dataclass

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen

from dtcleaner.ui.screens.base import ChromeScreen
from textual.widgets import Static

from dtcleaner.core.constants import ScanMode
from dtcleaner.i18n import t
from dtcleaner.ui.components import MascotLine, StatPanel
from dtcleaner.ui.mascot import Mood
from dtcleaner.ui.theme import PALETTE
from dtcleaner.utils.formatting import human_bytes


@dataclass(frozen=True, slots=True)
class MenuEntry:
    key: str
    title_key: str
    desc_key: str
    action: str


MENU: tuple[MenuEntry, ...] = (
    MenuEntry("1", "home.quick_scan", "home.quick_scan_desc", "quick"),
    MenuEntry("2", "home.full_scan", "home.full_scan_desc", "full"),
    MenuEntry("3", "home.custom_scan", "home.custom_scan_desc", "custom"),
    MenuEntry("4", "home.protected", "home.protected_desc", "protected"),
    MenuEntry("5", "home.settings", "home.settings_desc", "settings"),
    MenuEntry("6", "home.history", "home.history_desc", "history"),
    MenuEntry("7", "home.help", "home.help_desc", "help"),
)


class MenuItem(Static):
    """One row of the menu: key, title, and the description when it fits.

    Single row on purpose. The earlier bordered three-row box clipped its own
    description and pushed entries 6 and 7 off any 24-row terminal.
    """

    #: Below this width the description is dropped rather than truncated to a
    #: couple of useless words.
    DESC_MIN_WIDTH = 58

    def __init__(self, entry: MenuEntry, **kwargs) -> None:
        super().__init__(classes="menu-item", **kwargs)
        self.entry = entry
        self.can_focus = True

    def render(self) -> Text:
        title = t(self.entry.title_key)
        focused = self.has_focus
        text = Text(no_wrap=True, overflow="ellipsis")
        # An explicit caret, not just a background tint: on a low-contrast
        # terminal the tint alone was invisible and the menu felt unresponsive.
        text.append("▸ " if focused else "  ", style=f"bold {PALETTE['accent']}")
        text.append(f" {self.entry.key} ", style=f"bold {PALETTE['bg']} on {PALETTE['accent']}")
        text.append("  ")
        text.append(title, style=f"bold {PALETTE['text']}" if focused else PALETTE["text"])

        width = self.size.width
        if width >= self.DESC_MIN_WIDTH:
            pad = max(1, 24 - len(title))
            text.append(" " * pad)
            text.append(t(self.entry.desc_key), style=PALETTE["text_faint"])
        return text

    def on_focus(self) -> None:
        self.refresh()

    def on_blur(self) -> None:
        self.refresh()

    def on_resize(self) -> None:
        # The description appears and disappears with the width, so the row has
        # to re-render on resize rather than only on focus changes.
        self.refresh()

    def on_click(self) -> None:
        self.screen.trigger(self.entry.action)  # type: ignore[attr-defined]


class HomeScreen(ChromeScreen):
    BINDINGS = [
        Binding("1", "pick('quick')", show=False),
        Binding("2", "pick('full')", show=False),
        Binding("3", "pick('custom')", show=False),
        Binding("4", "pick('protected')", show=False),
        Binding("5", "pick('settings')", show=False),
        Binding("6", "pick('history')", show=False),
        Binding("7", "pick('help')", show=False),
        Binding("enter", "activate", show=False),
        Binding("q", "quit_app", show=False),
        Binding("question_mark", "pick('help')", show=False),
    ]

    def compose_content(self) -> ComposeResult:
        with Vertical(classes="content"):
            yield MascotLine(Mood.IDLE)
            # VerticalScroll, not Vertical: on a very short terminal the menu
            # must stay reachable by scrolling instead of silently losing rows.
            with Horizontal(id="home-body"):
                with VerticalScroll(id="home-menu"):
                    for entry in MENU:
                        yield MenuItem(entry)
                with Vertical(id="home-side"):
                    yield StatPanel(t("history.title"), self._history_rows(), id="home-history")

    def on_mount(self) -> None:
        self.app.set_title(t("home.title"), Mood.IDLE)  # type: ignore[attr-defined]
        self.app.set_keys(  # type: ignore[attr-defined]
            [
                ("1-7", t("keys.navigate")),
                ("ENTER", t("common.ok")),
                ("?", t("keys.help")),
                ("Q", t("keys.quit")),
            ]
        )
        first = self.query(MenuItem).first()
        if first is not None:
            first.focus()

    def _history_rows(self) -> list[tuple[str, str]]:
        history = self.app.history  # type: ignore[attr-defined]
        total = history.total_recovered_bytes()
        cleanups = history.recent_cleanups(limit=1)
        rows = [(t("history.total_recovered"), human_bytes(total))]
        if cleanups:
            last = cleanups[0]
            rows.append((t("history.cleanups"), last.timestamp.strftime("%Y-%m-%d %H:%M")))
        return rows

    # -- actions ------------------------------------------------------------
    def action_activate(self) -> None:
        focused = self.focused
        if isinstance(focused, MenuItem):
            self.trigger(focused.entry.action)

    def action_pick(self, action: str) -> None:
        self.trigger(action)

    def action_quit_app(self) -> None:
        self.app.exit()

    def trigger(self, action: str) -> None:
        app = self.app  # type: ignore[assignment]
        if action == "quick":
            app.start_scan(ScanMode.QUICK)  # type: ignore[attr-defined]
        elif action == "full":
            app.start_scan(ScanMode.FULL)  # type: ignore[attr-defined]
        elif action == "custom":
            app.open_custom_scan()  # type: ignore[attr-defined]
        elif action == "protected":
            app.open_protected()  # type: ignore[attr-defined]
        elif action == "settings":
            app.open_settings()  # type: ignore[attr-defined]
        elif action == "history":
            app.open_history()  # type: ignore[attr-defined]
        elif action == "help":
            app.open_help()  # type: ignore[attr-defined]
