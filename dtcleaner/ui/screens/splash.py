"""Splash screen.

Short and skippable on purpose: a tool people run monthly should not make them
watch an animation. Any key dismisses it, and it auto-advances after ~1.6s.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from dtcleaner.i18n import t
from dtcleaner.ui import mascot
from dtcleaner.ui.mascot import Mood
from dtcleaner.ui.screens.base import ChromeScreen


class SplashScreen(ChromeScreen):
    AUTO_ADVANCE = 1.6

    def compose_content(self) -> ComposeResult:
        caps = self.app.caps  # type: ignore[attr-defined]
        with Vertical(id="splash"):
            # Both are mounted; CSS picks one by breakpoint, so a resize swaps
            # them instantly instead of re-composing the screen.
            yield Static(mascot.wordmark(caps.unicode), id="splash-wordmark")
            yield Static(
                mascot.wordmark(caps.unicode, compact=True), id="splash-wordmark-small"
            )
            yield Static(mascot.art(Mood.IDLE, unicode=caps.unicode), id="splash-mascot")
            yield Static(t("app.tagline"), id="splash-tagline")
            yield Static(
                f"{t('app.mascot_name')} - {t('app.mascot_title')}",
                id="splash-byte",
                classes="faint center",
            )

    def on_mount(self) -> None:
        self.set_timer(self.AUTO_ADVANCE, self._advance)

    def on_key(self) -> None:
        self._advance()

    def _advance(self) -> None:
        if self.is_current:
            self.app.switch_to_home()  # type: ignore[attr-defined]
