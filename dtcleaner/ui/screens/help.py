"""Help screen.

Doubles as the product's safety disclosure. Users trust a deletion tool more
when it explains its own rules, and a user who understands the rules makes
better decisions on the review screen.
"""

from __future__ import annotations

from rich.console import Group
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen

from dtcleaner.ui.screens.base import ChromeScreen
from textual.widgets import Static

from dtcleaner.core.constants import RiskLevel
from dtcleaner.i18n import t
from dtcleaner.ui.components import MascotLine
from dtcleaner.ui.mascot import Mood
from dtcleaner.ui.theme import PALETTE, risk_markup

SHORTCUTS: tuple[tuple[str, str], ...] = (
    ("↑ ↓ / TAB", "keys.navigate"),
    ("SPACE", "keys.toggle"),
    ("A", "keys.select_all_safe"),
    ("N", "keys.deselect_all"),
    ("D", "keys.details"),
    ("R", "keys.remove"),
    ("P", "keys.protect"),
    ("C", "keys.confirm_cleanup"),
    ("/", "keys.filter"),
    ("ESC", "keys.back"),
    ("Q", "keys.quit"),
)

RULES: tuple[str, ...] = (
    "help.rule_1",
    "help.rule_2",
    "help.rule_3",
    "help.rule_4",
    "help.rule_5",
    "help.rule_6",
)


class HelpScreen(ChromeScreen):
    BINDINGS = [Binding("escape", "back", show=False)]

    def compose_content(self) -> ComposeResult:
        caps = self.app.caps  # type: ignore[attr-defined]
        with VerticalScroll(classes="content"):
            yield MascotLine(Mood.IDLE)
            yield Static(self._rules(), classes="panel")
            yield Static(self._risks(), classes="panel")
            yield Static(self._shortcuts(), classes="panel")

    def on_mount(self) -> None:
        self.app.set_title(t("help.title"), Mood.IDLE)  # type: ignore[attr-defined]
        self.app.set_keys([("ESC", t("keys.back"))])  # type: ignore[attr-defined]
        self.focus_first_control()

    def _rules(self) -> Group:
        body = Text()
        for index, key in enumerate(RULES, start=1):
            body.append(f" {index}. ", style=PALETTE["accent"])
            body.append(f"{t(key)}\n", style=PALETTE["text"])
        return Group(
            Text(t("help.how_it_works"), style=f"bold {PALETTE['accent']}"), Text(""), body
        )

    def _risks(self) -> Group:
        table = Table.grid(padding=(0, 2))
        table.add_column(no_wrap=True)
        table.add_column(style=PALETTE["text_dim"])
        for risk in RiskLevel:
            table.add_row(
                Text.from_markup(risk_markup(risk)), t(f"risk.{risk.value}.desc")
            )
        return Group(Text(t("common.risk"), style=f"bold {PALETTE['accent']}"), Text(""), table)

    def _shortcuts(self) -> Group:
        table = Table.grid(padding=(0, 3))
        table.add_column(style=f"bold {PALETTE['accent']}", no_wrap=True)
        table.add_column(style=PALETTE["text"])
        for key, label in SHORTCUTS:
            table.add_row(key, t(label))
        return Group(
            Text(t("help.shortcuts"), style=f"bold {PALETTE['accent']}"), Text(""), table
        )

    def action_back(self) -> None:
        self.app.switch_to_home()  # type: ignore[attr-defined]
