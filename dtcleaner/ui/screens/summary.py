"""Cleanup summary.

Failures are reported plainly rather than hidden. A cleaner that quietly
swallows "3 items could not be removed" teaches users not to trust it; one that
says so, and points at the log, stays trustworthy.
"""

from __future__ import annotations

from rich.console import Group
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, Static

from dtcleaner.core.models import CleanupResult
from dtcleaner.i18n import t
from dtcleaner.ui.components import MascotLine
from dtcleaner.ui.mascot import Mood
from dtcleaner.ui.screens.base import ChromeScreen
from dtcleaner.ui.theme import PALETTE
from dtcleaner.utils.formatting import human_bytes, human_duration
from dtcleaner.utils.paths import display_path


class SummaryScreen(ChromeScreen):
    BINDINGS = [
        Binding("escape", "home", show=False),
        Binding("enter", "home", show=False),
    ]

    def __init__(self, result: CleanupResult, protected_count: int = 0, **kwargs) -> None:
        super().__init__(**kwargs)
        self.result = result
        self.protected_count = protected_count

    def compose_content(self) -> ComposeResult:
        mood = Mood.WARNING if self.result.failed_items else Mood.HAPPY
        with VerticalScroll(classes="content"):
            yield MascotLine(mood)
            yield Static(self._summary(), classes="panel")
            if self.result.failed_items or self.result.skipped_items:
                yield Static(self._problems(), classes="panel")
        with Horizontal(id="modal-buttons"):
            yield Button(t("common.ok"), variant="primary", id="home")

    def on_mount(self) -> None:
        mood = Mood.WARNING if self.result.failed_items else Mood.HAPPY
        self.app.set_title(t("summary.title"), mood)  # type: ignore[attr-defined]
        self.app.set_keys([("ENTER", t("keys.back"))])  # type: ignore[attr-defined]

    def _summary(self) -> Group:
        table = Table.grid(padding=(0, 3))
        table.add_column(style=PALETTE["text_dim"], no_wrap=True)
        table.add_column(style=PALETTE["text"], justify="right")

        table.add_row(
            t("summary.space_recovered"),
            Text(human_bytes(self.result.recovered_bytes), style=f"bold {PALETTE['ok']}"),
        )
        table.add_row(t("summary.items_deleted"), str(len(self.result.deleted_items)))
        if self.result.failed_items:
            table.add_row(
                t("summary.items_failed"),
                Text(str(len(self.result.failed_items)), style=PALETTE["danger"]),
            )
        if self.result.skipped_items:
            table.add_row(
                t("summary.items_skipped"),
                Text(str(len(self.result.skipped_items)), style=PALETTE["warn"]),
            )
        if self.protected_count:
            table.add_row(t("summary.protected_ignored"), str(self.protected_count))
        table.add_row(
            t("summary.total_time"), human_duration(self.result.duration_seconds or 0)
        )
        if self.result.log_path:
            table.add_row(
                t("summary.log_path"),
                Text(display_path(self.result.log_path, 48), style=PALETTE["info"]),
            )

        footer_key = (
            "summary.had_failures" if self.result.failed_items else "summary.run_again"
        )
        footer_style = PALETTE["warn"] if self.result.failed_items else PALETTE["text_dim"]
        return Group(table, Text(""), Text(t(footer_key), style=footer_style))

    def _problems(self) -> Group:
        table = Table.grid(padding=(0, 2))
        table.add_column(style=PALETTE["text"], no_wrap=True)
        table.add_column(style=PALETTE["text_dim"])

        for outcome in (self.result.skipped_items + self.result.failed_items)[:10]:
            reason = outcome.skipped_reason_text() or t(outcome.error or "error.unexpected")
            table.add_row(display_path(outcome.path, 50), reason)

        return Group(
            Text(t("cleanup.failed"), style=f"bold {PALETTE['warn']}"), Text(""), table
        )

    def on_button_pressed(self) -> None:
        self.action_home()

    def action_home(self) -> None:
        self.app.switch_to_home()  # type: ignore[attr-defined]
