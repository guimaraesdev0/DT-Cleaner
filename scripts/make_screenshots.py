"""Render the screenshots used in README.md into docs/images/.

Runs the real app headlessly and exports Textual's own SVG screenshots, so the
images in the README are what the app actually renders -- no mockups, no
hand-editing.

    python scripts/make_screenshots.py

Everything on screen comes from `scripts/demo_data.py`: invented projects,
invented disk, invented history. The screenshots must never expose the machine
that rendered them, and they come out identical on any contributor's laptop.

SVG rather than PNG on purpose: crisp at any zoom, text stays selectable, and
GitHub renders it inline in a README.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Isolate the run BEFORE importing anything that reads configuration, so the
# screenshots never pick up the developer's own settings, protected paths or
# scan history.
_SHOT_HOME = Path(tempfile.mkdtemp(prefix="dtc-shots-home-"))
os.environ["DTC_HOME"] = str(_SHOT_HOME)

from demo_data import (
    DEMO_DISKS,
    DEMO_HISTORY,
    build_cleanup_result,
    build_session,
)

from dtcleaner.core.config import get_config, get_store, save_config
from dtcleaner.core.scanner import Phase, Progress
from dtcleaner.ui.app import DTCleanerApp
from dtcleaner.ui.screens import results as results_screen
from dtcleaner.ui.screens.preview import PreviewScreen
from dtcleaner.ui.screens.results import ResultsScreen
from dtcleaner.ui.screens.scan_progress import ScanProgressScreen
from dtcleaner.ui.screens.summary import SummaryScreen

OUT = REPO_ROOT / "docs" / "images"

#: 132 columns puts the app just past its `-wide` breakpoint (130), so the
#: screenshots show the full three-panel dashboard and the Home side panel
#: rather than the stacked narrow layout.
SIZE = (132, 32)

#: Staged finds for the scan screen. A real scan finishes in milliseconds, far
#: too fast to catch the live feed mid-flight.
DEMO_FINDS = [
    ("node_modules", "Node Modules", "mobile-wallet"),
    ("target", "Rust Target", "payments-api"),
    ("__pycache__", "Python Cache", "ml-pipeline"),
    ("build", "Android Builds", "android-wallet"),
    (".next", "Frontend Build Output", "acme-dashboard"),
    (".gradle", "Gradle Cache", "legacy-portal"),
]

DEMO_SCAN_PATHS = [
    r"D:\dev\mobile-wallet\src\features\checkout",
    r"D:\work\payments-api\crates\ledger\src",
    r"D:\dev\ml-pipeline\pipelines\ingest",
    r"D:\work\android-wallet\android\app\src\main",
    r"D:\dev\acme-dashboard\app\reports\weekly",
    r"D:\dev\legacy-portal\modules\billing",
]


def save(app, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.svg").write_text(app.export_screenshot(), encoding="utf-8")
    print(f"  {name}.svg")


async def paint(pilot, frames: int = 4) -> None:
    """Let the screen actually render before capturing it.

    `push_screen` makes a screen current before its first paint, so capturing
    immediately yields a blank 2 KB SVG.
    """
    for _ in range(frames):
        await pilot.pause()


def seed_history() -> None:
    """Give the Home screen a plausible 'total reclaimed' figure."""
    from dtcleaner.services.history_service import HistoryService

    service = HistoryService(get_store().history_path)
    with service._connect() as conn:
        for index, (recovered, deleted, when) in enumerate(DEMO_HISTORY):
            conn.execute(
                """INSERT OR REPLACE INTO cleanups
                   (id, session_id, started_at, finished_at, delete_mode,
                    deleted_items, failed_items, skipped_items,
                    recovered_bytes, duration_seconds, log_path)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    f"demo-{index}",
                    f"demo-session-{index}",
                    when.isoformat(),
                    when.isoformat(),
                    "recycle_bin",
                    deleted,
                    0,
                    0,
                    recovered,
                    73.4,
                    None,
                ),
            )


async def capture_splash_and_home() -> None:
    app = DTCleanerApp(skip_splash=False)
    async with app.run_test(size=SIZE) as pilot:
        await paint(pilot)
        save(app, "01-splash")
        await pilot.press("space")
        await paint(pilot)
        save(app, "02-home")


async def capture_scan() -> None:
    app = DTCleanerApp(skip_splash=True)
    async with app.run_test(size=SIZE) as pilot:
        screen = ScanProgressScreen()
        app.push_screen(screen)
        await paint(pilot)
        for index, ((name, category, project), path) in enumerate(
            zip(DEMO_FINDS, DEMO_SCAN_PATHS, strict=True), start=1
        ):
            screen.update_progress(
                Progress(
                    Phase.DISCOVERY,
                    current_path=path,
                    dirs_visited=30_717 * index,
                    candidates=index + 11,
                    found_name=name,
                    found_category=category,
                    found_project=project,
                )
            )
            screen._tick_frame()
            screen._tick_frame()
            await pilot.pause()
        save(app, "03-scanning")


async def capture_flow() -> None:
    """Results, details, preview and summary, all from the demo session."""
    session = build_session()
    app = DTCleanerApp(skip_splash=True)
    async with app.run_test(size=SIZE) as pilot:
        await paint(pilot)
        app.session = session
        app.push_screen(ResultsScreen(session))
        await paint(pilot, 6)
        save(app, "04-results")

        app.open_details(session.top_items(1)[0])
        await paint(pilot)
        save(app, "05-details")
        await pilot.press("escape")
        await paint(pilot)

        app.push_screen(PreviewScreen(session))
        await paint(pilot, 6)
        save(app, "06-preview")

        app.push_screen(SummaryScreen(build_cleanup_result(session), protected_count=1))
        await paint(pilot, 6)
        save(app, "07-summary")


async def capture_secondary() -> None:
    for name, opener in (("08-help", "open_help"), ("09-settings", "open_settings")):
        app = DTCleanerApp(skip_splash=True)
        async with app.run_test(size=SIZE) as pilot:
            await paint(pilot)
            getattr(app, opener)()
            await paint(pilot, 6)
            save(app, name)


async def main() -> None:
    config = get_config()
    # English: the README is English, and so is the project's source language.
    config.language = "en"
    config.animations = True
    save_config(config)
    seed_history()

    # The dashboard would otherwise report the real drive of whoever runs this.
    results_screen.disks_for_paths = lambda _roots: DEMO_DISKS

    print(f"Rendering screenshots into {OUT}")
    await capture_splash_and_home()
    await capture_scan()
    await capture_secondary()
    await capture_flow()
    print(f"\nDone. Temporary config discarded at {_SHOT_HOME}")


if __name__ == "__main__":
    asyncio.run(main())
