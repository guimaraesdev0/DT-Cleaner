"""Base screen that carries the app chrome.

Why this exists
---------------
The header and status bar were originally composed by `App.compose()`. That
mounts them on the *default* screen, and Textual draws a pushed screen on top of
it -- so the chrome was covered on every screen the user ever saw. The status
bar in particular was being updated by every screen and displayed by none.

Chrome therefore belongs to the screen, not to the app. Subclasses implement
`compose_content()` and get the header, the content region and the status bar
in the right order, docked correctly, on every screen.

Modal screens deliberately do NOT inherit from this: they overlay the screen
below, which already has its own chrome.
"""

from __future__ import annotations

from collections.abc import Iterable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widget import Widget

from dtcleaner.ui.components import AppHeader, StatusBar
from dtcleaner.ui.mascot import Mood


class ChromeScreen(Screen):
    """A screen with the DT-Cleaner header and status bar.

    Also owns arrow-key navigation. Textual moves focus with TAB by default and
    lets the arrows scroll the container instead -- which made the menus feel
    dead, since pressing Down visibly did nothing. Here the arrows move focus,
    and widgets that need the arrows themselves (tables, selects, inputs) keep
    them via `_arrows_belong_to_focused`.
    """

    #: Title shown in the header. Subclasses override, or call `set_chrome()`.
    screen_title: str = ""
    screen_mood: Mood = Mood.IDLE

    BINDINGS = [
        Binding("down", "nav_down", show=False, priority=True),
        Binding("up", "nav_up", show=False, priority=True),
    ]

    def _arrows_belong_to_focused(self) -> bool:
        """True when the focused widget consumes up/down for its own job.

        Note what is NOT here: a *collapsed* `Select` and an `Input`. Both were
        swallowing up/down and trapping the user on one row -- a Select only
        needs the arrows while its overlay is open, and an Input uses left/right
        only.
        """
        from textual.widgets import DataTable, ListView, OptionList, Select, TextArea

        focused = self.focused
        if focused is None:
            return False
        if isinstance(focused, (DataTable, ListView, OptionList, TextArea)):
            return True
        if isinstance(focused, Select):
            return bool(focused.expanded)
        # An open Select renders its overlay as a child widget.
        return any(
            isinstance(ancestor, (Select, OptionList))
            for ancestor in focused.ancestors_with_self
        )

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Disable the arrow bindings when the focused widget owns the arrows.

        This has to happen here, not inside the action. The bindings are
        `priority=True`, so they consume the keypress before the focused widget
        ever sees it -- an action that simply returns early would swallow Down
        and leave a DataTable cursor frozen. Returning False deactivates the
        binding so the key falls through to the widget.
        """
        if action in ("nav_down", "nav_up") and self._arrows_belong_to_focused():
            return False
        return True

    def action_nav_down(self) -> None:
        self.focus_next()

    def action_nav_up(self) -> None:
        self.focus_previous()

    def focus_first_control(self) -> None:
        """Put focus on something usable, so the screen never feels inert."""
        from textual.widgets import (
            Button,
            Checkbox,
            DataTable,
            Input,
            ListView,
            Select,
            Switch,
        )

        for widget in self.query("*"):
            if isinstance(
                widget, (DataTable, ListView, Input, Switch, Select, Checkbox, Button)
            ) and widget.display:
                widget.focus()
                return

    def compose(self) -> ComposeResult:
        yield AppHeader(self.app.caps, self.screen_title)  # type: ignore[attr-defined]
        yield from self.compose_content()
        yield StatusBar()

    def compose_content(self) -> Iterable[Widget]:
        """Everything between the header and the status bar."""
        return ()

    # -- chrome helpers -----------------------------------------------------
    def set_chrome(self, title: str, mood: Mood, keys: list[tuple[str, str]]) -> None:
        """Set the header title, BYTE's mood and the visible key hints at once."""
        self.screen_title = title
        self.screen_mood = mood
        header = self.header
        if header is not None:
            header.title_text = title
            header.set_mood(mood)
        bar = self.status_bar
        if bar is not None:
            bar.set_keys(keys)

    @property
    def header(self) -> AppHeader | None:
        found = self.query(AppHeader)
        return found.first(AppHeader) if found else None

    @property
    def status_bar(self) -> StatusBar | None:
        found = self.query(StatusBar)
        return found.first(StatusBar) if found else None

    def tick_mascot(self, frame: int) -> None:
        header = self.header
        if header is not None:
            header.frame = frame
