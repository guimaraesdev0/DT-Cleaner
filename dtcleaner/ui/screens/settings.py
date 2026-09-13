"""Settings screen.

Language lives at the top because it is the setting that makes every other
setting readable. Changing it re-renders the whole app immediately -- no
restart -- because all user-facing strings resolve through `t()` at render time
rather than being baked in at construction.

Safety-relevant toggles (Safe Mode, delete mode, confirmations) are grouped
together and default to their safest value; turning one off is always an
explicit act.

Implementation note
-------------------
`SettingRow` takes a *factory*, not a ready-made widget. Constructing a `Select`
outside `compose()` and handing it over crashes on mount: the Select's value
watcher fires before its own internal children exist and the screen dies with
`NoMatches: #label`, which took the whole app down with it. Building the control
inside `compose()` keeps Textual's mount ordering intact.
"""

from __future__ import annotations

from collections.abc import Callable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import Select, Static, Switch

from dtcleaner.core.constants import DeleteMode
from dtcleaner.i18n import AVAILABLE_LANGUAGES, t
from dtcleaner.ui.mascot import Mood
from dtcleaner.ui.screens.base import ChromeScreen


class SettingRow(Horizontal):
    """Label, optional description, and the control that changes the setting."""

    def __init__(
        self, label: str, description: str, control_factory: Callable[[], Widget], **kwargs
    ) -> None:
        super().__init__(classes="setting-row", **kwargs)
        self._label = label
        self._description = description
        self._control_factory = control_factory

    def compose(self) -> ComposeResult:
        with Vertical(classes="setting-label"):
            yield Static(self._label)
            if self._description:
                yield Static(self._description, classes="faint")
        with Horizontal(classes="setting-value"):
            yield self._control_factory()


class SettingsScreen(ChromeScreen):
    BINDINGS = [Binding("escape", "back", show=False)]

    def compose_content(self) -> ComposeResult:
        config = self.app.config  # type: ignore[attr-defined]

        with VerticalScroll(classes="content"):
            yield SettingRow(
                t("settings.language"),
                t("settings.language_desc"),
                lambda: Select(
                    [(label, code) for code, label in AVAILABLE_LANGUAGES.items()],
                    value=config.language,
                    allow_blank=False,
                    id="language",
                ),
            )
            yield SettingRow(
                t("settings.delete_mode"),
                t("settings.delete_mode_desc"),
                lambda: Select(
                    [
                        (t("preview.mode_recycle"), DeleteMode.RECYCLE_BIN.value),
                        (t("preview.mode_permanent"), DeleteMode.PERMANENT.value),
                    ],
                    value=config.delete_mode.value,
                    allow_blank=False,
                    id="delete_mode",
                ),
            )
            yield SettingRow(
                t("settings.safe_mode"),
                t("settings.safe_mode_desc"),
                lambda: Switch(value=config.safe_mode, id="safe_mode"),
            )
            yield SettingRow(
                t("settings.show_protected"),
                t("settings.show_protected_desc"),
                lambda: Switch(value=config.show_protected_items, id="show_protected_items"),
            )
            yield SettingRow(
                t("settings.confirm_medium"),
                "",
                lambda: Switch(value=config.confirm_medium_risk, id="confirm_medium_risk"),
            )
            yield SettingRow(
                t("settings.confirm_high"),
                "",
                lambda: Switch(value=config.confirm_high_risk, id="confirm_high_risk"),
            )
            yield SettingRow(
                t("settings.animations"),
                "",
                lambda: Switch(value=config.animations, id="animations"),
            )
            yield SettingRow(
                t("settings.ascii_fallback"),
                t("settings.ascii_fallback_desc"),
                lambda: Switch(value=config.ascii_fallback, id="ascii_fallback"),
            )
            yield SettingRow(
                t("settings.log_level"),
                "",
                lambda: Select(
                    [(level, level) for level in ("DEBUG", "INFO", "WARNING", "ERROR")],
                    value=config.log_level,
                    allow_blank=False,
                    id="log_level",
                ),
            )

    def on_mount(self) -> None:
        self.app.set_title(t("settings.title"), Mood.IDLE)  # type: ignore[attr-defined]
        self.app.set_keys(  # type: ignore[attr-defined]
            [
                ("UP/DOWN", t("keys.navigate")),
                ("SPACE", t("keys.toggle")),
                ("ESC", t("keys.back")),
            ]
        )
        # After refresh, not during mount: the controls do not exist yet here.
        self.call_after_refresh(self.focus_first_control)

    # -- persistence --------------------------------------------------------
    def on_switch_changed(self, event: Switch.Changed) -> None:
        field = event.switch.id
        if field:
            setattr(self.app.config, field, event.value)  # type: ignore[attr-defined]
            self.app.save_settings()  # type: ignore[attr-defined]

    def on_select_changed(self, event: Select.Changed) -> None:
        field = event.select.id
        if field is None or event.value is Select.BLANK:
            return
        config = self.app.config  # type: ignore[attr-defined]

        if field == "delete_mode":
            config.delete_mode = DeleteMode(str(event.value))
        elif field == "language":
            # Select also fires Changed while mounting; ignore the no-op or the
            # screen would rebuild itself in a loop.
            if str(event.value) == config.language:
                return
            config.language = str(event.value)
            self.app.save_settings()  # type: ignore[attr-defined]
            # Rebuild the screen so every visible label picks up the new language.
            self.app.reload_settings_screen()  # type: ignore[attr-defined]
            return
        else:
            setattr(config, field, str(event.value))

        self.app.save_settings()  # type: ignore[attr-defined]

    def action_back(self) -> None:
        self.app.switch_to_home()  # type: ignore[attr-defined]
