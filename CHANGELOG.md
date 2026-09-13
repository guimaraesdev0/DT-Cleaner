# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-09-13

First public release.

### Added

- **Safety Engine** with five protection layers: system paths, sensitive files,
  user-protected paths, project context validation, and explicit confirmation.
  Full contract in `docs/safety.md`.
- **Six detectors** — Node/frontend, Python, Rust, .NET, JVM, Android/Expo —
  with confidence scoring and per-ecosystem project markers.
- **Interactive TUI** built on Textual: splash, home, scan progress with a live
  feed of finds, results dashboard, item details, cleanup preview, progress and
  summary, plus protected paths, settings, history and help.
- **Responsive layout** with breakpoints at 90 and 130 columns, verified at six
  terminal sizes by `tests/test_ui_layout.py`.
- **BYTE**, the watchdog mascot, with alignment invariants under test.
- **Internationalisation** — English and Brazilian Portuguese, switchable at
  runtime. Block reasons are stored as keys plus parameters, so a scanned item
  renders in either language without re-scanning.
- **CLI** — `scan`, `protected add/remove/list`, `history`, `settings` and
  `doctor`. `dtc scan` never deletes, by design and without an override.
- **Recycle Bin / trash by default**, with permanent deletion behind a typed
  confirmation.
- **Logging and history** — a human-readable log, a JSONL audit log, and a
  SQLite history of scans and cleanups.
- **POSIX denylist** (`/usr`, `/etc`, `/System`, …) so Layer 1 is not empty on
  Linux and macOS. See `docs/platforms.md` for the support status.
- **Sandbox and screenshot generators** under `scripts/`, so the README images
  come from the running app using synthetic data.

### Known limitations

- Linux and macOS are **experimental**: the POSIX rules are implemented but have
  not been exercised on a real host. `dtc doctor` reports this.
- `disk_service` returns only `/` off Windows; Full Scan does not yet enumerate
  real mount points on POSIX.
- No distro packages or Homebrew formula.

[0.1.0]: https://github.com/guimaraesdev0/DT-Cleaner/releases/tag/v0.1.0
