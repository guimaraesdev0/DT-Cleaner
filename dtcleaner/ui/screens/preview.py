"""Cleanup preview -- the last screen before anything is deleted.

Safety decisions visible here:

* BYTE switches to WARNING whenever the plan contains anything above LOW risk.
  The mascot never looks happy on a screen that can destroy data.
* Permanent deletion requires typing a confirmation word. Recycle Bin does not,
  because it is undoable. The friction is proportional to the consequence.
* The screen restates what will NOT be touched (removed and protected counts),
  so the user can confirm their exclusions actually took effect.
"""

from __future__ import annotations

from rich.console import Group
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen

from dtcleaner.ui.screens.base import ChromeScreen
from textual.widgets import Button, Input, Static

from dtcleaner.core.cleanup import build_plan
from dtcleaner.core.constants import RISK_ORDER, DeleteMode, RiskLevel
from dtcleaner.core.models import CleanupPlan, ScanSession
from dtcleaner.i18n import t
from dtcleaner.ui.mascot import Mood
from dtcleaner.ui.theme import PALETTE, category_markup, risk_markup
from dtcleaner.utils.formatting import human_bytes
from dtcleaner.utils.paths import display_path


class PreviewScreen(ChromeScreen):
    BINDINGS = [
        Binding("escape", "back", show=False),
        Binding("c", "confirm", show=False),
    ]

    def __init__(self, session: ScanSession, **kwargs) -> None:
        super().__init__(**kwargs)
        self.session = session
        self.plan: CleanupPlan = build_plan(session, self.app_delete_mode())

    def app_delete_mode(self) -> DeleteMode:
        return self.app.config.delete_mode  # type: ignore[attr-defined]

    @property
    def needs_typed_confirmation(self) -> bool:
        return self.plan.delete_mode is DeleteMode.PERMANENT

    def compose_content(self) -> ComposeResult:
        with VerticalScroll(classes="content"):
            yield Static(t("preview.subtitle"), classes="subtitle")
            if self.plan.warnings:
                yield Static(self._warning_text(), id="preview-warning")
            yield Static(self._summary(), classes="panel")
            yield Static(self._top_items(), classes="panel", id="preview-top")
        if self.needs_typed_confirmation:
            yield Input(
                placeholder=t("preview.type_to_confirm", word=t("preview.confirm_word")),
                id="confirm-input",
            )
        with Horizontal(id="modal-buttons"):
            yield Button(t("common.back"), id="back")
            yield Button(
                t("preview.confirm_action"),
                variant="error" if self.needs_typed_confirmation else "primary",
                id="confirm",
            )

    def on_mount(self) -> None:
        risky = any(
            RISK_ORDER.get(item.risk_level, 0) > RISK_ORDER[RiskLevel.LOW]
            for item in self.plan.items
        )
        mood = Mood.WARNING if (risky or self.needs_typed_confirmation) else Mood.THINKING
        self.app.set_title(t("preview.title"), mood)  # type: ignore[attr-defined]
        self.app.set_keys(  # type: ignore[attr-defined]
            [("C", t("preview.confirm_action")), ("ESC", t("common.back"))]
        )

    # -- rendering ----------------------------------------------------------
    def _warning_text(self) -> Text:
        text = Text()
        for index, key in enumerate(self.plan.warnings):
            if index:
                text.append("\n")
            if key == "preview.risk_warning":
                count = sum(
                    1
                    for i in self.plan.items
                    if RISK_ORDER.get(i.risk_level, 0) > RISK_ORDER[RiskLevel.LOW]
                )
                text.append("! " + t(key, count=count))
            else:
                text.append("! " + t(key))
        return text

    def _summary(self) -> Group:
        table = Table.grid(padding=(0, 2))
        table.add_column(style=PALETTE["text_dim"], no_wrap=True)
        table.add_column(style=PALETTE["text"])

        table.add_row(
            t("preview.items_total"), Text(str(self.plan.item_count), style="bold")
        )
        table.add_row(
            t("preview.size_total"),
            Text(human_bytes(self.plan.total_size), style=f"bold {PALETTE['ok']}"),
        )
        mode_key = (
            "preview.mode_permanent"
            if self.plan.delete_mode is DeleteMode.PERMANENT
            else "preview.mode_recycle"
        )
        mode_color = (
            PALETTE["danger"] if self.needs_typed_confirmation else PALETTE["ok"]
        )
        table.add_row(t("preview.delete_mode"), Text(t(mode_key), style=mode_color))

        breakdown = self.plan.risk_breakdown()
        for risk in (RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH):
            if breakdown.get(risk):
                table.add_row(
                    Text.from_markup(risk_markup(risk)), str(breakdown[risk])
                )

        table.add_row(
            t("review.removed_count", count=self.plan.excluded_count).split("(")[0].strip(),
            str(self.plan.excluded_count),
        )
        table.add_row(t("common.protected"), str(self.plan.protected_count))

        categories = Text(
            ", ".join(t(f"category.{c.value}") for c in self.plan.categories()),
            style=PALETTE["text_dim"],
        )
        return Group(
            Text(t("preview.title"), style=f"bold {PALETTE['accent']}"),
            Text(""),
            table,
            Text(""),
            Text(t("preview.affected_categories"), style=PALETTE["text_dim"]),
            categories,
        )

    def _top_items(self) -> Group:
        table = Table.grid(padding=(0, 2))
        table.add_column(style=PALETTE["text"], no_wrap=True)
        table.add_column(style=PALETTE["text_dim"])
        table.add_column(style=PALETTE["ok"], justify="right")

        biggest = sorted(self.plan.items, key=lambda i: -i.size_bytes)[:8]
        for item in biggest:
            table.add_row(
                display_path(item.path, 54),
                Text.from_markup(category_markup(item.category)),
                human_bytes(item.size_bytes),
            )
        return Group(
            Text(t("results.top_biggest"), style=f"bold {PALETTE['accent']}"),
            Text(""),
            table,
        )

    # -- actions ------------------------------------------------------------
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.action_back()
        else:
            self.action_confirm()

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_confirm(self) -> None:
        if self.needs_typed_confirmation:
            typed = self.query_one("#confirm-input", Input).value.strip()
            if typed.casefold() != t("preview.confirm_word").casefold():
                self.app.notify_warning(  # type: ignore[attr-defined]
                    t("preview.type_to_confirm", word=t("preview.confirm_word"))
                )
                self.query_one("#confirm-input", Input).focus()
                return
        self.app.start_cleanup(self.plan)  # type: ignore[attr-defined]
