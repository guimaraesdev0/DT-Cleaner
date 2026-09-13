"""Scan results dashboard and selection review.

Dashboard and review live on one screen deliberately. Splitting them would make
the user navigate away from the numbers to act on them, and the decision that
matters ("is this row safe to remove from my list?") needs both at once.

Three distinct actions, three distinct keys, three distinct visual results:

* SPACE  toggles selection for this cleanup only
* R      removes the row from the list entirely (it disappears)
* P      protects the path permanently (persisted; every future scan skips it)

Keeping them separate is a safety property: a user who wants to preserve one
folder forever should not have to remember to re-deselect it next month.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Input, Static

from dtcleaner.core.constants import RISK_ORDER, RiskLevel
from dtcleaner.core.models import ScanItem, ScanSession
from dtcleaner.i18n import t
from dtcleaner.services.disk_service import disks_for_paths
from dtcleaner.ui.components import DiskPanel, EmptyState, StatPanel
from dtcleaner.ui.mascot import Mood
from dtcleaner.ui.screens.base import ChromeScreen
from dtcleaner.ui.theme import (
    PALETTE,
    category_markup,
    confidence_markup,
    risk_markup,
)
from dtcleaner.utils.formatting import human_bytes
from dtcleaner.utils.paths import display_path


class ResultsScreen(ChromeScreen):
    # Auto-focus is pinned to the table. Textual's auto-focus runs AFTER
    # on_mount, and `None` here means "inherit the app default" rather than
    # "off" -- which is how it kept landing on the hidden filter Input, where
    # every single-letter shortcut (C, A, N, D, R, P) was typed as text and did
    # nothing. The Input is also kept `disabled` while hidden, because a
    # disabled widget cannot take focus at all.
    AUTO_FOCUS = "#items"

    BINDINGS = [
        Binding("space", "toggle", show=False),
        Binding("a", "select_all_safe", show=False),
        Binding("n", "deselect_all", show=False),
        Binding("d", "details", show=False),
        Binding("p", "protect", show=False),
        Binding("r", "remove", show=False),
        Binding("c", "confirm", show=False),
        Binding("slash", "filter", show=False),
        Binding("escape", "back", show=False),
    ]

    def __init__(self, session: ScanSession, **kwargs) -> None:
        super().__init__(**kwargs)
        self.session = session
        self._rows: dict[str, ScanItem] = {}
        self._filter = ""
        self._columns: tuple[str, ...] = ()
        self._name_width = 30

    # -- layout -------------------------------------------------------------
    def compose_content(self) -> ComposeResult:
        caps = self.app.caps  # type: ignore[attr-defined]
        if not self.session.visible_items:
            yield EmptyState(caps, t("scan.empty_title"), t("scan.empty_body"))
            return

        with Vertical(classes="content"):
            with Horizontal(id="dashboard"):
                yield DiskPanel(disks_for_paths(self.session.scanned_roots), caps)
                yield StatPanel(t("results.scan_result"), self._result_rows(), id="panel-result")
                yield StatPanel(t("results.categories"), self._category_rows(), id="panel-cats")
            yield Input(
                placeholder=t("keys.filter"),
                id="filter-input",
                classes="-hidden",
                disabled=True,
            )
            yield DataTable(id="items", cursor_type="row", zebra_stripes=True)
            yield Static("", id="selection-summary")

    def on_mount(self) -> None:
        self.app.set_title(t("results.title"), Mood.THINKING)  # type: ignore[attr-defined]
        self.app.set_keys(  # type: ignore[attr-defined]
            [
                ("SPACE", t("keys.toggle")),
                ("D", t("keys.details")),
                ("R", t("keys.remove")),
                ("P", t("keys.protect")),
                ("A", t("keys.select_all_safe")),
                ("N", t("keys.deselect_all")),
                ("ESC", t("keys.back")),
            ],
            primary=("C", t("keys.continue_cleanup")),
        )
        if not self.session.visible_items:
            return

        self._build_columns()
        self._reload_table()
        self.call_after_refresh(self._focus_table)

    def _focus_table(self) -> None:
        self.query_one("#items", DataTable).focus()

    # -- responsive columns -------------------------------------------------
    #: Which columns fit at each width. A DataTable does not shrink its columns
    #: to fit, so a fixed set would overflow and clip the cursor column off
    #: screen on a narrow terminal. Dropping columns keeps what is left legible.
    COLUMN_TIERS: tuple[tuple[int, tuple[str, ...]], ...] = (
        (0, ("sel", "name", "size")),
        (72, ("sel", "name", "size", "risk")),
        (100, ("sel", "cat", "name", "size", "risk", "conf")),
        (132, ("sel", "cat", "name", "size", "risk", "conf", "reason")),
    )

    def _columns_for_width(self, width: int) -> tuple[str, ...]:
        chosen = self.COLUMN_TIERS[0][1]
        for minimum, columns in self.COLUMN_TIERS:
            if width >= minimum:
                chosen = columns
        return chosen

    def _build_columns(self) -> None:
        table = self.query_one("#items", DataTable)
        width = self.size.width or 100
        self._columns = self._columns_for_width(width)

        # The name column absorbs whatever the fixed columns leave behind.
        fixed = sum(
            {"sel": 3, "cat": 20, "size": 11, "risk": 11, "conf": 6, "reason": 28}[c]
            for c in self._columns
            if c != "name"
        )
        # DataTable pads every cell by one column on each side, plus a border.
        padding = 2 * len(self._columns) + 2
        self._name_width = max(16, width - fixed - padding)

        labels = {
            "sel": "",
            "cat": t("common.category"),
            "name": t("common.name"),
            "size": t("common.size"),
            "risk": t("common.risk"),
            # Short label: the column is 6 wide, so "Confidence" would clip.
            "conf": t("common.confidence_short"),
            "reason": t("common.reason"),
        }
        widths = {
            "sel": 3,
            "cat": 20,
            "name": self._name_width,
            "size": 11,
            "risk": 11,
            "conf": 6,
            "reason": 28,
        }
        table.clear(columns=True)
        for key in self._columns:
            table.add_column(labels[key], width=widths[key], key=key)

    def on_resize(self) -> None:
        """Rebuild the table when the width crosses into another tier."""
        new_columns = self._columns_for_width(self.size.width or 100)
        if new_columns != getattr(self, "_columns", None):
            self._build_columns()
            self._reload_table()

    # -- table --------------------------------------------------------------
    def _reload_table(self) -> None:
        if not self._columns:
            return
        table = self.query_one("#items", DataTable)
        cursor = table.cursor_row
        table.clear()
        self._rows.clear()

        for item in self._filtered_items():
            key = table.add_row(*self._row_cells(item), key=item.id)
            self._rows[str(key)] = item

        if cursor and cursor < table.row_count:
            table.move_cursor(row=cursor)
        self._refresh_summary()

    def _filtered_items(self) -> list[ScanItem]:
        items = self.session.visible_items
        if not self._filter:
            return items
        needle = self._filter.casefold()
        return [
            i
            for i in items
            if needle in i.path.casefold() or needle in i.category.value.casefold()
        ]

    def _row_cells(self, item: ScanItem) -> tuple:
        """Build only the cells for the columns currently on screen."""
        caps = self.app.caps  # type: ignore[attr-defined]
        if item.protected:
            mark = Text("⛒" if caps.unicode else "#", style=PALETTE["info"])
        elif not item.is_selectable:
            mark = Text("-", style=PALETTE["text_faint"])
        elif item.selected:
            mark = Text("✔" if caps.unicode else "x", style=PALETTE["ok"])
        else:
            mark = Text(" ", style=PALETTE["text_dim"])

        name_style = PALETTE["text_faint"] if not item.is_selectable else PALETTE["text"]
        available = {
            "sel": mark,
            "cat": _clip(Text.from_markup(category_markup(item.category))),
            "name": Text(
                display_path(item.display_name, max(16, self._name_width - 1)),
                style=name_style,
                no_wrap=True,
                overflow="ellipsis",
            ),
            "size": Text(human_bytes(item.size_bytes), justify="right", no_wrap=True),
            "risk": _clip(Text.from_markup(risk_markup(item.risk_level))),
            "conf": _clip(Text.from_markup(confidence_markup(item.confidence))),
            "reason": Text(
                item.protected_reason_text() or item.reason_text(),
                style=PALETTE["text_dim"],
                no_wrap=True,
                overflow="ellipsis",
            ),
        }
        return tuple(available[key] for key in self._columns)

    def _current_item(self) -> ScanItem | None:
        table = self.query_one("#items", DataTable)
        if table.row_count == 0:
            return None
        try:
            row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
        except Exception:
            return None
        return self._rows.get(str(row_key))

    def _update_row(self, item: ScanItem) -> None:
        table = self.query_one("#items", DataTable)
        try:
            for column, value in zip(self._columns, self._row_cells(item), strict=True):
                table.update_cell(item.id, column, value)
        except Exception:
            self._reload_table()
        self._refresh_summary()

    # -- panels -------------------------------------------------------------
    def _result_rows(self) -> list[tuple[str, str]]:
        session = self.session
        risks = session.risk_counts()
        rows = [
            (t("results.recoverable"), human_bytes(session.total_recoverable_bytes)),
            (t("common.items"), f"{session.items_found:,}"),
            (t("results.projects"), f"{session.project_count:,}"),
            (t("results.duration"), f"{session.duration_seconds or 0:.1f}s"),
        ]
        for risk in (RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.PROTECTED):
            count = risks.get(risk, 0)
            if count:
                rows.append((risk_markup(risk), str(count)))
        if session.errors:
            rows.append((t("results.errors"), str(len(session.errors))))
        return rows

    def _category_rows(self) -> list[tuple[str, str]]:
        grouped = self.session.by_category()
        rows = []
        for category, items in sorted(
            grouped.items(), key=lambda kv: -sum(i.size_bytes for i in kv[1])
        ):
            total = sum(i.size_bytes for i in items)
            rows.append((category_markup(category), f"{human_bytes(total)}  ({len(items)})"))
        return rows[:9]

    def _refresh_summary(self) -> None:
        """Counts, and -- first -- what to press next.

        The call to action leads the line on purpose. It used to trail the
        counts and was the first thing truncated on a narrow terminal, which is
        exactly backwards: a user who cannot see the counts still gets by, a
        user who cannot see how to continue is stuck.
        """
        selected = self.session.selected_items
        removed = [i for i in self.session.items if i.removed_from_list]
        protected = [i for i in self.session.items if i.protected]

        text = Text(no_wrap=True, overflow="ellipsis")
        self._append_call_to_action(text, bool(selected))

        text.append("   ")
        text.append(
            t(
                "review.selected_count",
                count=len(selected),
                size=human_bytes(sum(i.size_bytes for i in selected)),
            ),
            style=PALETTE["text"] if selected else PALETTE["text_dim"],
        )
        if removed:
            text.append("   ")
            text.append(t("review.removed_count", count=len(removed)), style=PALETTE["text_dim"])
        if protected:
            text.append("   ")
            text.append(t("review.protected_count", count=len(protected)), style=PALETTE["info"])

        self.query_one("#selection-summary", Static).update(text)

    def _append_call_to_action(self, text: Text, has_selection: bool) -> None:
        """Render "press [C] to continue" with the key badge in the right spot.

        The sentinel split keeps word order correct in every language -- the key
        sits mid-sentence in English and Portuguese alike, so appending the
        badge at the end produced "press  to continue  C".
        """
        key = "review.press_to_continue" if has_selection else "review.select_to_continue"
        colour = PALETTE["ok"] if has_selection else PALETTE["text_faint"]
        badge = f"bold {PALETTE['bg']} on {PALETTE['ok']}" if has_selection else (
            f"bold {PALETTE['bg']} on {PALETTE['text_faint']}"
        )

        # Private-use codepoint: it cannot occur in a real translation.
        sentinel = "\ue000"
        before, _, after = t(key, key=sentinel).partition(sentinel)
        if before:
            text.append(before, style=colour)
        text.append(" C ", style=badge)
        if after:
            text.append(after, style=colour)

    # -- actions ------------------------------------------------------------
    def action_toggle(self) -> None:
        item = self._current_item()
        if item is None:
            return
        if not item.set_selected(not item.selected):
            reason = item.protected_reason_text() or t(f"risk.{item.risk_level.value}.desc")
            self.app.notify_warning(t("review.not_selectable", reason=reason))  # type: ignore[attr-defined]
            return
        self._update_row(item)

    def action_select_all_safe(self) -> None:
        """'A' selects everything SAFE, never everything. The distinction matters."""
        changed = 0
        for item in self._filtered_items():
            if item.should_autoselect(self.app.config.safe_mode) and not item.selected:  # type: ignore[attr-defined]
                item.set_selected(True)
                changed += 1
        self._reload_table()
        self.app.notify_info(f"{changed} +")  # type: ignore[attr-defined]

    def action_deselect_all(self) -> None:
        for item in self.session.items:
            item.selected = False
        self._reload_table()

    def action_details(self) -> None:
        item = self._current_item()
        if item is not None:
            self.app.open_details(item)  # type: ignore[attr-defined]

    def action_remove(self) -> None:
        item = self._current_item()
        if item is None:
            return
        item.remove_from_list()
        self._reload_table()
        self.app.notify_info(t("review.removed_notice"))  # type: ignore[attr-defined]

    def action_protect(self) -> None:
        item = self._current_item()
        if item is None:
            return
        target = item.project_root or item.path
        self.app.protect_path(target)  # type: ignore[attr-defined]
        # Every item under the newly protected root becomes untouchable at once.
        from dtcleaner.utils import paths as P

        for other in self.session.items:
            if P.is_within(other.path, target):
                other.mark_protected("safety.user_protected", root=target)
        self._reload_table()
        self.app.notify_info(t("review.protected_notice"))  # type: ignore[attr-defined]

    def action_filter(self) -> None:
        field = self.query_one("#filter-input", Input)
        field.disabled = False
        field.remove_class("-hidden")
        field.focus()

    def _close_filter(self) -> None:
        """Hide the field again and hand focus back to the table.

        Leaving it open would keep swallowing the single-letter shortcuts.
        """
        field = self.query_one("#filter-input", Input)
        if not field.value:
            field.add_class("-hidden")
            field.disabled = True
        self.query_one("#items", DataTable).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "filter-input":
            self._filter = event.value
            self._reload_table()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "filter-input":
            self._close_filter()

    def action_confirm(self) -> None:
        if not self.session.selected_items:
            self.app.notify_warning(t("review.nothing_selected"))  # type: ignore[attr-defined]
            return
        self.app.open_preview(self.session)  # type: ignore[attr-defined]

    def action_back(self) -> None:
        # ESC closes the filter first, if it is what is open.
        field = self.query_one("#filter-input", Input)
        if field.has_focus:
            field.value = ""
            self._close_filter()
            return
        self.app.switch_to_home()  # type: ignore[attr-defined]


def _clip(text: Text) -> Text:
    """Rich's `Text.from_markup` takes no layout kwargs, so set them after."""
    text.no_wrap = True
    text.overflow = "ellipsis"
    return text


def sort_key(item: ScanItem) -> tuple[int, int]:
    """Riskiest-looking first within a size ordering, for review screens."""
    return (RISK_ORDER.get(item.risk_level, 9), -item.size_bytes)
