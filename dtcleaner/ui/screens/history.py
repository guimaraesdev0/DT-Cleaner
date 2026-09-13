"""History screen: past scans and cleanups."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from dtcleaner.i18n import t
from dtcleaner.ui.components import EmptyState
from dtcleaner.ui.mascot import Mood
from dtcleaner.ui.screens.base import ChromeScreen
from dtcleaner.ui.theme import PALETTE
from dtcleaner.utils.formatting import human_bytes, human_duration
from dtcleaner.utils.paths import display_path


class HistoryScreen(ChromeScreen):
    BINDINGS = [Binding("escape", "back", show=False)]

    def compose_content(self) -> ComposeResult:
        history = self.app.history  # type: ignore[attr-defined]
        scans = history.recent_scans(limit=15)
        cleanups = history.recent_cleanups(limit=15)

        if not scans and not cleanups:
            yield EmptyState(
                self.app.caps,  # type: ignore[attr-defined]
                t("history.title"),
                t("history.empty"),
            )
            return

        with Vertical(classes="content"):
            yield Static(
                f"{t('history.total_recovered')}: "
                f"[{PALETTE['ok']} bold]{human_bytes(history.total_recovered_bytes())}[/]"
            )
            yield Static(t("history.cleanups"), classes="panel-title")
            yield DataTable(id="cleanups", cursor_type="row")
            yield Static(t("history.scans"), classes="panel-title")
            yield DataTable(id="scans", cursor_type="row")

    def on_mount(self) -> None:
        self.app.set_title(t("history.title"), Mood.IDLE)  # type: ignore[attr-defined]
        self.app.set_keys([("ESC", t("keys.back"))])  # type: ignore[attr-defined]
        self.focus_first_control()

        history = self.app.history  # type: ignore[attr-defined]
        cleanups = history.recent_cleanups(limit=15)
        scans = history.recent_scans(limit=15)
        if not cleanups and not scans:
            return

        cleanup_table = self.query_one("#cleanups", DataTable)
        cleanup_table.add_columns(
            t("common.modified"),
            t("summary.space_recovered"),
            t("summary.items_deleted"),
            t("summary.items_failed"),
            t("summary.log_path"),
        )
        for entry in cleanups:
            cleanup_table.add_row(
                entry.timestamp.strftime("%Y-%m-%d %H:%M"),
                Text(human_bytes(entry.recovered_bytes), style=PALETTE["ok"]),
                str(entry.deleted_items),
                Text(
                    str(entry.failed_items),
                    style=PALETTE["danger"] if entry.failed_items else PALETTE["text_dim"],
                ),
                display_path(entry.log_path or "--", 40),
            )

        scan_table = self.query_one("#scans", DataTable)
        scan_table.add_columns(
            t("common.modified"),
            t("scan.mode_title"),
            t("common.items"),
            t("results.recoverable"),
            t("results.duration"),
        )
        for entry in scans:
            scan_table.add_row(
                entry.timestamp.strftime("%Y-%m-%d %H:%M"),
                entry.scan_mode or "--",
                str(entry.items_found),
                human_bytes(entry.recoverable_bytes),
                human_duration(entry.duration_seconds),
            )

    def action_back(self) -> None:
        self.app.switch_to_home()  # type: ignore[attr-defined]
