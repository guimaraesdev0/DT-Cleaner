"""Scan progress screen.

The scan runs in a Textual worker thread; this screen only receives throttled
progress ticks and turns them into motion.

What moves, and why each one earns its frames:

* a **spinner** on the active phase -- proof the process is alive during a long
  discovery pass, when no counter may change for seconds at a time
* a **sweep bar** -- a scan head running left to right while the total is still
  unknown; it becomes a real progress bar the moment sizing starts and a total
  exists
* a **live feed of finds** -- each artifact appears as it is discovered and
  fades as newer ones arrive. This is the dramatic part, and also the most
  informative: the user sees what the app is actually finding, not an abstract
  number
* the **mascot** in the header, eyes glancing side to side

All of it is gated on `settings.animations`. With animations off the screen
still updates; it just does not tick on a timer.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from rich.console import Group
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import ProgressBar, Static

from dtcleaner.core.scanner import Phase, Progress
from dtcleaner.i18n import t
from dtcleaner.ui.components import MascotLine
from dtcleaner.ui.mascot import Mood
from dtcleaner.ui.screens.base import ChromeScreen
from dtcleaner.ui.theme import PALETTE, category_markup
from dtcleaner.utils.paths import display_path

PHASE_ORDER: tuple[Phase, ...] = (
    Phase.DISCOVERY,
    Phase.CLASSIFICATION,
    Phase.VALIDATION,
    Phase.SIZING,
    Phase.CATEGORIZATION,
    Phase.FINALIZING,
)

SPINNER_UNICODE = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
SPINNER_ASCII = "|/-\\"

#: How many recent finds stay on screen. Six is enough to feel like a stream
#: without turning into a log the user has to read.
FEED_SIZE = 6


@dataclass(frozen=True, slots=True)
class Find:
    name: str
    category: str
    project: str


class PhaseList(Static):
    """Checklist of scan phases, with a spinner on the active one."""

    def __init__(self, unicode: bool, **kwargs) -> None:
        super().__init__(id="phase-list", **kwargs)
        self.unicode = unicode
        self.current = Phase.DISCOVERY
        self.frame = 0

    def set_phase(self, phase: Phase) -> None:
        if phase is not self.current:
            self.current = phase
            self.refresh()

    def tick(self, frame: int) -> None:
        self.frame = frame
        self.refresh()

    def render(self) -> Text:
        done_mark = "✔" if self.unicode else "x"
        pending_mark = "·" if self.unicode else "-"
        spinner = SPINNER_UNICODE if self.unicode else SPINNER_ASCII
        active_mark = spinner[self.frame % len(spinner)]
        current_index = PHASE_ORDER.index(self.current)

        text = Text(no_wrap=True, overflow="ellipsis")
        for index, phase in enumerate(PHASE_ORDER):
            if index < current_index:
                text.append(f" {done_mark} {t(phase.value)}\n", style=PALETTE["ok"])
            elif index == current_index:
                text.append(
                    f" {active_mark} {t(phase.value)}\n", style=f"bold {PALETTE['accent']}"
                )
            else:
                text.append(f" {pending_mark} {t(phase.value)}\n", style=PALETTE["text_faint"])
        return text


class SweepBar(Static):
    """Indeterminate progress: a scan head sweeping across the track.

    Used while the total is unknown. A static bar there would either sit at zero
    (looks frozen) or fake a percentage (lies about progress).
    """

    HEAD = 6

    def __init__(self, unicode: bool, **kwargs) -> None:
        super().__init__(id="sweep-bar", **kwargs)
        self.unicode = unicode
        self.frame = 0

    def tick(self, frame: int) -> None:
        self.frame = frame
        self.refresh()

    def render(self) -> Text:
        width = max(10, self.size.width)
        track = "░" if self.unicode else "."
        body = "▓" if self.unicode else "="
        head = "█" if self.unicode else "#"

        # Ping-pong so the head reverses at the edges instead of jumping back.
        span = max(1, width - self.HEAD)
        position = self.frame % (span * 2)
        if position > span:
            position = span * 2 - position

        cells = [track] * width
        for offset in range(self.HEAD):
            index = position + offset
            if 0 <= index < width:
                cells[index] = head if offset >= self.HEAD - 2 else body

        text = Text(no_wrap=True)
        for index, cell in enumerate(cells):
            lit = position <= index < position + self.HEAD
            text.append(cell, style=PALETTE["accent"] if lit else PALETTE["border"])
        return text


class FindFeed(Static):
    """The last few artifacts found, newest first, fading with age."""

    #: Newest to oldest. The tail dims so the eye tracks what just arrived.
    FADE = (PALETTE["ok"], PALETTE["text"], PALETTE["text_dim"], PALETTE["text_faint"])

    def __init__(self, **kwargs) -> None:
        super().__init__(id="find-feed", **kwargs)
        self.finds: deque[Find] = deque(maxlen=FEED_SIZE)

    def add(self, find: Find) -> None:
        self.finds.appendleft(find)
        self.refresh()

    def render(self) -> Group:
        title = Text(t("scan.recent_finds"), style=f"bold {PALETTE['accent']}", no_wrap=True)
        if not self.finds:
            return Group(
                title, Text(f"  {t('common.loading')}...", style=PALETTE["text_faint"])
            )

        table = Table.grid(padding=(0, 2))
        table.add_column(no_wrap=True, overflow="ellipsis")
        table.add_column(no_wrap=True, overflow="ellipsis")
        table.add_column(style=PALETTE["text_faint"], no_wrap=True, overflow="ellipsis")

        for index, find in enumerate(self.finds):
            color = self.FADE[min(index, len(self.FADE) - 1)]
            row = Text("+ ", style=PALETTE["ok"] if index == 0 else PALETTE["text_faint"])
            row.append(find.name, style=color)
            table.add_row(
                row,
                Text.from_markup(_category_label(find.category, index)),
                find.project,
            )
        return Group(title, table)


def _category_label(category_value: str, index: int) -> str:
    """Category label, dimmed for older entries in the feed."""
    from dtcleaner.core.constants import Category

    try:
        category = Category(category_value)
    except ValueError:
        return category_value
    if index == 0:
        return category_markup(category)
    return f"[{PALETTE['text_faint']}]{t(f'category.{category.value}')}[/]"


class ScanProgressScreen(ChromeScreen):
    BINDINGS = [Binding("escape", "cancel", show=False)]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._frame = 0
        self._determinate = False

    def compose_content(self) -> ComposeResult:
        caps = self.app.caps  # type: ignore[attr-defined]
        with Vertical(classes="content"):
            yield MascotLine(Mood.SCANNING, id="scan-mascot")
            yield PhaseList(caps.unicode)
            yield SweepBar(caps.unicode)
            yield ProgressBar(total=100, show_eta=False, id="scan-bar", classes="-hidden")
            yield Static("", id="scan-path")
            yield Static("", id="scan-stats")
            yield FindFeed()

    def on_mount(self) -> None:
        self.app.set_title(t("scan.starting"), Mood.SCANNING)  # type: ignore[attr-defined]
        self.app.set_keys([("ESC", t("scan.cancel_hint"))])  # type: ignore[attr-defined]
        self._render_stats(0, 0)
        if self.app.config.animations:  # type: ignore[attr-defined]
            # ~12 fps: fast enough to read as motion, slow enough that the UI
            # thread stays out of the scanner's way.
            self.set_interval(0.08, self._tick_frame)

    def _tick_frame(self) -> None:
        self._frame += 1
        self.query_one(PhaseList).tick(self._frame)
        if not self._determinate:
            self.query_one(SweepBar).tick(self._frame)
        self.query_one("#scan-mascot", MascotLine).frame = self._frame
        self.app.tick_header(self._frame)  # type: ignore[attr-defined]

    # -- called from the worker thread via call_from_thread -----------------
    def update_progress(self, progress: Progress) -> None:
        if progress.is_find:
            self.query_one(FindFeed).add(
                Find(progress.found_name, progress.found_category, progress.found_project)
            )

        self.query_one(PhaseList).set_phase(progress.phase)
        self._switch_bar(progress)

        if progress.current_path:
            path = display_path(progress.current_path, max(20, self.size.width - 14))
            self.query_one("#scan-path", Static).update(
                Text(
                    f"{t('scan.current_path')}: {path}",
                    style=PALETTE["text_dim"],
                    no_wrap=True,
                    overflow="ellipsis",
                )
            )

        self._render_stats(progress.dirs_visited, progress.candidates, progress)

    def _switch_bar(self, progress: Progress) -> None:
        """Sweep while the total is unknown; real progress once it is not."""
        determinate = bool(progress.total)
        if determinate != self._determinate:
            self._determinate = determinate
            self.query_one(SweepBar).set_class(determinate, "-hidden")
            self.query_one("#scan-bar", ProgressBar).set_class(not determinate, "-hidden")

        if determinate:
            self.query_one("#scan-bar", ProgressBar).update(
                total=progress.total, progress=progress.done
            )

    def _render_stats(self, dirs: int, found: int, progress: Progress | None = None) -> None:
        text = Text(no_wrap=True, overflow="ellipsis")
        text.append(f"{t('scan.dirs_visited')} ", style=PALETTE["text_dim"])
        text.append(f"{dirs:,}", style=PALETTE["text"])
        text.append("    ")
        text.append(f"{t('scan.candidates_found')} ", style=PALETTE["text_dim"])
        text.append(f"{found:,}", style=f"bold {PALETTE['ok']}")
        if progress is not None and progress.total:
            text.append("    ")
            text.append(f"{progress.done}/{progress.total}", style=PALETTE["accent"])
        self.query_one("#scan-stats", Static).update(text)

    def action_cancel(self) -> None:
        self.app.cancel_scan()  # type: ignore[attr-defined]
