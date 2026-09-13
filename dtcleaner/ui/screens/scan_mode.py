"""Custom scan: pick the folders (or drives) to walk.

Drives are listed with their free space so the user can aim at the one that is
actually full, and a folder can be typed directly for the common case of "just
scan C:\\dev".
"""

from __future__ import annotations

import os

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Checkbox, Input, Static

from dtcleaner.core.constants import ScanMode
from dtcleaner.i18n import t
from dtcleaner.services.disk_service import list_disks
from dtcleaner.ui.mascot import Mood
from dtcleaner.ui.screens.base import ChromeScreen
from dtcleaner.ui.theme import PALETTE
from dtcleaner.utils.formatting import human_bytes, percent


class CustomScanScreen(ChromeScreen):
    BINDINGS = [
        Binding("escape", "back", show=False),
        Binding("s", "start", show=False),
    ]

    def compose_content(self) -> ComposeResult:
        with VerticalScroll(classes="content"):
            yield Static(t("scan.select_drives"), classes="panel-title")
            with Vertical(id="drive-list"):
                for disk in list_disks():
                    free = t("results.free").lower()
                    used = t("results.used").lower()
                    label = (
                        f"{disk.mountpoint}   "
                        f"{human_bytes(disk.free_bytes)} {free} / "
                        f"{human_bytes(disk.total_bytes)}   "
                        f"({percent(disk.used_bytes, disk.total_bytes)} {used})"
                    )
                    yield Checkbox(
                        label,
                        value=False,
                        id=f"drive-{disk.device[0]}",
                        name=disk.mountpoint,
                    )

            yield Static(t("scan.select_paths"), classes="panel-title")
            with Horizontal():
                yield Input(placeholder=r"C:\dev", id="path-input")
                yield Button(t("common.next"), id="add-path")
            yield Static("", id="chosen-paths", classes="dim")

        with Horizontal(id="modal-buttons"):
            yield Button(t("common.back"), id="back")
            yield Button(t("keys.start_scan"), variant="primary", id="start")

    def on_mount(self) -> None:
        self.app.set_title(t("home.custom_scan"), Mood.IDLE)  # type: ignore[attr-defined]
        self.app.set_keys(  # type: ignore[attr-defined]
            [("S", t("keys.start_scan")), ("ESC", t("keys.back"))]
        )
        self._paths: list[str] = []

    # -- path list ----------------------------------------------------------
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "add-path":
            self._add_path()
        elif event.button.id == "start":
            self.action_start()
        elif event.button.id == "back":
            self.action_back()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "path-input":
            self._add_path()

    def _add_path(self) -> None:
        field = self.query_one("#path-input", Input)
        raw = field.value.strip().strip('"')
        if not raw:
            return
        if not os.path.isdir(raw):
            self.query_one("#chosen-paths", Static).update(
                f"[{PALETTE['danger']}]{t('protected.invalid')}[/]"
            )
            return
        if raw not in self._paths:
            self._paths.append(raw)
        field.value = ""
        self._render_paths()

    def _render_paths(self) -> None:
        text = "\n".join(f"  {p}" for p in self._paths) or t("scan.no_roots")
        self.query_one("#chosen-paths", Static).update(text)

    def _selected_roots(self) -> list[str]:
        roots = list(self._paths)
        for box in self.query(Checkbox):
            if box.value and box.name:
                roots.append(box.name)
        return roots

    # -- actions ------------------------------------------------------------
    def action_start(self) -> None:
        roots = self._selected_roots()
        if not roots:
            self.app.notify_warning(t("scan.no_roots"))  # type: ignore[attr-defined]
            return
        self.app.start_scan(ScanMode.CUSTOM, roots)  # type: ignore[attr-defined]

    def action_back(self) -> None:
        self.app.switch_to_home()  # type: ignore[attr-defined]
