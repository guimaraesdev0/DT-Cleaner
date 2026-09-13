# The Safety Contract

This document is normative. Any change that weakens a rule here is a breaking
change to the product, and the tests in `tests/test_safety_denylist.py`,
`tests/test_false_positives.py` and `tests/test_cleanup_plan.py` exist to
enforce it.

## The one rule

> **A folder is never deleted because of its name.**

`build`, `dist`, `bin`, `obj`, `out`, `target` and `coverage` are ordinary words
that appear in countless projects that have nothing to do with compilers. A name
match makes something a *candidate*, never a target.

## The pipeline

Every path travels this route, in this order. No stage can be skipped, and no
stage can raise the verdict of a previous one.

```
Walker ──▶ Detector ──▶ Candidate
                            │
                  ContextValidator      finds the nearest project marker
                            │
                   ConfidenceScorer     0.0 – 1.0
                            │
                     RiskClassifier     LOW / MEDIUM / HIGH
                            │
              ┏━━━━━━━━━━━━━━━━━━━━━━┓
              ┃    SAFETY ENGINE     ┃  veto only — can lower, never raise
              ┗━━━━━━━━━━━━━━━━━━━━━━┛
                            │
                        ScanItem ──▶ user review (select / remove / protect)
                            │
                       CleanupPlan
                            │
              ┏━━━━━━━━━━━━━━━━━━━━━━┓
              ┃  FINAL GATE (again)  ┃  re-derived from disk, per item
              ┗━━━━━━━━━━━━━━━━━━━━━━┛
                            │
                     CleanupEngine ──▶ Recycle Bin | permanent
```

## The five protection layers

### Layer 1 — system paths

Blocked outright, along with everything inside them:

- every volume root (`C:\`, `D:\`, ...)
- `%SystemRoot%`, `%ProgramFiles%`, `%ProgramFiles(x86)%`, `%ProgramData%`,
  `%PUBLIC%` and the other paths in `FORBIDDEN_ENV_VARS`
- `$Recycle.Bin`, `System Volume Information`, `Recovery`, `PerfLogs`, `Boot`,
  `EFI`, `Config.Msi`
- any user profile root (`C:\Users\<anyone>`)
- first-level profile folders (`Desktop`, `Documents`, `Downloads`, `AppData`,
  `OneDrive`, `.ssh`, `.aws`, ...)
- `AppData\Roaming` and `AppData\LocalLow`

System paths come from **environment variables**, not hardcoded strings, so
Windows installed on another drive or in another language is still covered.

Additionally, `MIN_DELETE_DEPTH = 2`: nothing less than two levels below a
volume root is ever deletable. `C:\node_modules` is refused by construction.

### Layer 2 — sensitive files

A folder containing any of these at its first level becomes PROTECTED, no matter
how convincing the detection was:

`.env` and `.env.*`, lockfiles, `package.json`, `Cargo.toml`, `pyproject.toml`,
`local.properties`, `google-services.json`, `*.jks`, `*.keystore`, `*.pem`,
`*.key`, `*.pfx`, SQLite databases, SSH keys, `*.sln` / `*.csproj`.

Directory names that are never targets: `.git`, `.hg`, `.svn`, `src`, `lib`,
`app`, `assets`, `public`, `static`, `docs`, `tests`, `config`, `secrets`.

### Layer 3 — user protected paths

Anything the user registers in Protected Paths (`P` in the review screen, the
Protected Paths manager, or `dtc protected add`). Persisted in
`%USERPROFILE%\.dt-cleaner\config.json`.

Containment is checked **component by component**, never with a string prefix:
`C:\dev-old` is not inside `C:\dev`.

### Layer 4 — project context

An ambiguous name must have a proven project marker within
`MAX_AMBIGUOUS_MARKER_DISTANCE` (4) levels above it. Unambiguous, tool-owned
names (`node_modules`, `__pycache__`, `.next`) may exist without one but are
capped at `UNAMBIGUOUS_NO_PROJECT_CAP` (0.65) confidence, which is below the
auto-selection threshold.

Anything below `MIN_CONFIDENCE_DELETABLE` (0.60) becomes UNKNOWN and is not
selectable at all.

### Layer 5 — explicit confirmation

Nothing is ever deleted automatically. The user selects, reviews a preview, and
confirms. Permanent deletion additionally requires typing a confirmation word.

## Path canonicalization

Every comparison runs on the canonical form:

- `os.path.realpath` resolves `..`, `.` and 8.3 short names, so
  `C:\dev\..\Windows\System32` and `C:\PROGRA~1` are matched correctly
- the `\\?\` long-path prefix is stripped for comparison and re-added for I/O
- casefolded on Windows
- a bare drive letter (`C:`) is read as the **drive root**, not as that drive's
  current working directory (which is what the OS would do, and which would be
  dangerous here)

## Reparse points

Junctions, symlinks and cloud placeholders are detected via
`FILE_ATTRIBUTE_REPARSE_POINT` and:

- are never traversed by the scanner (a junction to `C:\` would otherwise turn a
  folder scan into a full-disk scan, or loop forever)
- are never counted by the sizer
- are never deleted (removing a junction can wipe its target)

If the attribute cannot be read, the entry is treated as a link. Fail-closed.

## The final gate (TOCTOU)

Between the scan and the confirmation, the world can change: the user checks out
a branch, moves a folder, or a junction gets swapped. So immediately before each
deletion, `SafetyEngine.final_gate()` re-derives everything from disk and refuses
when:

| Condition | Result |
|---|---|
| risk is UNKNOWN or PROTECTED | skipped |
| path no longer exists | skipped |
| target is no longer a directory | skipped |
| folder name changed since the scan | skipped |
| ambiguous item left its project, or the project is gone | skipped |
| a sensitive file appeared inside | skipped |
| any Layer 1–3 rule now matches | skipped |

A skipped item is reported, never fatal. One bad item never aborts a run.

## Fail-closed by default

| Situation | Outcome |
|---|---|
| corrupted `config.json` | safest defaults (safe mode on, Recycle Bin, confirmations on) |
| unreadable directory during validation | no markers found → no proof → UNKNOWN |
| unreadable reparse attribute | treated as a link → not traversed, not deleted |
| detector declares no risk | UNKNOWN, not LOW |
| confidence below threshold | UNKNOWN |
| any exception in classification | PROTECTED |

## Deletion backends

Recycle Bin is the default and **never silently falls back** to permanent
deletion. If the Recycle Bin operation fails, the item is reported as failed —
upgrading a recoverable delete to an irreversible one would break the promise
the preview screen made to the user.

Permanent deletion clears the read-only attribute and retries once (npm and pip
both leave read-only files on Windows) and operates through the `\\?\` prefix so
deep dependency trees do not fail at MAX_PATH.

## Single deletion entry point

`CleanupEngine.execute()` accepts a `CleanupPlan` and nothing else. There is no
"delete this path" function anywhere in the codebase. No screen, CLI command, or
future feature can bypass selection and confirmation.

`dtc scan` from the command line **never deletes**. There is no flag to make it
delete. This is deliberate: nobody should be able to put an unattended cleanup
into a scheduled task.
