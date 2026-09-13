"""The Textual application: navigation, workers and shared state.

Threading model
---------------
Scanning and cleanup are blocking, filesystem-bound work, so both run in
Textual worker threads (`thread=True`). They touch the UI only through
`call_from_thread`, which is the single supported way to cross that boundary.
Progress is already rate-limited upstream by `Throttle`, so the UI thread never
drowns in updates.

The app object owns the long-lived services (config, safety engine, logger,
history) and every screen reaches them through it. That keeps a single
SafetyEngine instance in play -- important, because reloading protected paths
must affect every subsequent decision immediately.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from textual.app import App
from textual.binding import Binding
from textual.widgets import Static

from dtcleaner.core.cleanup import CleanupEngine, CleanupProgress
from dtcleaner.core.config import AppConfig, ConfigStore, get_config, get_store, save_config
from dtcleaner.core.constants import APP_NAME, APP_VERSION, ScanMode
from dtcleaner.core.logging_service import SessionLogger
from dtcleaner.core.models import CleanupPlan, CleanupResult, ScanItem, ScanSession
from dtcleaner.core.safety import SafetyEngine
from dtcleaner.core.scanner import Progress, Scanner, resolve_roots
from dtcleaner.i18n import t
from dtcleaner.services.history_service import HistoryService
from dtcleaner.ui.mascot import Mood
from dtcleaner.ui.screens.base import ChromeScreen
from dtcleaner.ui.screens.cleanup import CleanupScreen
from dtcleaner.ui.screens.details import DetailsScreen
from dtcleaner.ui.screens.help import HelpScreen
from dtcleaner.ui.screens.history import HistoryScreen
from dtcleaner.ui.screens.home import HomeScreen
from dtcleaner.ui.screens.preview import PreviewScreen
from dtcleaner.ui.screens.protected import ProtectedScreen
from dtcleaner.ui.screens.results import ResultsScreen
from dtcleaner.ui.screens.scan_mode import CustomScanScreen
from dtcleaner.ui.screens.scan_progress import ScanProgressScreen
from dtcleaner.ui.screens.settings import SettingsScreen
from dtcleaner.ui.screens.splash import SplashScreen
from dtcleaner.ui.screens.summary import SummaryScreen
from dtcleaner.ui.theme import detect_capabilities


class DTCleanerApp(App):
    CSS_PATH = "dtcleaner.tcss"
    TITLE = APP_NAME

    # Textual stamps these classes on the Screen and keeps them current while
    # the terminal is resized, so the stylesheet can restructure the layout
    # without any manual resize handling. Written narrow-first: an unexpected
    # size falls back to the stacked layout rather than to a broken one.
    HORIZONTAL_BREAKPOINTS = [(0, "-compact"), (90, "-normal"), (130, "-wide")]
    VERTICAL_BREAKPOINTS = [(0, "-short"), (28, "-tall")]

    BINDINGS = [
        Binding("ctrl+c", "quit", show=False),
        Binding("ctrl+q", "quit", show=False),
    ]

    def __init__(self, skip_splash: bool = False) -> None:
        super().__init__()
        self.store: ConfigStore = get_store()
        self.config: AppConfig = get_config()
        self.caps = detect_capabilities(self.config.ascii_fallback)
        self.safety = SafetyEngine(user_protected=list(self.config.protected_paths))
        self.logger = SessionLogger(self.store, self.config)
        self.history = HistoryService(self.store.history_path)

        self.session: ScanSession | None = None
        self._scanner: Scanner | None = None
        self._cleanup_engine: CleanupEngine | None = None
        self._skip_splash = skip_splash

    # -- chrome -------------------------------------------------------------
    # The app composes NO chrome. Header and status bar belong to each screen
    # (see ui/screens/base.ChromeScreen): widgets mounted on the default screen
    # are covered by any pushed screen, so app-level chrome was invisible.

    def on_mount(self) -> None:
        self.logger.info(f"{APP_NAME} {APP_VERSION} started")
        if self._skip_splash:
            self.switch_to_home()
        else:
            self.push_screen(SplashScreen())

    def set_title(self, title: str, mood: Mood = Mood.IDLE) -> None:
        screen = self.screen
        if isinstance(screen, ChromeScreen):
            screen.set_chrome(title, mood, screen.status_bar._pairs if screen.status_bar else [])

    def tick_header(self, frame: int) -> None:
        screen = self.screen
        if isinstance(screen, ChromeScreen):
            screen.tick_mascot(frame)

    def set_keys(self, pairs: list[tuple[str, str]]) -> None:
        screen = self.screen
        if isinstance(screen, ChromeScreen):
            bar = screen.status_bar
            if bar is not None:
                bar.set_keys(pairs)

    def notify_info(self, message: str) -> None:
        self.notify(message, severity="information", timeout=3)

    def notify_warning(self, message: str) -> None:
        self.notify(message, severity="warning", timeout=5)

    def notify_error(self, message: str) -> None:
        self.notify(message, severity="error", timeout=8)

    # -- navigation ---------------------------------------------------------
    def switch_to_home(self) -> None:
        self._reset_screens()
        self.push_screen(HomeScreen())

    def _reset_screens(self) -> None:
        """Return to a single-screen stack. Screens hold scan state, so stale
        ones must not linger behind the home screen."""
        while len(self.screen_stack) > 1:
            self.pop_screen()

    def open_custom_scan(self) -> None:
        self.push_screen(CustomScanScreen())

    def open_protected(self) -> None:
        self.push_screen(ProtectedScreen())

    def open_settings(self) -> None:
        self.push_screen(SettingsScreen())

    def reload_settings_screen(self) -> None:
        """Re-create Settings so a language change is visible immediately."""
        self.pop_screen()
        self.push_screen(SettingsScreen())

    def open_history(self) -> None:
        self.push_screen(HistoryScreen())

    def open_help(self) -> None:
        self.push_screen(HelpScreen())

    def open_details(self, item: ScanItem) -> None:
        self.push_screen(DetailsScreen(item))

    def open_preview(self, session: ScanSession) -> None:
        self.push_screen(PreviewScreen(session))

    # -- settings -----------------------------------------------------------
    def save_settings(self) -> None:
        save_config(self.config)
        self.caps = detect_capabilities(self.config.ascii_fallback)
        self.reload_safety()

    def reload_safety(self) -> None:
        """Push the current protected list into the live SafetyEngine."""
        self.safety.reload_protected(list(self.config.protected_paths))

    def protect_path(self, path: str) -> bool:
        added = self.config.add_protected(path)
        if added:
            save_config(self.config)
            self.reload_safety()
            self.logger.info("protected.added", path=path)
        return added

    # -- scanning -----------------------------------------------------------
    def start_scan(self, mode: ScanMode, custom_roots: list[str] | None = None) -> None:
        roots = resolve_roots(self.config, mode, custom_roots)
        if not roots:
            self.notify_warning(t("scan.no_roots"))
            return

        self._reset_screens()
        progress_screen = ScanProgressScreen()
        self.push_screen(progress_screen)
        self.logger.scan_started(mode.value, roots)
        self._run_scan(roots, mode, progress_screen)

    def cancel_scan(self) -> None:
        if self._scanner is not None:
            self._scanner.cancel()
            self.notify_warning(t("scan.cancelled"))

    def _run_scan(
        self, roots: list[str], mode: ScanMode, screen: ScanProgressScreen
    ) -> None:
        def on_progress(progress: Progress) -> None:
            # Called from the worker thread; hop back to the UI thread.
            try:
                self.call_from_thread(screen.update_progress, progress)
            except Exception:  # noqa: BLE001 - screen may already be gone
                pass

        scanner = Scanner(
            config=self.config, safety=self.safety, on_progress=on_progress
        )
        self._scanner = scanner

        def work() -> ScanSession:
            return scanner.scan(roots, mode)

        self.run_worker(
            lambda: self._scan_worker(work), thread=True, exclusive=True, name="scan"
        )

    def _scan_worker(self, work) -> None:
        try:
            session = work()
        except Exception as exc:  # noqa: BLE001 - a scan crash must not kill the app
            self.call_from_thread(self._scan_failed, str(exc))
            return
        self.call_from_thread(self._scan_finished, session)

    def _scan_finished(self, session: ScanSession) -> None:
        self.session = session
        self._scanner = None
        self.logger.scan_finished(
            session.items_found,
            session.total_recoverable_bytes,
            session.duration_seconds or 0.0,
            len(session.errors),
        )
        self.history.record_scan(session)

        self._reset_screens()
        self.push_screen(ResultsScreen(session))
        if session.cancelled:
            self.notify_warning(t("scan.cancelled"))

    def _scan_failed(self, message: str) -> None:
        self._scanner = None
        self.logger.error("scan.failed", error=message)
        self.notify_error(f"{t('error.unexpected')}: {message}")
        self.switch_to_home()

    # -- cleanup ------------------------------------------------------------
    def start_cleanup(self, plan: CleanupPlan) -> None:
        self._reset_screens()
        screen = CleanupScreen(plan)
        self.push_screen(screen)
        self.logger.cleanup_started(
            plan.item_count, plan.total_size, plan.delete_mode.value
        )

        def on_progress(progress: CleanupProgress) -> None:
            try:
                self.call_from_thread(screen.update_progress, progress)
            except Exception:  # noqa: BLE001
                pass

        engine = CleanupEngine(
            safety=self.safety,
            on_progress=on_progress,
            on_log=self.logger.cleanup_event,
        )
        self._cleanup_engine = engine

        started = datetime.now()

        def work() -> CleanupResult:
            result = engine.execute(plan)
            result.log_path = str(self.logger.text_path)
            return result

        self.run_worker(
            lambda: self._cleanup_worker(work, started, plan),
            thread=True,
            exclusive=True,
            name="cleanup",
        )

    def _cleanup_worker(self, work, started: datetime, plan: CleanupPlan) -> None:
        try:
            result = work()
        except Exception as exc:  # noqa: BLE001
            self.call_from_thread(self._cleanup_failed, str(exc))
            return
        self.call_from_thread(self._cleanup_finished, result, plan)

    def _cleanup_finished(self, result: CleanupResult, plan: CleanupPlan) -> None:
        self._cleanup_engine = None
        self.logger.cleanup_finished(
            len(result.deleted_items),
            len(result.failed_items),
            result.recovered_bytes,
            result.duration_seconds or 0.0,
        )
        self.history.record_cleanup(result)

        # Deleted items must not linger in the session: a second pass would
        # offer paths that no longer exist.
        if self.session is not None:
            deleted = {o.item_id for o in result.deleted_items}
            self.session.items = [i for i in self.session.items if i.id not in deleted]

        self._reset_screens()
        self.push_screen(SummaryScreen(result, protected_count=plan.protected_count))

    def _cleanup_failed(self, message: str) -> None:
        self._cleanup_engine = None
        self.logger.error("cleanup.failed", error=message)
        self.notify_error(f"{t('error.unexpected')}: {message}")
        self.switch_to_home()

    # -- shutdown -----------------------------------------------------------
    def on_unmount(self) -> None:
        try:
            self.logger.close()
        except Exception:  # noqa: BLE001
            pass


def run(skip_splash: bool = False) -> None:
    DTCleanerApp(skip_splash=skip_splash).run()
