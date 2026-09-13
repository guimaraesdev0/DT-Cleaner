"""Cleanup progress screen.

Kept deliberately quiet: one current item, one progress bar, three counters.
Streaming every deleted path would fill the terminal with thousands of lines
and bury the only thing that matters -- whether anything went wrong. Failures
and skips are counted here and detailed in the log and the summary.
"""

from __future__ import annotations

from rich.console import Group
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen

from dtcleaner.ui.screens.base import ChromeScreen
from textual.widgets import ProgressBar, Static

from dtcleaner.core.cleanup import CleanupProgress
from dtcleaner.core.models import CleanupPlan
from dtcleaner.i18n import t
from dtcleaner.ui.components import MascotLine
from dtcleaner.ui.mascot import Mood
from dtcleaner.ui.theme import PALETTE, category_markup
from dtcleaner.utils.formatting import human_bytes
from dtcleaner.utils.paths import display_path


class CleanupScreen(ChromeScreen):
    """No cancel binding on purpose.

    Interrupting mid-tree could leave a half-deleted folder, which is worse than
    finishing: the engine already deletes one item at a time, so the blast
    radius of "let it finish" is a single artifact.
    """

    def __init__(self, plan: CleanupPlan, **kwargs) -> None:
        super().__init__(**kwargs)
        self.plan = plan
        self._frame = 0
        self._last: CleanupProgress | None = None

    def compose_content(self) -> ComposeResult:
        caps = self.app.caps  # type: ignore[attr-defined]
        with Vertical(classes="content"):
            yield MascotLine(Mood.WORKING, id="cleanup-mascot")
            yield ProgressBar(total=self.plan.item_count, show_eta=False, id="cleanup-bar")
            yield Static("", id="cleanup-current")
            yield Static("", id="cleanup-stats", classes="panel")

    def on_mount(self) -> None:
        self.app.set_title(t("cleanup.title"), Mood.WORKING)  # type: ignore[attr-defined]
        self.app.set_keys([])  # type: ignore[attr-defined]
        self._render_stats(None)
        if self.app.config.animations:  # type: ignore[attr-defined]
            self.set_interval(0.14, self._tick_frame)

    def _tick_frame(self) -> None:
        self._frame += 1
        box = self.query_one("#cleanup-mascot", MascotLine)
        box.frame = self._frame
        box.refresh()
        self.app.tick_header(self._frame)  # type: ignore[attr-defined]

    # -- called from the worker thread --------------------------------------
    def update_progress(self, progress: CleanupProgress) -> None:
        self._last = progress
        self.query_one("#cleanup-bar", ProgressBar).update(
            total=progress.total, progress=progress.done
        )

        current = Text()
        current.append(f"{t('cleanup.current_item')}: ", style=PALETTE["text_dim"])
        current.append(display_path(progress.item.path, 62), style=PALETTE["text"])
        self.query_one("#cleanup-current", Static).update(current)
        self._render_stats(progress)

    def _render_stats(self, progress: CleanupProgress | None) -> None:
        table = Table.grid(padding=(0, 3))
        table.add_column(style=PALETTE["text_dim"], no_wrap=True)
        table.add_column(style=PALETTE["text"], justify="right")

        done = progress.done if progress else 0
        total = progress.total if progress else self.plan.item_count
        freed = progress.freed_bytes if progress else 0

        table.add_row(t("cleanup.progress", done=done, total=total), "")
        table.add_row(t("cleanup.freed_so_far"), Text(human_bytes(freed), style=PALETTE["ok"]))
        table.add_row(t("cleanup.remaining"), str(max(0, total - done)))

        if progress and progress.skipped:
            table.add_row(
                t("cleanup.skipped"), Text(str(progress.skipped), style=PALETTE["warn"])
            )
        if progress and progress.failed:
            table.add_row(
                t("cleanup.failed"), Text(str(progress.failed), style=PALETTE["danger"])
            )

        category = (
            Text.from_markup(category_markup(progress.item.category))
            if progress
            else Text("")
        )
        self.query_one("#cleanup-stats", Static).update(Group(table, Text(""), category))
