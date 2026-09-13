# Contributing to DT-Cleaner

Thanks for considering it. This is a tool that deletes files, so the bar for
changes is a little higher than usual — but the rules are simple and the test
suite does most of the enforcing.

## The one rule

> **A change that lets DT-Cleaner delete something it previously refused to
> delete needs a test proving the new case is safe.**

Everything else is negotiable. That is not.

If your change only makes the app *more* conservative, or touches the UI, docs,
i18n or tooling, this does not apply — just make sure the suite still passes.

## Getting set up

```bash
git clone https://github.com/guimaraesdev0/DT-Cleaner.git
cd DT-Cleaner

python -m venv .venv
source .venv/bin/activate          # Windows: .\.venv\Scripts\Activate.ps1

pip install -e ".[dev]"
pytest -q
dtc doctor
```

Never test a cleanup against real work. Use the sandbox:

```bash
python scripts/make_sandbox.py     # builds a fake project tree with traps
```

It prints a path. Point a Custom Scan at it, and delete the folder when you are
done.

## Read this first

If you are touching anything under `core/`, read
**[`docs/safety.md`](docs/safety.md)**. It is normative: it describes guarantees
the product makes, and the tests exist to enforce them. Changing a denylist
without reading it is how a safety net acquires a hole.

## The most useful contributions right now

1. **Run the test suite on Linux or macOS** and open an issue with the output —
   see [`docs/platforms.md`](docs/platforms.md). This is the single biggest gap.
2. **New ecosystem detectors** — Go, Elixir, Zig, Haskell, Flutter, Unity.
   [`docs/detectors.md`](docs/detectors.md) walks through it; it is about 30
   lines plus a test.
3. **New languages** — one JSON file in `dtcleaner/i18n/locales/`.
4. **False positives you hit in the wild.** If DT-Cleaner offered you something
   it should not have, that is the most valuable bug report there is. Include
   the path shape, not the path.

## Adding a detector

Short version — full version in [`docs/detectors.md`](docs/detectors.md):

1. Create `dtcleaner/core/detectors/<ecosystem>.py` with a `RuleDetector`.
2. Register the module in `_load_builtin()` in `detectors/base.py`.
3. Add the project markers to `PROJECT_MARKERS` in `core/constants.py`.
4. **Add a false-positive test** to `tests/test_false_positives.py` proving your
   ambiguous names are refused without project context.

A detector without that last test does not get merged.

## Adding a language

1. Copy `dtcleaner/i18n/locales/en.json` to `<code>.json`.
2. Translate the values. Leave the keys and `{placeholders}` alone.
3. Add the code and its native-language label to `AVAILABLE_LANGUAGES` in
   `dtcleaner/i18n/__init__.py`.

`test_every_key_exists_in_every_locale` fails if you miss a key, so you will
know.

## Code style

- **English** for all code, comments, docstrings and identifiers. User-facing
  text goes through `i18n`, never hardcoded.
- Line length 100. `ruff check dtcleaner tests` should be clean.
- Type hints on public functions.
- Comments explain *why*, not *what*. A comment that restates the code is noise;
  one that records a decision or a trap is what keeps this codebase safe.

## Tests

```bash
pytest -q                          # everything
pytest tests/test_safety_denylist.py -v
pytest -q -k "false_positive"
```

The suite is organised by what it protects:

| File | Guards |
|---|---|
| `test_safety_denylist.py` | Layer 1 and 2 — system paths, sensitive files |
| `test_platform_support.py` | POSIX denylist parity |
| `test_protected_paths.py` | Layer 3 — the user's own list |
| `test_false_positives.py` | The heart of it: names without context |
| `test_cleanup_plan.py` | The final gate, including TOCTOU cases |
| `test_detectors.py` | Detection rules and context resolution |
| `test_scanner_and_sizer.py` | Walk behavior, junctions, cancellation, i18n |
| `test_ui_layout.py` | Responsive layout at six terminal sizes |
| `test_ui_smoke.py` | Screens compose, mount and respond |
| `test_mascot.py` | Mascot alignment invariants |
| `test_paths_windows.py` | Windows path semantics |

## Pull requests

- One topic per PR.
- Describe what changed and, if it touches safety, what test proves it is safe.
- Screenshots for UI changes are appreciated — regenerate them with
  `python scripts/make_screenshots.py` if you changed anything visible in the
  README images.
- CI runs the suite on Windows, Linux and macOS across Python 3.11–3.13.
  Linux and macOS failures are expected today and are useful data, not a
  blocker for unrelated work.

## Reporting a security issue

If you find a way to make DT-Cleaner delete something it should refuse to
delete, please open an issue describing the *class* of problem and the path
shape involved. Do not include real paths from a machine you care about.

## Code of conduct

Be decent. Assume good faith. Disagree about the code, not the person.
