"""Protected paths manager (LAYER 3).

Adding a path here is the strongest statement a user can make, so the screen
validates before accepting: a path that does not exist is rejected rather than
silently stored, otherwise a typo would create the illusion of protection.
"""

from __future__ import annotations

import os
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen

from dtcleaner.ui.screens.base import ChromeScreen
from textual.widgets import Button, Input, ListItem, ListView, Static

from dtcleaner.i18n import t
from dtcleaner.ui.mascot import Mood
from dtcleaner.ui.theme import PALETTE


class ProtectedScreen(ChromeScreen):
    BINDINGS = [
        Binding("escape", "back", show=False),
        Binding("delete", "remove", show=False),
        Binding("r", "remove", show=False),
    ]

    def compose_content(self) -> ComposeResult:
        with Vertical(classes="content"):
            yield Static(t("protected.subtitle"), classes="dim")
            with Horizontal():
                yield Input(placeholder=r"C:\dev\important-client", id="path-input")
                yield Button(t("protected.add"), variant="primary", id="add")
            yield ListView(id="protected-list")
            yield Static("", id="protected-status", classes="dim")

    def on_mount(self) -> None:
        self.app.set_title(t("protected.title"), Mood.BLOCKED)  # type: ignore[attr-defined]
        self.app.set_keys(  # type: ignore[attr-defined]
            [("ENTER", t("protected.add")), ("R", t("protected.remove")), ("ESC", t("keys.back"))]
        )
        self._reload()

    def _reload(self) -> None:
        view = self.query_one("#protected-list", ListView)
        view.clear()
        paths = self.app.config.protected_paths  # type: ignore[attr-defined]
        if not paths:
            view.append(ListItem(Static(t("protected.empty"), classes="faint")))
            return
        for path in paths:
            view.append(ListItem(Static(path), id=f"p-{abs(hash(path))}", name=path))

    # -- actions ------------------------------------------------------------
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "add":
            self._add()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "path-input":
            self._add()

    def _add(self) -> None:
        field = self.query_one("#path-input", Input)
        raw = field.value.strip().strip('"')
        if not raw:
            return

        if not os.path.isdir(raw):
            self._status(t("protected.invalid"), PALETTE["danger"])
            return

        added = self.app.config.add_protected(raw)  # type: ignore[attr-defined]
        if not added:
            self._status(t("protected.already"), PALETTE["warn"])
            return

        self.app.save_settings()  # type: ignore[attr-defined]
        self.app.reload_safety()  # type: ignore[attr-defined]
        field.value = ""
        self._reload()
        self._status(t("protected.added", path=Path(raw).name), PALETTE["ok"])

    def action_remove(self) -> None:
        view = self.query_one("#protected-list", ListView)
        item = view.highlighted_child
        if item is None or not item.name:
            return
        if self.app.config.remove_protected(item.name):  # type: ignore[attr-defined]
            self.app.save_settings()  # type: ignore[attr-defined]
            self.app.reload_safety()  # type: ignore[attr-defined]
            self._reload()
            self._status(t("protected.removed", path=Path(item.name).name), PALETTE["text_dim"])
        else:
            self._status(t("protected.not_found"), PALETTE["warn"])

    def _status(self, message: str, color: str) -> None:
        self.query_one("#protected-status", Static).update(f"[{color}]{message}[/]")

    def action_back(self) -> None:
        self.app.switch_to_home()  # type: ignore[attr-defined]
