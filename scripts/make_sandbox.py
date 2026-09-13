"""Create a throwaway project tree to try DT-Cleaner against.

Builds a folder with realistic artifacts AND realistic traps, so you can verify
the safety rules yourself without pointing the app at real work:

    python scripts/make_sandbox.py

It prints the path. Scan it, review it, clean it, and check what survived.
Delete the whole folder when you are done.
"""

from __future__ import annotations

import os
import random
import shutil
import sys
from pathlib import Path

SANDBOX = Path(os.environ.get("TEMP", ".")) / "dtc-sandbox"


def fill(directory: Path, count: int = 6, size_kb: int = 400) -> int:
    directory.mkdir(parents=True, exist_ok=True)
    total = 0
    for index in range(count):
        payload = size_kb * 1024 + random.randint(0, 50_000)
        (directory / f"chunk_{index}.bin").write_bytes(b"x" * payload)
        total += payload
    return total


def build() -> Path:
    shutil.rmtree(SANDBOX, ignore_errors=True)

    # --- real projects: these SHOULD be found and offered -------------------
    web = SANDBOX / "web-app"
    (web).mkdir(parents=True)
    (web / "package.json").write_text('{"name":"web-app"}', encoding="utf-8")
    (web / "yarn.lock").write_text("", encoding="utf-8")
    (web / "src").mkdir()
    (web / "src" / "index.ts").write_text("export const x = 1", encoding="utf-8")
    fill(web / "node_modules" / "react")
    fill(web / "node_modules" / "lodash")
    fill(web / "dist")
    fill(web / ".next")

    api = SANDBOX / "api-service"
    api.mkdir(parents=True)
    (api / "pyproject.toml").write_text("[project]\nname='api'", encoding="utf-8")
    fill(api / "__pycache__", 4, 200)
    fill(api / ".pytest_cache", 3, 150)

    rust = SANDBOX / "cli-tool"
    rust.mkdir(parents=True)
    (rust / "Cargo.toml").write_text('[package]\nname = "cli-tool"', encoding="utf-8")
    fill(rust / "target" / "debug", 8, 500)

    mobile = SANDBOX / "mobile-app"
    (mobile / "android" / "app").mkdir(parents=True)
    (mobile / "android" / "settings.gradle").write_text("rootProject.name='m'", encoding="utf-8")
    (mobile / "package.json").write_text('{"name":"mobile"}', encoding="utf-8")
    fill(mobile / "android" / "app" / "build", 7, 600)
    fill(mobile / ".expo", 3, 200)

    # --- traps: these must NOT become deletable -----------------------------
    # 1. a "build" folder with no project anywhere near it
    trap_build = SANDBOX / "old-photos" / "build"
    fill(trap_build, 4, 300)
    (trap_build / "vacation.txt").write_text("family photos", encoding="utf-8")

    # 2. a "target" folder that is not Rust
    trap_target = SANDBOX / "shooting-range" / "target"
    fill(trap_target, 3, 200)
    (trap_target / "scores.csv").write_text("10,9,8", encoding="utf-8")

    # 3. a perfectly valid dist that happens to hold a .env
    secret = SANDBOX / "client-site"
    secret.mkdir(parents=True)
    (secret / "package.json").write_text('{"name":"client"}', encoding="utf-8")
    fill(secret / "dist", 3, 300)
    (secret / "dist" / ".env").write_text("API_KEY=do-not-delete-me", encoding="utf-8")

    return SANDBOX


def main() -> None:
    path = build()
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())

    print(f"\nSandbox created: {path}")
    print(f"Total size: {total / 1024 / 1024:.1f} MB\n")
    print("Try it:")
    print(f'  dtc scan --path "{path}"      (report only, deletes nothing)')
    print(f"  dtc                            (interactive: Custom Scan -> this path)\n")
    print("What SHOULD be offered:")
    print("  web-app/node_modules, web-app/dist, web-app/.next")
    print("  api-service/__pycache__, api-service/.pytest_cache")
    print("  cli-tool/target, mobile-app/android/app/build, mobile-app/.expo\n")
    print("What must NOT be selectable (the traps):")
    print("  old-photos/build        -> UNKNOWN, no project marker")
    print("  shooting-range/target   -> UNKNOWN, no Cargo.toml")
    print("  client-site/dist        -> PROTECTED, contains a .env\n")
    print(f"Remove it when done:  rmdir /s /q \"{path}\"\n")


if __name__ == "__main__":
    sys.exit(main())
