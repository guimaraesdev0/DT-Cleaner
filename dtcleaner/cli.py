"""Command line interface.

The TUI is the product; this CLI exists for the cases a TUI handles badly:
scripting, quick lookups, and diagnosing a broken terminal.

One safety rule governs the whole CLI: `dtc scan` NEVER deletes. It reports
what it found and stops. Deletion only ever happens through the interactive
review and confirmation flow, so there is no flag anyone can add to a scheduled
task that silently wipes folders.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from dtcleaner.core.config import get_config, get_store, save_config
from dtcleaner.core.constants import (
    APP_NAME,
    APP_VERSION,
    PLATFORM_SUPPORT,
    RiskLevel,
    ScanMode,
)
from dtcleaner.core.safety import SafetyEngine
from dtcleaner.core.scanner import Scanner, resolve_roots
from dtcleaner.i18n import AVAILABLE_LANGUAGES, set_language, t
from dtcleaner.services.disk_service import list_disks
from dtcleaner.services.history_service import HistoryService
from dtcleaner.services.recycle_bin_service import SEND2TRASH_AVAILABLE
from dtcleaner.ui.theme import PALETTE, detect_capabilities
from dtcleaner.utils import paths as P
from dtcleaner.utils.formatting import human_bytes, human_duration

app = typer.Typer(
    name="dtc",
    help=f"{APP_NAME} - reclaim dev disk space, safely.",
    no_args_is_help=False,
    add_completion=False,
)
protected_app = typer.Typer(help=t("cli.protected_help"))
app.add_typer(protected_app, name="protected")

console = Console()


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-v", help="Show version and exit."),
    language: str | None = typer.Option(
        None, "--lang", help=f"Interface language ({', '.join(AVAILABLE_LANGUAGES)})."
    ),
) -> None:
    """Launch the interactive app when no subcommand is given."""
    config = get_config()
    set_language(language or config.language)

    if version:
        console.print(f"{APP_NAME} {APP_VERSION}")
        raise typer.Exit()

    if ctx.invoked_subcommand is None:
        from dtcleaner.ui.app import run

        run()


@app.command("scan")
def scan_command(
    quick: bool = typer.Option(False, "--quick", help="Scan the usual project folders."),
    full: bool = typer.Option(False, "--full", help="Scan every fixed drive."),
    path: list[str] = typer.Option(None, "--path", "-p", help="Scan a specific folder."),
    limit: int = typer.Option(25, "--limit", help="How many rows to print."),
) -> None:
    """Scan and REPORT. This command never deletes anything."""
    config = get_config()
    set_language(config.language)

    if path:
        mode, roots = ScanMode.CUSTOM, list(path)
    elif full:
        mode, roots = ScanMode.FULL, None
    else:
        mode, roots = ScanMode.QUICK, None

    resolved = resolve_roots(config, mode, roots)
    if not resolved:
        console.print(f"[{PALETTE['warn']}]{t('scan.no_roots')}[/]")
        raise typer.Exit(code=1)

    safety = SafetyEngine(user_protected=list(config.protected_paths))
    scanner = Scanner(config=config, safety=safety)

    with console.status(f"[{PALETTE['accent']}]{t('scan.starting')}...", spinner="dots"):
        session = scanner.scan(resolved, mode)

    table = Table(title=t("results.title"), title_style=f"bold {PALETTE['accent']}")
    table.add_column(t("common.category"), style=PALETTE["info"])
    table.add_column(t("common.path"))
    table.add_column(t("common.size"), justify="right", style=PALETTE["ok"])
    table.add_column(t("common.risk"))
    table.add_column(t("common.confidence"), justify="right")

    for item in session.top_items(limit):
        table.add_row(
            t(f"category.{item.category.value}"),
            P.display_path(item.path, 54),
            human_bytes(item.size_bytes),
            _risk_cell(item.risk_level),
            f"{item.confidence:.0%}",
        )

    console.print(table)
    console.print(
        f"\n{t('results.recoverable')}: "
        f"[{PALETTE['ok']} bold]{human_bytes(session.total_recoverable_bytes)}[/]   "
        f"{t('common.items')}: {session.items_found}   "
        f"{t('results.projects')}: {session.project_count}   "
        f"{t('results.duration')}: {human_duration(session.duration_seconds)}"
    )
    if session.errors:
        console.print(f"[{PALETTE['warn']}]{t('results.errors')}: {len(session.errors)}[/]")
    console.print(
        f"\n[{PALETTE['text_dim']}]Nothing was deleted. Run [bold]dtc[/bold] "
        f"for the interactive review and cleanup.[/]"
    )

    HistoryService(get_store().history_path).record_scan(session)


@protected_app.command("list")
def protected_list() -> None:
    """List protected paths."""
    config = get_config()
    set_language(config.language)
    if not config.protected_paths:
        console.print(f"[{PALETTE['text_dim']}]{t('protected.empty')}[/]")
        return
    for entry in config.protected_paths:
        console.print(f"  {entry}")


@protected_app.command("add")
def protected_add(target: str = typer.Argument(..., help="Folder to protect.")) -> None:
    """Protect a folder from every future scan."""
    config = get_config()
    set_language(config.language)

    if not os.path.isdir(target):
        console.print(f"[{PALETTE['danger']}]{t('protected.invalid')}[/]")
        raise typer.Exit(code=1)

    if not config.add_protected(target):
        console.print(f"[{PALETTE['warn']}]{t('protected.already')}[/]")
        return

    save_config(config)
    console.print(f"[{PALETTE['ok']}]{t('protected.added', path=target)}[/]")


@protected_app.command("remove")
def protected_remove(target: str = typer.Argument(..., help="Folder to unprotect.")) -> None:
    """Remove a folder from the protected list."""
    config = get_config()
    set_language(config.language)

    if not config.remove_protected(target):
        console.print(f"[{PALETTE['warn']}]{t('protected.not_found')}[/]")
        raise typer.Exit(code=1)

    save_config(config)
    console.print(f"[{PALETTE['text_dim']}]{t('protected.removed', path=target)}[/]")


@app.command("history")
def history_command(limit: int = typer.Option(10, "--limit")) -> None:
    """Show recent scans and cleanups."""
    config = get_config()
    set_language(config.language)
    history = HistoryService(get_store().history_path)

    cleanups = history.recent_cleanups(limit)
    scans = history.recent_scans(limit)
    if not cleanups and not scans:
        console.print(f"[{PALETTE['text_dim']}]{t('history.empty')}[/]")
        return

    if cleanups:
        table = Table(title=t("history.cleanups"))
        table.add_column(t("common.modified"))
        table.add_column(t("summary.space_recovered"), justify="right", style=PALETTE["ok"])
        table.add_column(t("summary.items_deleted"), justify="right")
        table.add_column(t("summary.items_failed"), justify="right")
        for entry in cleanups:
            table.add_row(
                entry.timestamp.strftime("%Y-%m-%d %H:%M"),
                human_bytes(entry.recovered_bytes),
                str(entry.deleted_items),
                str(entry.failed_items),
            )
        console.print(table)

    if scans:
        table = Table(title=t("history.scans"))
        table.add_column(t("common.modified"))
        table.add_column(t("scan.mode_title"))
        table.add_column(t("common.items"), justify="right")
        table.add_column(t("results.recoverable"), justify="right")
        for entry in scans:
            table.add_row(
                entry.timestamp.strftime("%Y-%m-%d %H:%M"),
                entry.scan_mode or "--",
                str(entry.items_found),
                human_bytes(entry.recoverable_bytes),
            )
        console.print(table)

    console.print(
        f"\n{t('history.total_recovered')}: "
        f"[{PALETTE['ok']} bold]{human_bytes(history.total_recovered_bytes())}[/]"
    )


@app.command("settings")
def settings_command(
    language: str | None = typer.Option(None, "--lang", help="Set the interface language."),
    safe_mode: bool | None = typer.Option(None, "--safe-mode/--no-safe-mode"),
) -> None:
    """Show or change settings."""
    config = get_config()
    changed = False

    if language is not None:
        if language not in AVAILABLE_LANGUAGES:
            console.print(f"[{PALETTE['danger']}]Unknown language: {language}[/]")
            raise typer.Exit(code=1)
        config.language = language
        changed = True
    if safe_mode is not None:
        config.safe_mode = safe_mode
        changed = True

    if changed:
        save_config(config)
    set_language(config.language)

    table = Table(title=t("settings.title"))
    table.add_column(t("common.name"), style=PALETTE["text_dim"])
    table.add_column(t("common.total"))
    table.add_row(t("settings.language"), AVAILABLE_LANGUAGES[config.language])
    table.add_row(t("settings.safe_mode"), _on_off(config.safe_mode))
    table.add_row(t("settings.delete_mode"), config.delete_mode.value)
    table.add_row(t("settings.show_protected"), _on_off(config.show_protected_items))
    table.add_row(t("settings.animations"), _on_off(config.animations))
    table.add_row(t("settings.log_level"), config.log_level)
    table.add_row(t("common.protected"), str(len(config.protected_paths)))
    console.print(table)
    console.print(f"[{PALETTE['text_dim']}]{get_store().config_path}[/]")


@app.command("doctor")
def doctor_command() -> None:
    """Check permissions, terminal support and configuration."""
    config = get_config()
    set_language(config.language)
    caps = detect_capabilities(config.ascii_fallback)
    store = get_store()

    checks: list[tuple[str, bool | None, str]] = []

    checks.append(("Python", sys.version_info >= (3, 11), sys.version.split()[0]))
    support = PLATFORM_SUPPORT.get(sys.platform)
    # True = supported, None = experimental (warns), False = untested (fails).
    checks.append((
        "Platform",
        True if support == "supported" else (None if support else False),
        f"{sys.platform} ({support or 'untested'})",
    ))
    checks.append(("Unicode output", caps.unicode, str(sys.stdout.encoding)))
    checks.append(("Truecolor", caps.truecolor or None, os.environ.get("COLORTERM", "-")))
    checks.append(("Terminal width", caps.width >= 80, f"{caps.width} cols"))
    checks.append(
        ("Recycle Bin support", SEND2TRASH_AVAILABLE, "send2trash"
         if SEND2TRASH_AVAILABLE else "missing: pip install send2trash")
    )

    # Config directory must be writable, otherwise settings and protected paths
    # silently fail to persist -- which would be a safety problem.
    writable = _check_writable(store.base_dir)
    checks.append(("Config directory", writable, str(store.base_dir)))
    checks.append(("Log directory", _check_writable(store.log_dir), str(store.log_dir)))

    disks = list_disks()
    checks.append(("Fixed drives", bool(disks), ", ".join(d.mountpoint for d in disks) or "-"))

    roots = config.resolved_quick_paths()
    checks.append(
        ("Quick Scan roots", bool(roots), f"{len(roots)} found" if roots else "none detected")
    )

    # Long path support: without it, deep node_modules trees fail to delete.
    checks.append(("Long path handling", _check_long_paths(), r"\\?\ prefix"))

    table = Table(title=t("cli.doctor_running"))
    table.add_column("")
    table.add_column(t("common.name"))
    table.add_column(t("common.reason"), style=PALETTE["text_dim"])

    exit_code = 0
    for name, ok, detail in checks:
        if ok is True:
            status = f"[{PALETTE['ok']}]{t('cli.doctor_ok')}[/]"
        elif ok is None:
            status = f"[{PALETTE['warn']}]{t('cli.doctor_warn')}[/]"
        else:
            status = f"[{PALETTE['danger']}]{t('cli.doctor_fail')}[/]"
            exit_code = 1
        table.add_row(status, name, detail)

    console.print(table)
    if exit_code:
        console.print(f"[{PALETTE['warn']}]Some checks failed. See the details above.[/]")
    raise typer.Exit(code=exit_code)


def _check_writable(directory: Path) -> bool:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".dtc-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def _check_long_paths() -> bool:
    """Verify the long-path prefix actually works on this system."""
    try:
        deep = Path(get_store().base_dir) / ("l" * 40) / ("o" * 40) / ("n" * 40) / ("g" * 40)
        os.makedirs(P.with_long_prefix(deep), exist_ok=True)
        ok = P.inspect(deep).is_dir
        # Clean up the probe tree, deepest first.
        current = deep
        for _ in range(4):
            try:
                os.rmdir(P.with_long_prefix(current))
            except OSError:
                break
            current = current.parent
        return ok
    except OSError:
        return False


def _risk_cell(risk: RiskLevel) -> str:
    colors = {
        RiskLevel.LOW: PALETTE["ok"],
        RiskLevel.MEDIUM: PALETTE["warn"],
        RiskLevel.HIGH: PALETTE["danger"],
        RiskLevel.UNKNOWN: PALETTE["text_dim"],
        RiskLevel.PROTECTED: PALETTE["info"],
    }
    return f"[{colors[risk]}]{t(f'risk.{risk.value}')}[/]"


def _on_off(value: bool) -> str:
    return t("common.enabled") if value else t("common.disabled")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
