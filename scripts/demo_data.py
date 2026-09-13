"""Synthetic data for the README screenshots.

Everything here is invented. The screenshots must never show the machine that
rendered them -- no real paths, no real disk usage, no real scan history.

The numbers are chosen to look like a working developer's drive after a couple
of busy years: a few large Rust `target` directories, Android build output, a
pile of `node_modules`, and roughly 100 GB of reclaimable space in total. It
also includes the two cases that matter most for understanding the product:
one PROTECTED item and two UNKNOWN ones.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from dtcleaner.core.constants import Category, DeleteMode, Ecosystem, RiskLevel, ScanMode
from dtcleaner.core.models import (
    CleanupResult,
    DeletionOutcome,
    DiskInfo,
    ScanItem,
    ScanSession,
)

GB = 1024**3
MB = 1024**2

#: Fictional 2 TB workstation drive, comfortably full.
DEMO_DISKS = [
    DiskInfo(
        device="D:",
        mountpoint="D:\\",
        total_bytes=2048 * GB,
        used_bytes=1728 * GB,
        free_bytes=320 * GB,
        drive_type="fixed",
    )
]

#: (path, name, category, ecosystem, item_type, size, risk, confidence,
#:  project_root, reason_key, reason_params, markers, regenerate_hint)
_ITEMS: tuple[tuple, ...] = (
    (
        r"D:\work\payments-api\target", "target", Category.RUST_TARGET, Ecosystem.RUST,
        "cargo_target", int(21.4 * GB), RiskLevel.MEDIUM, 0.86, r"D:\work\payments-api",
        "detect.proven", {"marker": "cargo.toml", "distance": 1, "ecosystem": "Rust"},
        ("cargo.toml",), "cargo build (re-downloads and recompiles crates)",
    ),
    (
        r"D:\work\ledger-engine\target", "target", Category.RUST_TARGET, Ecosystem.RUST,
        "cargo_target", int(14.8 * GB), RiskLevel.MEDIUM, 0.80, r"D:\work\ledger-engine",
        "detect.proven", {"marker": "cargo.toml", "distance": 1, "ecosystem": "Rust"},
        ("cargo.toml",), "cargo build (re-downloads and recompiles crates)",
    ),
    (
        r"D:\work\edge-proxy\target", "target", Category.RUST_TARGET, Ecosystem.RUST,
        "cargo_target", int(9.3 * GB), RiskLevel.MEDIUM, 0.80, r"D:\work\edge-proxy",
        "detect.proven", {"marker": "cargo.toml", "distance": 1, "ecosystem": "Rust"},
        ("cargo.toml",), "cargo build (re-downloads and recompiles crates)",
    ),
    (
        r"D:\work\android-wallet\android\app\build", "build", Category.ANDROID_BUILD,
        Ecosystem.ANDROID, "android_app_build", int(9.6 * GB), RiskLevel.LOW, 0.94,
        r"D:\work\android-wallet\android",
        "detect.proven", {"marker": "settings.gradle", "distance": 2, "ecosystem": "Android"},
        ("settings.gradle", "gradlew"), "gradlew assembleDebug",
    ),
    (
        r"D:\work\data-platform\target", "target", Category.JVM_BUILD, Ecosystem.JVM,
        "maven_target", int(7.9 * GB), RiskLevel.LOW, 0.88, r"D:\work\data-platform",
        "detect.proven", {"marker": "pom.xml", "distance": 1, "ecosystem": "JVM"},
        ("pom.xml", "mvnw"), "mvn package",
    ),
    (
        r"D:\dev\mobile-wallet\node_modules", "node_modules", Category.NODE_MODULES,
        Ecosystem.NODE, "node_modules", int(5.2 * GB), RiskLevel.LOW, 1.0,
        r"D:\dev\mobile-wallet",
        "detect.proven", {"marker": "package.json", "distance": 1, "ecosystem": "Node"},
        ("package.json", "pnpm-lock.yaml"), "npm install / pnpm install / yarn",
    ),
    (
        r"D:\dev\acme-dashboard\node_modules", "node_modules", Category.NODE_MODULES,
        Ecosystem.NODE, "node_modules", int(4.6 * GB), RiskLevel.LOW, 1.0,
        r"D:\dev\acme-dashboard",
        "detect.proven", {"marker": "package.json", "distance": 1, "ecosystem": "Node"},
        ("package.json", "yarn.lock"), "npm install / pnpm install / yarn",
    ),
    (
        r"D:\dev\reporting-service\bin", "bin", Category.DOTNET_BUILD, Ecosystem.DOTNET,
        "dotnet_bin", int(4.2 * GB), RiskLevel.LOW, 0.80, r"D:\dev\reporting-service",
        "detect.proven", {"marker": "reporting.csproj", "distance": 1, "ecosystem": ".NET"},
        ("reporting.csproj",), "dotnet build",
    ),
    (
        r"D:\dev\shop-storefront\node_modules", "node_modules", Category.NODE_MODULES,
        Ecosystem.NODE, "node_modules", int(3.9 * GB), RiskLevel.LOW, 1.0,
        r"D:\dev\shop-storefront",
        "detect.proven", {"marker": "package.json", "distance": 1, "ecosystem": "Node"},
        ("package.json", "package-lock.json"), "npm install / pnpm install / yarn",
    ),
    (
        r"D:\dev\legacy-portal\.gradle", ".gradle", Category.GRADLE_CACHE, Ecosystem.JVM,
        "gradle_project_cache", int(3.4 * GB), RiskLevel.LOW, 0.85, r"D:\dev\legacy-portal",
        "detect.proven", {"marker": "build.gradle", "distance": 1, "ecosystem": "JVM"},
        ("build.gradle", "gradlew"), "gradlew build (re-syncs the project)",
    ),
    (
        r"D:\dev\design-system\node_modules", "node_modules", Category.NODE_MODULES,
        Ecosystem.NODE, "node_modules", int(3.1 * GB), RiskLevel.LOW, 1.0,
        r"D:\dev\design-system",
        "detect.proven", {"marker": "package.json", "distance": 1, "ecosystem": "Node"},
        ("package.json", "turbo.json"), "npm install / pnpm install / yarn",
    ),
    (
        r"D:\dev\reporting-service\obj", "obj", Category.DOTNET_BUILD, Ecosystem.DOTNET,
        "dotnet_obj", int(2.9 * GB), RiskLevel.LOW, 0.85, r"D:\dev\reporting-service",
        "detect.proven", {"marker": "reporting.csproj", "distance": 1, "ecosystem": ".NET"},
        ("reporting.csproj",), "dotnet build",
    ),
    (
        r"D:\dev\docs-site\node_modules", "node_modules", Category.NODE_MODULES,
        Ecosystem.NODE, "node_modules", int(2.7 * GB), RiskLevel.LOW, 1.0,
        r"D:\dev\docs-site",
        "detect.proven", {"marker": "package.json", "distance": 1, "ecosystem": "Node"},
        ("package.json",), "npm install / pnpm install / yarn",
    ),
    (
        r"D:\dev\acme-dashboard\.next", ".next", Category.FRONTEND_BUILD, Ecosystem.NODE,
        "next_build", int(2.3 * GB), RiskLevel.LOW, 1.0, r"D:\dev\acme-dashboard",
        "detect.proven", {"marker": "next.config.js", "distance": 1, "ecosystem": "Node"},
        ("next.config.js", "package.json"), "next build",
    ),
    (
        r"D:\dev\ml-pipeline\.mypy_cache", ".mypy_cache", Category.PYTHON_CACHE,
        Ecosystem.PYTHON, "mypy_cache", int(1.6 * GB), RiskLevel.LOW, 0.95,
        r"D:\dev\ml-pipeline",
        "detect.proven", {"marker": "pyproject.toml", "distance": 1, "ecosystem": "Python"},
        ("pyproject.toml", "poetry.lock"), "mypy .",
    ),
    (
        r"D:\work\android-wallet\.expo", ".expo", Category.EXPO_METRO, Ecosystem.ANDROID,
        "expo_cache", int(780 * MB), RiskLevel.LOW, 0.90, r"D:\work\android-wallet",
        "detect.proven", {"marker": "app.json", "distance": 1, "ecosystem": "Android"},
        ("app.json", "eas.json"), "npx expo start",
    ),
    (
        r"D:\dev\ml-pipeline\__pycache__", "__pycache__", Category.PYTHON_CACHE,
        Ecosystem.PYTHON, "pycache", int(412 * MB), RiskLevel.LOW, 1.0,
        r"D:\dev\ml-pipeline",
        "detect.proven", {"marker": "pyproject.toml", "distance": 1, "ecosystem": "Python"},
        ("pyproject.toml",), "regenerated automatically on the next run",
    ),
    (
        r"D:\dev\ml-pipeline\.pytest_cache", ".pytest_cache", Category.PYTHON_CACHE,
        Ecosystem.PYTHON, "pytest_cache", int(186 * MB), RiskLevel.LOW, 0.95,
        r"D:\dev\ml-pipeline",
        "detect.proven", {"marker": "pyproject.toml", "distance": 1, "ecosystem": "Python"},
        ("pyproject.toml",), "pytest",
    ),
    # --- the two cases the product exists for --------------------------------
    (
        r"D:\archive\vendor-exports\build", "build", Category.OTHER, Ecosystem.UNKNOWN,
        "node_build", int(2.4 * GB), RiskLevel.UNKNOWN, 0.30, None,
        "safety.ambiguous_no_project", {"name": "build"}, (), "",
    ),
    (
        r"D:\archive\range-data\target", "target", Category.OTHER, Ecosystem.UNKNOWN,
        "cargo_target", int(890 * MB), RiskLevel.UNKNOWN, 0.30, None,
        "safety.ambiguous_no_project", {"name": "target"}, (), "",
    ),
)

#: A perfectly valid Node build output that happens to hold a `.env`.
_PROTECTED = (
    r"D:\dev\client-portal\dist", "dist", Category.FRONTEND_BUILD, Ecosystem.NODE,
    "node_dist", int(1.2 * GB), r"D:\dev\client-portal",
)


def build_session() -> ScanSession:
    """A finished scan holding ~100 GB of reclaimable artifacts."""
    started = datetime.now() - timedelta(seconds=47)
    items: list[ScanItem] = []

    for (
        path, name, category, ecosystem, item_type, size, risk, confidence,
        project_root, reason_key, reason_params, markers, hint,
    ) in _ITEMS:
        item = ScanItem(
            path=path,
            name=name,
            category=category,
            ecosystem=ecosystem,
            item_type=item_type,
            size_bytes=size,
            file_count=size // 18_000,
            risk_level=risk,
            confidence=confidence,
            project_root=project_root,
            ambiguous=name in ("build", "dist", "target", "bin", "obj"),
            reason_key=reason_key,
            reason_params=reason_params,
            markers_found=markers,
            regenerate_hint=hint,
            last_modified=started - timedelta(days=len(items) * 3 + 2),
        )
        item.selected = item.should_autoselect(safe_mode=True)
        items.append(item)

    path, name, category, ecosystem, item_type, size, project_root = _PROTECTED
    protected = ScanItem(
        path=path,
        name=name,
        category=category,
        ecosystem=ecosystem,
        item_type=item_type,
        size_bytes=size,
        file_count=size // 18_000,
        confidence=0.0,
        project_root=project_root,
        ambiguous=True,
        reason_key="detect.proven",
        reason_params={"marker": "package.json", "distance": 1, "ecosystem": "Node"},
        markers_found=("package.json",),
        last_modified=started - timedelta(days=9),
    )
    protected.mark_protected("safety.sensitive_file", name=".env")
    items.append(protected)

    items.sort(key=lambda i: -i.size_bytes)

    return ScanSession(
        started_at=started,
        finished_at=started + timedelta(seconds=47),
        scan_mode=ScanMode.FULL,
        scanned_roots=["D:\\"],
        items=items,
        dirs_visited=184_302,
    )


def build_cleanup_result(session: ScanSession) -> CleanupResult:
    """A completed cleanup of everything the session had selected."""
    started = datetime.now() - timedelta(seconds=68)
    outcomes = [
        DeletionOutcome(
            item_id=item.id,
            path=item.path,
            success=True,
            freed_bytes=item.size_bytes,
            method="recycle_bin",
        )
        for item in session.selected_items
    ]
    return CleanupResult(
        plan_id="demo-plan",
        session_id=session.id,
        started_at=started,
        finished_at=started + timedelta(seconds=68),
        delete_mode=DeleteMode.RECYCLE_BIN,
        outcomes=outcomes,
        log_path=r"C:\Users\dev\.dt-cleaner\logs\dtc-20260913-094512.log",
    )


#: Fake history rows for the Home screen's side panel.
DEMO_HISTORY = [
    (int(62.4 * GB), 41, datetime.now() - timedelta(days=34)),
    (int(18.9 * GB), 12, datetime.now() - timedelta(days=96)),
]
