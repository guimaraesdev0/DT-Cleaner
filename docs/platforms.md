# Platform support

| Platform | Status | What that means |
|---|---|---|
| **Windows 10 / 11** | ✅ **Supported** | Every safety rule is implemented and covered by tests that run on Windows. This is the platform DT-Cleaner is built and verified on. |
| **Linux** | 🧪 **Experimental** | The full test suite passes in CI on Ubuntu across Python 3.11–3.13. Not yet exercised in day-to-day use, and Full Scan still does not enumerate real mount points. |
| **macOS** | 🧪 **Experimental** | The suite passes in CI after the temp carve-out below. The macOS-specific roots (`/System`, `/Library`, `/Applications`, `/private`) are declared but untested against a real cleanup. |

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

## The macOS temp trap

Adding the POSIX roots broke macOS completely, and the reason is worth
recording.

On macOS `/tmp` and `/var` are symlinks into `/private`, so `realpath` turns
every temporary directory into `/private/var/folders/…`. That sits inside two
entries of the list above, so the engine refused **every path under the system
temp directory** — which is exactly where `scripts/make_sandbox.py` builds its
demo tree and where the whole test suite works. Fourteen tests failed on macOS
while Linux and Windows were green.

The fix is `POSIX_TEMP_ROOTS`: scratch space that lives inside a system root but
is not system content, exempted from the system rules only.

```
/tmp  /private/tmp  /var/tmp  /private/var/tmp  /var/folders  /private/var/folders
```

It is deliberately narrow — the directories the OS itself empties, and nothing
else. `/private/etc`, `/private/var/db`, `/private/var/root` and `/var/log` are
**not** exempt and stay blocked, which
`test_temp_carveout_does_not_cover_system_paths` asserts as data on every
platform. Every other layer — minimum depth, profile rules, protected names,
your protected paths, reparse points — still applies inside temp.

## What still needs work before POSIX is "supported"

1. **POSIX equivalents of the Windows-only suites.** CI now runs everything on
   Ubuntu and macOS, but `tests/test_safety_denylist.py` and
   `tests/test_paths_windows.py` skip themselves off Windows. They need POSIX
   counterparts covering case sensitivity, symlink handling and permission
   errors — the rules those files guard are currently unverified on POSIX.
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

CI covers Ubuntu and macOS, so the most useful contribution now is **real
usage**: run a scan on a Linux or macOS machine, check what it offers, and open
an issue if anything looks wrong — especially a false positive.

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
