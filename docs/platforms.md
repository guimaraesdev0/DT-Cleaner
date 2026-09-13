# Platform support

| Platform | Status | What that means |
|---|---|---|
| **Windows 10 / 11** | ✅ **Supported** | Every safety rule is implemented and covered by tests that run on Windows. This is the platform DT-Cleaner is built and verified on. |
| **Linux** | 🧪 **Experimental** | Runs, and the POSIX denylist is implemented, but the path rules have not been exercised on a real Linux host. |
| **macOS** | 🧪 **Experimental** | Same as Linux. The macOS-specific roots (`/System`, `/Library`, `/Applications`, `/private`) are declared but untested in practice. |

`dtc doctor` reports the level for the machine it is running on. On an
experimental platform it prints a warning rather than an OK — a tool that
deletes things should say when it is on less-tested ground.

## What is already cross-platform

These parts have no Windows assumptions and should behave identically anywhere:

- **All six detectors** — Node, Python, Rust, .NET, JVM, Android/Expo. They match
  directory names and project markers, nothing OS-specific.
- **Project context validation and confidence scoring** — pure path arithmetic.
- **The scanner** — `os.scandir` based, with symlink detection via
  `stat.S_ISLNK` on POSIX and reparse-point attributes on Windows.
- **Trash support** — `send2trash` implements the XDG trash spec on Linux and
  Finder's trash on macOS.
- **The whole UI** — Textual is cross-platform.
- **Config, logging and history** — `~/.dt-cleaner/` on every platform.

## What was Windows-only, and was fixed

Layer 1 of the safety model resolves system directories from environment
variables (`%SystemRoot%`, `%ProgramFiles%`, …). **None of those exist on
POSIX**, so on Linux and macOS Layer 1 used to resolve to an empty list.

In practice a scan would rarely have targeted a system path anyway — a
candidate still needs a matching detector and proven project context — but the
structural guarantee the product is built on simply was not there.

`POSIX_SYSTEM_ROOTS` and `POSIX_SYSTEM_DIR_NAMES` in `core/constants.py` now
cover it:

```
/bin  /boot  /dev  /etc  /lib  /lib32  /lib64  /proc  /run
/sbin /srv   /sys  /usr  /var  /snap
/Applications  /Library  /System  /Volumes  /private  /cores  /opt/homebrew
```

Plus the hidden home directories POSIX users expect to keep: `.local`,
`.cache`, `.gnupg`, `.password-store`, `.mozilla`, `.thunderbird`, `~/Library`.

`tests/test_platform_support.py` checks this list as **data**, so those tests
run on Windows too and the list cannot silently rot. The live path checks are
skipped off-POSIX and are what still needs a real Linux/macOS run.

## What still needs work before POSIX is "supported"

1. **Run the suite on Linux and macOS.** `tests/test_safety_denylist.py` and
   `tests/test_paths_windows.py` are Windows-only today; they need POSIX
   equivalents covering case sensitivity (`/Users` vs `/users` behave
   differently from Windows), symlink handling, and permission errors.
2. **Case sensitivity.** `canonical()` casefolds on Windows and does not on
   POSIX — correct, but the denylists were written for a casefolded world and
   deserve explicit tests on a case-sensitive filesystem.
3. **Mount point enumeration.** `disk_service` returns just `/` off Windows. A
   real implementation would read `/proc/mounts` (Linux) or `diskutil` (macOS)
   so Full Scan does not wander into network shares or `/mnt`.
4. **Trash verification.** `send2trash` is believed to work; nobody has watched
   it actually move a folder to the XDG trash from this app.
5. **Quick Scan defaults.** `~/dev`, `~/projects`, `~/code` already work;
   `/srv/dev`, `/opt/dev`, `/workspace` are guesses that want real-world input.
6. **Packaging.** No distro packages, no Homebrew formula. `pipx install` only.

## Helping

Running the test suite on Linux or macOS and opening an issue with the output is
the single most useful contribution right now — especially any test that fails,
and especially anything under `tests/test_platform_support.py`.

```bash
git clone https://github.com/guimaraesdev0/DT-Cleaner.git
cd DT-Cleaner
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
dtc doctor
```

Please do **not** run a cleanup on a machine you care about until the platform
is marked supported. Use `python scripts/make_sandbox.py` and point a Custom
Scan at the throwaway folder it creates.
