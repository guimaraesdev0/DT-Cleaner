"""Item details modal.

The point of this screen is transparency: it shows exactly WHY DT-Cleaner
believes a folder is disposable -- which markers were found, how far away they
were, what the confidence was, and how to regenerate the contents. A user who
disagrees with the verdict can see the reasoning instead of guessing.
"""

from __future__ import annotations

from rich.console import Group
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from dtcleaner.core.models import ScanItem
from dtcleaner.i18n import t
from dtcleaner.ui.theme import PALETTE, confidence_markup, risk_markup
from dtcleaner.utils.formatting import human_bytes, relative_age


class DetailsScreen(ModalScreen[None]):
    BINDINGS = [
        Binding("escape", "dismiss_modal", show=False),
        Binding("enter", "dismiss_modal", show=False),
    ]

    def __init__(self, item: ScanItem, **kwargs) -> None:
        super().__init__(**kwargs)
        self.item = item

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-box"):
            yield Static(t("details.title"), id="modal-title")
            yield Static(self._body())
            with Horizontal(id="modal-buttons"):
                yield Button(t("common.close"), variant="primary", id="close")

    def _body(self) -> Group:
        item = self.item
        table = Table.grid(padding=(0, 2))
        table.add_column(style=PALETTE["text_dim"], no_wrap=True)
        table.add_column(style=PALETTE["text"])

        table.add_row(t("common.path"), Text(item.path, style=PALETTE["accent"]))
        table.add_row(t("common.category"), t(f"category.{item.category.value}"))
        table.add_row(t("common.size"), f"{human_bytes(item.size_bytes)}  ({item.file_count:,})")
        table.add_row(t("common.risk"), Text.from_markup(risk_markup(item.risk_level)))
        table.add_row(
            t("common.confidence"), Text.from_markup(confidence_markup(item.confidence))
        )
        table.add_row(t("common.project"), item.project_root or t("common.none"))
        table.add_row(t("common.modified"), relative_age(item.last_modified))

        blocks: list = [table, Text("")]

        blocks.append(Text(t("details.why_detected"), style=f"bold {PALETTE['accent']}"))
        blocks.append(Text(f"  {item.reason_text()}", style=PALETTE["text"]))

        protected_reason = item.protected_reason_text()
        if protected_reason:
            blocks.append(Text(""))
            blocks.append(Text(t("common.protected"), style=f"bold {PALETTE['info']}"))
            blocks.append(Text(f"  {protected_reason}", style=PALETTE["info"]))

        blocks.append(Text(""))
        blocks.append(Text(t("details.markers"), style=f"bold {PALETTE['accent']}"))
        if item.markers_found:
            blocks.append(
                Text("  " + ", ".join(item.markers_found), style=PALETTE["ok"])
            )
        else:
            blocks.append(Text(f"  {t('details.no_markers')}", style=PALETTE["text_dim"]))

        if item.regenerate_hint:
            blocks.append(Text(""))
            blocks.append(Text(t("details.regenerate"), style=f"bold {PALETTE['accent']}"))
            blocks.append(Text(f"  {item.regenerate_hint}", style=PALETTE["text"]))

        blocks.append(Text(""))
        blocks.append(
            Text(t(f"risk.{item.risk_level.value}.desc"), style=PALETTE["text_dim"])
        )
        return Group(*blocks)

    def on_button_pressed(self) -> None:
        self.dismiss(None)

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)
