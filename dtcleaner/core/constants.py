r"""Safety constants and the detection catalog.

This file is the product's dictionary. It decides NOTHING on its own -- that is
`safety.py`'s job. What lives here is purely declarative:

* what must never be touched (LAYER 1 and LAYER 2)
* which folder names are ambiguous and therefore require project context
* which files prove that a given ecosystem exists at a location

Changing any list here changes the safety behavior of the whole app, so every
entry has a reason and `tests/test_safety_denylist.py` locks the main
guarantees in place.
"""

from __future__ import annotations

from enum import StrEnum

APP_NAME = "DT-Cleaner"
APP_SLUG = "dt-cleaner"
APP_COMMAND = "dtc"
APP_VERSION = "0.1.0"
APP_REPOSITORY = "https://github.com/guimaraesdev0/DT-Cleaner"

#: How well each platform is supported. `dtc doctor` reports this, because
#: running a deletion tool on a platform whose safety rules are less exercised
#: is something the user is entitled to know up front.
#: See `docs/platforms.md` for what "experimental" means in practice.
PLATFORM_SUPPORT: dict[str, str] = {
    "win32": "supported",
    "linux": "experimental",
    "darwin": "experimental",
}


# ---------------------------------------------------------------------------
# LAYER 1 -- absolutely forbidden system directories
# ---------------------------------------------------------------------------
# Matching uses `is_within`, so anything INSIDE these paths is blocked too.
# Names are lowercase because `canonical()` casefolds on Windows.

SYSTEM_DIR_NAMES: frozenset[str] = frozenset(
    {
        "windows",
        "winnt",
        "program files",
        "program files (x86)",
        "programdata",
        "$recycle.bin",
        "system volume information",
        "recovery",
        "perflogs",
        "boot",
        "efi",
        "msocache",
        "config.msi",
        "$windows.~bt",
        "$windows.~ws",
        "documents and settings",
    }
)

# Forbidden absolute paths are resolved at runtime from environment variables
# (SystemRoot, ProgramFiles, ProgramData, ...). Using the variables instead of
# hardcoded strings covers installs outside C: and localized Windows builds.
FORBIDDEN_ENV_VARS: tuple[str, ...] = (
    "SystemRoot",
    "windir",
    "ProgramFiles",
    "ProgramFiles(x86)",
    "ProgramW6432",
    "ProgramData",
    "CommonProgramFiles",
    "CommonProgramFiles(x86)",
    "PUBLIC",
)

# ---------------------------------------------------------------------------
# LAYER 1 -- POSIX (Linux / macOS)
# ---------------------------------------------------------------------------
# The Windows lists above resolve through environment variables that simply do
# not exist on POSIX, which would leave Layer 1 empty there. These absolute
# roots are the equivalent: anything at or inside them is refused outright.
#
# Support status is tracked in `docs/platforms.md`. Windows is the supported
# platform; POSIX is experimental and `dtc doctor` says so.

POSIX_SYSTEM_ROOTS: tuple[str, ...] = (
    # Linux / Unix
    "/bin",
    "/boot",
    "/dev",
    "/etc",
    "/lib",
    "/lib32",
    "/lib64",
    "/proc",
    "/run",
    "/sbin",
    "/srv",
    "/sys",
    "/usr",
    "/var",
    "/snap",
    # macOS
    "/Applications",
    "/Library",
    "/System",
    "/Volumes",
    "/private",
    "/cores",
    "/opt/homebrew",
)

# Top-level POSIX directory names, matched the same way `SYSTEM_DIR_NAMES` is
# on Windows. Kept separate so neither platform's rules can weaken the other's.
POSIX_SYSTEM_DIR_NAMES: frozenset[str] = frozenset(
    {
        "bin",
        "boot",
        "dev",
        "etc",
        "lib",
        "lib32",
        "lib64",
        "proc",
        "run",
        "sbin",
        "srv",
        "sys",
        "usr",
        "var",
        "snap",
        "applications",
        "library",
        "system",
        "volumes",
        "private",
        "cores",
    }
)

# Hidden config directories directly in a POSIX home directory. The Windows
# profile list already covers .ssh/.aws/.config; these are the rest.
POSIX_PROTECTED_HOME_DIRS: frozenset[str] = frozenset(
    {
        ".local",
        ".cache",
        ".gnupg",
        ".password-store",
        ".mozilla",
        ".thunderbird",
        "library",  # ~/Library on macOS
    }
)


# User profile folders that can never be the target THEMSELVES. An artifact
# *inside* Documents may well be a valid candidate (a project lives there), but
# the folder itself is untouchable.
PROTECTED_PROFILE_DIRS: frozenset[str] = frozenset(
    {
        "desktop",
        "documents",
        "downloads",
        "pictures",
        "music",
        "videos",
        "onedrive",
        "appdata",
        "favorites",
        "links",
        "contacts",
        "searches",
        "saved games",
        "3d objects",
        ".ssh",
        ".gnupg",
        ".aws",
        ".azure",
        ".kube",
        ".docker",
        ".config",
    }
)

# AppData subtrees that require safe context. Tool caches under AppData\Local
# are valid candidates, but Roaming holds real application configuration and
# stays out of reach by default.
APPDATA_BLOCKED_SEGMENTS: frozenset[str] = frozenset({"roaming", "locallow"})

# Minimum depth below the volume root required for ANY deletion.
# `C:\node_modules` (depth 1) is rejected by construction: a legitimate
# artifact always lives inside a project, never bolted onto the drive root.
MIN_DELETE_DEPTH = 2


# ---------------------------------------------------------------------------
# LAYER 2 -- files and directories never deleted automatically
# ---------------------------------------------------------------------------

PROTECTED_FILE_NAMES: frozenset[str] = frozenset(
    {
        ".env",
        ".env.local",
        ".env.production",
        ".env.development",
        ".npmrc",
        ".yarnrc",
        ".yarnrc.yml",
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "bun.lockb",
        "cargo.toml",
        "cargo.lock",
        "pyproject.toml",
        "poetry.lock",
        "requirements.txt",
        "pipfile",
        "pipfile.lock",
        "setup.py",
        "setup.cfg",
        "gradle.properties",
        "local.properties",
        "google-services.json",
        "googleservice-info.plist",
        "keystore.properties",
        "firebase.json",
        "serviceaccount.json",
        "id_rsa",
        "id_ed25519",
        "known_hosts",
        "credentials",
        "secrets.json",
    }
)

PROTECTED_FILE_SUFFIXES: frozenset[str] = frozenset(
    {
        ".env",
        ".jks",
        ".keystore",
        ".pem",
        ".key",
        ".pfx",
        ".p12",
        ".cer",
        ".crt",
        ".ppk",
        ".sqlite",
        ".sqlite3",
        ".db",
        ".mdf",
        ".bak",
        ".sln",
        ".csproj",
        ".fsproj",
        ".vbproj",
    }
)

PROTECTED_FILE_PREFIXES: tuple[str, ...] = (".env.",)

# Directories that are never a target, in any context.
PROTECTED_DIR_NAMES: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "src",
        "source",
        "lib",
        "app",
        "assets",
        "public",
        "static",
        "docs",
        "test",
        "tests",
        "config",
        ".ssh",
        ".gnupg",
        "keystore",
        "secrets",
    }
)


# ---------------------------------------------------------------------------
# Ambiguous names -- removable only with confirmed project context
# ---------------------------------------------------------------------------
# A folder called `build` may be compiler output OR the source of a build
# system. `dist` may be bundler output OR a versioned distribution. Without a
# project marker nearby, neither one is touchable.

AMBIGUOUS_DIR_NAMES: frozenset[str] = frozenset(
    {
        "build",
        "dist",
        "out",
        "output",
        "bin",
        "obj",
        "target",
        "release",
        "debug",
        "coverage",
        "tmp",
        "temp",
    }
)

# Maximum distance, in levels, between a project marker and an ambiguous name.
# `C:\proj\package.json` validates `C:\proj\dist`, but not `C:\proj\a\b\c\d\dist`.
MAX_AMBIGUOUS_MARKER_DISTANCE = 4

# Maximum distance for unambiguous names (node_modules, __pycache__, ...).
# Kept short deliberately. At 8 levels a stray marker far up the tree (in the
# user profile, say) would "prove" a project for an artifact that has nothing to
# do with it, producing a misleading project root in the UI. Real tool folders
# sit within a level or two of their marker.
MAX_MARKER_DISTANCE = 4


# ---------------------------------------------------------------------------
# Domain enums
# ---------------------------------------------------------------------------


class RiskLevel(StrEnum):
    """Order matters: `RISK_ORDER` below defines increasing severity."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"
    PROTECTED = "PROTECTED"


RISK_ORDER: dict[RiskLevel, int] = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.UNKNOWN: 3,
    RiskLevel.PROTECTED: 4,
}

SELECTABLE_RISKS: frozenset[RiskLevel] = frozenset(
    {RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH}
)


class Category(StrEnum):
    NODE_MODULES = "Node Modules"
    FRONTEND_BUILD = "Frontend Build Output"
    ANDROID_BUILD = "Android Builds"
    EXPO_METRO = "Expo / Metro"
    PYTHON_CACHE = "Python Cache"
    PYTHON_BUILD = "Python Build"
    RUST_TARGET = "Rust Target"
    DOTNET_BUILD = ".NET bin/obj"
    JVM_BUILD = "JVM Build Output"
    GRADLE_CACHE = "Gradle Cache"
    TOOL_CACHE = "Tool Cache"
    OTHER = "Other Safe Artifacts"


CATEGORY_ORDER: tuple[Category, ...] = (
    Category.NODE_MODULES,
    Category.ANDROID_BUILD,
    Category.FRONTEND_BUILD,
    Category.EXPO_METRO,
    Category.PYTHON_CACHE,
    Category.PYTHON_BUILD,
    Category.RUST_TARGET,
    Category.DOTNET_BUILD,
    Category.JVM_BUILD,
    Category.GRADLE_CACHE,
    Category.TOOL_CACHE,
    Category.OTHER,
)


class Ecosystem(StrEnum):
    NODE = "node"
    PYTHON = "python"
    RUST = "rust"
    DOTNET = "dotnet"
    JVM = "jvm"
    ANDROID = "android"
    UNKNOWN = "unknown"


class ScanMode(StrEnum):
    QUICK = "quick"
    FULL = "full"
    CUSTOM = "custom"


class DeleteMode(StrEnum):
    RECYCLE_BIN = "recycle_bin"
    PERMANENT = "permanent"


# ---------------------------------------------------------------------------
# Project markers -- the proof that an ecosystem exists at a location
# ---------------------------------------------------------------------------
# These are the files `ContextValidator` looks for while walking up the tree.
# Without at least one of them, a candidate never rises above UNKNOWN.

PROJECT_MARKERS: dict[Ecosystem, frozenset[str]] = {
    Ecosystem.NODE: frozenset(
        {
            "package.json",
            "package-lock.json",
            "pnpm-lock.yaml",
            "yarn.lock",
            "bun.lockb",
            "tsconfig.json",
            "vite.config.js",
            "vite.config.ts",
            "vite.config.mjs",
            "next.config.js",
            "next.config.ts",
            "next.config.mjs",
            "nuxt.config.js",
            "nuxt.config.ts",
            "svelte.config.js",
            "angular.json",
            "turbo.json",
            "webpack.config.js",
            "rollup.config.js",
        }
    ),
    Ecosystem.PYTHON: frozenset(
        {
            "pyproject.toml",
            "setup.py",
            "setup.cfg",
            "requirements.txt",
            "poetry.lock",
            "pipfile",
            "tox.ini",
            "manage.py",
        }
    ),
    Ecosystem.RUST: frozenset({"cargo.toml"}),
    Ecosystem.DOTNET: frozenset({"global.json", "nuget.config", "directory.build.props"}),
    Ecosystem.JVM: frozenset(
        {
            "pom.xml",
            "build.gradle",
            "build.gradle.kts",
            "settings.gradle",
            "settings.gradle.kts",
            "gradlew",
            "gradlew.bat",
            "mvnw",
            "build.sbt",
        }
    ),
    Ecosystem.ANDROID: frozenset(
        {
            "settings.gradle",
            "settings.gradle.kts",
            "gradlew",
            "gradlew.bat",
            "app.json",
            "app.config.js",
            "app.config.ts",
            "eas.json",
        }
    ),
}

# Suffix-based markers (glob-like), checked in addition to exact names.
PROJECT_MARKER_SUFFIXES: dict[Ecosystem, tuple[str, ...]] = {
    Ecosystem.DOTNET: (".sln", ".csproj", ".fsproj", ".vbproj"),
    Ecosystem.PYTHON: (".egg-info",),
}


# ---------------------------------------------------------------------------
# Directories skipped during the walk
# ---------------------------------------------------------------------------
# Descending into these is wasted work (or a risk). Skipping early is the
# scanner's main optimization: it avoids millions of stat() calls inside nested
# node_modules trees.

SKIP_TRAVERSE_DIR_NAMES: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",  # the top was found; no need to descend
        "$recycle.bin",
        "system volume information",
        "windows",
        "winnt",
        "program files",
        "program files (x86)",
        "programdata",
        "recovery",
        "perflogs",
        "msocache",
        "config.msi",
        ".venv",
        "venv",
        "env",
        "site-packages",
    }
)

# Default Quick Scan roots, resolved at runtime against the user profile.
QUICK_SCAN_RELATIVE_ROOTS: tuple[str, ...] = (
    "dev",
    "Dev",
    "projects",
    "Projects",
    "repos",
    "Repos",
    "code",
    "Code",
    "source",
    "src",
    "workspace",
    "Documents/GitHub",
    "Documents/projects",
    "Desktop",
)

# POSIX equivalents of the Windows drive-letter guesses below.
QUICK_SCAN_POSIX_ROOTS: tuple[str, ...] = (
    "/srv/dev",
    "/opt/dev",
    "/workspace",
    "/work",
)

QUICK_SCAN_ABSOLUTE_ROOTS: tuple[str, ...] = (
    r"C:\dev",
    r"C:\projects",
    r"C:\repos",
    r"C:\code",
    r"C:\work",
    r"D:\dev",
    r"D:\projects",
    r"D:\repos",
    r"D:\code",
    r"D:\work",
)


# ---------------------------------------------------------------------------
# Confidence thresholds
# ---------------------------------------------------------------------------

# Below this value an item becomes UNKNOWN and is never selectable.
MIN_CONFIDENCE_DELETABLE = 0.60

# Auto-selection in Safe Mode requires high confidence AND LOW risk.
MIN_CONFIDENCE_AUTOSELECT = 0.85
