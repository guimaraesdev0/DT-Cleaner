"""Reusable widgets shared across screens.

Layout principle for everything here: a widget must survive being squeezed.
Panels report their content as a Rich grid with `no_wrap` only where truncation
is safer than reflow, and nothing assumes a minimum terminal width -- the
breakpoint classes in `dtcleaner.tcss` handle the structural changes, and these
widgets handle the content changes.
"""

from __future__ import annotations

from rich.console import Group
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widgets import Static

from dtcleaner.core.models import DiskInfo
from dtcleaner.i18n import t
from dtcleaner.ui import mascot
from dtcleaner.ui.mascot import Mood
from dtcleaner.ui.theme import PALETTE, Capabilities
from dtcleaner.utils.formatting import bar, human_bytes, percent


class AppHeader(Static):
    """Top bar: wordmark, screen title and BYTE's face.

    The face is the app's constant companion. It is the ONLY place the mascot
    appears on most screens, which keeps the personality present without
    spending rows that the data needs.
    """

    mood: reactive[Mood] = reactive(Mood.IDLE)
    frame: reactive[int] = reactive(0)
    title_text: reactive[str] = reactive("")

    def __init__(self, caps: Capabilities, title: str = "", **kwargs) -> None:
        super().__init__(id="app-header", **kwargs)
        self.caps = caps
        self.title_text = title

    def render(self) -> Text:
        text = Text(no_wrap=True, overflow="ellipsis")
        text.append(mascot.chip(self.mood, frame=self.frame), style=PALETTE["accent"])
        text.append("  DT-Cleaner", style=f"bold {PALETTE['accent']}")
        if self.title_text:
            text.append("  ·  ", style=PALETTE["text_faint"])
            text.append(self.title_text, style=PALETTE["text"])
        return text

    def set_mood(self, mood: Mood) -> None:
        self.mood = mood
        self.frame = 0


class StatusBar(Static):
    """Bottom bar listing the keys live on the current screen.

    Secondary hints are dropped from the right when they do not fit, rather
    than wrapping onto a second row -- the bar is docked at height 1 and a wrap
    would push content off screen.

    The `primary` hint is different: it is the action that moves the user
    forward, it renders first, in the accent colour, and it is NEVER dropped.
    That rule exists because it was broken: the results screen listed eight
    hints with "C  Confirm cleanup" second from the end, so the key that starts
    a cleanup was truncated away at every terminal width and users could not
    find it.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(id="status-bar", **kwargs)
        self._pairs: list[tuple[str, str]] = []
        self._primary: tuple[str, str] | None = None

    def set_keys(
        self, pairs: list[tuple[str, str]], primary: tuple[str, str] | None = None
    ) -> None:
        self._pairs = pairs
        self._primary = primary
        self.refresh()

    def render(self) -> Text:
        width = max(20, self.size.width - 2)
        text = Text(no_wrap=True, overflow="ellipsis")
        used = 0

        if self._primary is not None:
            key, label = self._primary
            text.append(f" {key} ", style=f"bold {PALETTE['bg']} on {PALETTE['ok']}")
            text.append(f" {label}", style=f"bold {PALETTE['ok']}")
            used = len(key) + len(label) + 5

        for key, label in self._pairs:
            chunk = len(key) + len(label) + 5
            if used + chunk > width:
                break
            if used:
                text.append("   ")
                used += 3
            text.append(f" {key} ", style=f"bold {PALETTE['bg']} on {PALETTE['accent']}")
            text.append(f" {label}", style=PALETTE["text_dim"])
            used += chunk
        return text


class MascotLine(Static):
    """BYTE's dialogue as a single row.

    Carries the words only -- the face lives in the header, and the mascot rule
    is one BYTE per screen. Deliberately not the 5-line art either: large art
    only earns its space on the splash screen, and anywhere else it pushed the
    actual content off a short terminal.
    """

    frame: reactive[int] = reactive(0)

    def __init__(self, mood: Mood = Mood.IDLE, **kwargs) -> None:
        super().__init__(classes="mascot-line", **kwargs)
        self.mood = mood

    def render(self) -> Text:
        return Text(
            mascot.line(self.mood),
            style=PALETTE["text_dim"],
            no_wrap=True,
            overflow="ellipsis",
        )

    def set_mood(self, mood: Mood) -> None:
        self.mood = mood
        self.frame = 0
        self.refresh()


class EmptyState(Vertical):
    """Shared empty state: BYTE's face, a title and one explanatory line."""

    def __init__(self, caps: Capabilities, title: str, body: str, **kwargs) -> None:
        super().__init__(classes="empty-state", **kwargs)
        self.caps = caps
        self._title = title
        self._body = body

    def compose(self) -> ComposeResult:
        yield Static(mascot.art(Mood.EMPTY), classes="mascot")
        yield Static(self._title, classes="title")
        yield Static(self._body, classes="body")


class DiskPanel(Static):
    """SYSTEM panel: capacity, usage and a gauge per scanned volume."""

    def __init__(self, disks: list[DiskInfo], caps: Capabilities, **kwargs) -> None:
        super().__init__(classes="panel", **kwargs)
        self.disks = disks
        self.caps = caps

    def render(self) -> Group:
        title = Text(t("results.system"), style=f"bold {PALETTE['accent']}", no_wrap=True)
        table = Table.grid(padding=(0, 1))
        table.add_column(style=PALETTE["text_dim"], no_wrap=True)
        table.add_column(style=PALETTE["text"], justify="right", no_wrap=True)

        if not self.disks:
            table.add_row(t("common.unknown"), "--")
            return Group(title, table)

        # The gauge scales with the panel so it never gets clipped mid-bar.
        width = max(6, min(18, self.size.width - 8))
        fill = "█" if self.caps.unicode else "#"
        empty = "░" if self.caps.unicode else "."

        for disk in self.disks:
            color = PALETTE["danger"] if disk.used_percent > 90 else PALETTE["ok"]
            table.add_row(t("results.disk"), disk.mountpoint)
            table.add_row(t("results.capacity"), human_bytes(disk.total_bytes))
            table.add_row(t("results.used"), percent(disk.used_bytes, disk.total_bytes))
            table.add_row(t("results.free"), human_bytes(disk.free_bytes))
            table.add_row(
                "", Text(bar(disk.used_bytes, disk.total_bytes, width, fill, empty), style=color)
            )
        return Group(title, table)


class StatPanel(Static):
    """Generic label/value panel.

    Both columns are `no_wrap`: at narrow widths a truncated label is readable,
    while a wrapped one turns a five-row panel into a twelve-row one and pushes
    the table off screen.
    """

    def __init__(self, title: str, rows: list[tuple[str, str]], **kwargs) -> None:
        super().__init__(classes="panel", **kwargs)
        self._title = title
        self._rows = rows

    def update_rows(self, rows: list[tuple[str, str]]) -> None:
        self._rows = rows
        self.refresh()

    def render(self) -> Group:
        title = Text(self._title, style=f"bold {PALETTE['accent']}", no_wrap=True)
        table = Table.grid(padding=(0, 1))
        table.add_column(style=PALETTE["text_dim"], no_wrap=True, overflow="ellipsis")
        table.add_column(style=PALETTE["text"], justify="right", no_wrap=True)
        for label, value in self._rows:
            table.add_row(Text.from_markup(label), Text.from_markup(value))
        return Group(title, table)
