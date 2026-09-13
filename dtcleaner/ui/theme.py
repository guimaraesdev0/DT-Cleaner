"""Colors, risk styling and terminal capability detection.

Legibility beats decoration. Every foreground/background pair here clears the
WCAG AA contrast bar at normal text size, because a cleaner is a tool people use
while tired and in a hurry, and a misread risk badge has real consequences.

`Capabilities` detects what the host terminal can actually render, so the same
build degrades gracefully from Windows Terminal down to a bare console.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from dtcleaner.core.constants import Category, RiskLevel

# --- palette ---------------------------------------------------------------
# "byte-dark" is the default theme: near-black ground, amber accent (BYTE's
# visor), and risk colors that stay distinguishable for the most common forms
# of color blindness -- risk is never signalled by color alone, always by color
# plus a text label.

PALETTE: dict[str, str] = {
    "bg": "#0d1117",
    "bg_alt": "#161b22",
    "panel": "#1c2128",
    "border": "#30363d",
    "text": "#e6edf3",
    "text_dim": "#8b949e",
    "text_faint": "#6e7681",
    "accent": "#ffb547",
    "accent_dim": "#9a6d2a",
    "ok": "#3fb950",
    "warn": "#d29922",
    "danger": "#f85149",
    "info": "#58a6ff",
    "purple": "#bc8cff",
}

RISK_COLORS: dict[RiskLevel, str] = {
    RiskLevel.LOW: PALETTE["ok"],
    RiskLevel.MEDIUM: PALETTE["warn"],
    RiskLevel.HIGH: PALETTE["danger"],
    RiskLevel.UNKNOWN: PALETTE["text_dim"],
    RiskLevel.PROTECTED: PALETTE["info"],
}

CATEGORY_COLORS: dict[Category, str] = {
    Category.NODE_MODULES: PALETTE["ok"],
    Category.FRONTEND_BUILD: PALETTE["info"],
    Category.ANDROID_BUILD: PALETTE["purple"],
    Category.EXPO_METRO: PALETTE["purple"],
    Category.PYTHON_CACHE: PALETTE["accent"],
    Category.PYTHON_BUILD: PALETTE["accent"],
    Category.RUST_TARGET: PALETTE["warn"],
    Category.DOTNET_BUILD: PALETTE["info"],
    Category.JVM_BUILD: PALETTE["warn"],
    Category.GRADLE_CACHE: PALETTE["warn"],
    Category.TOOL_CACHE: PALETTE["text_dim"],
    Category.OTHER: PALETTE["text_dim"],
}


@dataclass(frozen=True, slots=True)
class Capabilities:
    """What this terminal can render."""

    unicode: bool
    truecolor: bool
    width: int

    @property
    def narrow(self) -> bool:
        """Below this width the dashboard stacks into a single column."""
        return self.width < 90


def detect_capabilities(force_ascii: bool = False) -> Capabilities:
    unicode_ok = not force_ascii
    if unicode_ok:
        encoding = (getattr(sys.stdout, "encoding", "") or "").lower()
        unicode_ok = "utf" in encoding or os.environ.get("WT_SESSION") is not None

    colorterm = os.environ.get("COLORTERM", "").lower()
    truecolor = "truecolor" in colorterm or "24bit" in colorterm
    truecolor = truecolor or os.environ.get("WT_SESSION") is not None

    try:
        width = os.get_terminal_size().columns
    except OSError:
        width = 100

    return Capabilities(unicode=unicode_ok, truecolor=truecolor, width=width)


# --- glyphs ----------------------------------------------------------------
# Two sets, picked by capability. The ASCII set is not an afterthought: it is
# what the app looks like over SSH, in CI logs and in the legacy console host.

GLYPHS_UNICODE: dict[str, str] = {
    "check": "✔",
    "cross": "✘",
    "lock": "⛒",
    "dot": "●",
    "arrow": "›",
    "bar_full": "█",
    "bar_empty": "░",
    "spinner": "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏",
    "box_h": "─",
    "warning": "▲",
    "selected": "▣",
    "unselected": "▢",
}

GLYPHS_ASCII: dict[str, str] = {
    "check": "x",
    "cross": "!",
    "lock": "#",
    "dot": "*",
    "arrow": ">",
    "bar_full": "#",
    "bar_empty": ".",
    "spinner": "|/-\\",
    "box_h": "-",
    "warning": "!",
    "selected": "[x]",
    "unselected": "[ ]",
}


def glyphs(caps: Capabilities) -> dict[str, str]:
    return GLYPHS_UNICODE if caps.unicode else GLYPHS_ASCII


# --- Rich markup helpers ---------------------------------------------------


def risk_markup(risk: RiskLevel, label: str | None = None) -> str:
    """Colored risk badge. The label is always present, never color alone."""
    from dtcleaner.i18n import t

    text = label or t(f"risk.{risk.value}")
    color = RISK_COLORS.get(risk, PALETTE["text_dim"])
    bold = " bold" if risk in (RiskLevel.HIGH, RiskLevel.PROTECTED) else ""
    return f"[{color}{bold}]{text}[/]"


def category_markup(category: Category) -> str:
    from dtcleaner.i18n import t

    color = CATEGORY_COLORS.get(category, PALETTE["text_dim"])
    return f"[{color}]{t(f'category.{category.value}')}[/]"


def confidence_markup(value: float) -> str:
    """Confidence shown as a percentage, colored by band."""
    if value >= 0.85:
        color = PALETTE["ok"]
    elif value >= 0.60:
        color = PALETTE["warn"]
    else:
        color = PALETTE["text_dim"]
    return f"[{color}]{value:.0%}[/]"


def dim(text: str) -> str:
    return f"[{PALETTE['text_dim']}]{text}[/]"


def accent(text: str) -> str:
    return f"[{PALETTE['accent']}]{text}[/]"


def danger(text: str) -> str:
    return f"[{PALETTE['danger']} bold]{text}[/]"


def ok(text: str) -> str:
    return f"[{PALETTE['ok']}]{text}[/]"
