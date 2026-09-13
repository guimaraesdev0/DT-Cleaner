"""BYTE, the watchdog -- DT-Cleaner's mascot.

Concept
-------
BYTE is a small dog that guards your disk. The name is the joke: a dog named
BYTE, who does not *bite* anything without permission.

A guard dog is the right metaphor for this product. It is friendly, it fetches
things, and it does not let strangers past. That matches the app's stance
exactly: helpful about finding junk, immovable about what it refuses to touch.

Design constraints
------------------
The art is deliberately tiny: 5 lines, 9 columns, pure ASCII. Earlier drafts
used box-drawing characters and a taller figure, which broke alignment on
terminals with different glyph widths and ate screen space the data needed.
Every line here is a fixed width and every mood swaps exactly three single
characters, so alignment cannot drift no matter which face is showing.

Usage rules
-----------
1. One BYTE per screen, never two.
2. The 5-line art appears only on Splash, Home, Scan, Cleanup, Summary, Help
   and empty states. Everywhere else uses the one-line chip.
3. BYTE never looks happy on a risk screen: Preview with anything above LOW
   risk must use WARNING, and a Summary with failures uses WARNING too.
4. Animation respects `settings.animations`; with it off, frame 0 is used.
5. The art is ASCII-only by design, so there is no separate fallback to keep in
   sync -- it renders identically everywhere.
"""

from __future__ import annotations

from enum import StrEnum

from dtcleaner.i18n import t


class Mood(StrEnum):
    """BYTE's states. Each maps to one face and one line of dialogue."""

    IDLE = "idle"
    SCANNING = "scanning"
    THINKING = "thinking"
    WARNING = "warning"
    BLOCKED = "blocked"
    WORKING = "working"
    HAPPY = "happy"
    EMPTY = "empty"


#: Face slots for each mood: (left eye, snout, right eye).
#: Every value MUST be exactly one character wide, or the art misaligns.
_FACES: dict[Mood, tuple[str, str, str]] = {
    Mood.IDLE: ("o", "w", "o"),
    Mood.SCANNING: ("o", "w", "o"),
    Mood.THINKING: ("o", "~", "o"),
    Mood.WARNING: ("O", "o", "O"),
    Mood.BLOCKED: ("x", "-", "x"),
    Mood.WORKING: ("o", "w", "o"),
    Mood.HAPPY: ("^", "w", "^"),
    Mood.EMPTY: ("-", ".", "-"),
}

#: Scanning: the eyes glance side to side, like a dog following a scent.
_SCAN_FRAMES: tuple[tuple[str, str, str], ...] = (
    ("o", "w", "o"),
    ("O", "w", "o"),
    ("o", "w", "o"),
    ("o", "w", "O"),
)

#: Working: the snout moves, like the dog is busy digging.
_WORK_FRAMES: tuple[tuple[str, str, str], ...] = (
    ("o", "w", "o"),
    ("o", "v", "o"),
    ("o", "w", "o"),
    ("o", "u", "o"),
)

#: 5 lines, 9 columns. The two `__` on top are floppy ears.
_ART = """\
 __   __
/  \\_/  \\
| {l}   {r} |
|   {m}   |
 \\_____/"""


def art(mood: Mood = Mood.IDLE, *, frame: int = 0, unicode: bool = True) -> str:
    """The 5-line BYTE. `unicode` is accepted for API symmetry but unused:
    the art is ASCII everywhere, which is the point."""
    left, snout, right = _face(mood, frame)
    return _ART.format(l=left, m=snout, r=right)


def chip(mood: Mood = Mood.IDLE, *, frame: int = 0, unicode: bool = True) -> str:
    """One-line BYTE for the header and status bars: `(o w o)`."""
    left, snout, right = _face(mood, frame)
    return f"({left} {snout} {right})"


def line(mood: Mood = Mood.IDLE) -> str:
    """BYTE's dialogue for this mood, in the active language."""
    return t(f"mascot.{mood.value}")


def frames_for(mood: Mood) -> int:
    """How many animation frames this mood has (1 means static)."""
    if mood is Mood.SCANNING:
        return len(_SCAN_FRAMES)
    if mood is Mood.WORKING:
        return len(_WORK_FRAMES)
    return 1


def _face(mood: Mood, frame: int) -> tuple[str, str, str]:
    if mood is Mood.SCANNING:
        return _SCAN_FRAMES[frame % len(_SCAN_FRAMES)]
    if mood is Mood.WORKING:
        return _WORK_FRAMES[frame % len(_WORK_FRAMES)]
    return _FACES[mood]


#: Full splash wordmark, block glyphs. 80 columns wide, so the stylesheet only
#: shows it from the `-normal` breakpoint (90 columns) upward.
WORDMARK_BLOCK = """\
██████╗ ████████╗      ██████╗██╗     ███████╗ █████╗ ███╗   ██╗███████╗██████╗
██╔══██╗╚══██╔══╝     ██╔════╝██║     ██╔════╝██╔══██╗████╗  ██║██╔════╝██╔══██╗
██║  ██║   ██║ █████╗ ██║     ██║     █████╗  ███████║██╔██╗ ██║█████╗  ██████╔╝
██║  ██║   ██║ ╚════╝ ██║     ██║     ██╔══╝  ██╔══██║██║╚██╗██║██╔══╝  ██╔══██╗
██████╔╝   ██║        ╚██████╗███████╗███████╗██║  ██║██║ ╚████║███████╗██║  ██║
╚═════╝    ╚═╝         ╚═════╝╚══════╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝"""

#: Narrow variant, 30 columns. Shown instead of the block wordmark below 90
#: columns, so a small terminal still gets a logo rather than a blank gap.
WORDMARK_COMPACT = """\
╔╦╗╔╦╗   ╔═╗╦  ╔═╗╔═╗╔╗╔╔═╗╦═╗
 ║║ ║    ║  ║  ║╣ ╠═╣║║║║╣ ╠╦╝
═╩╝ ╩    ╚═╝╩═╝╚═╝╩ ╩╝╚╝╚═╝╩╚═"""

#: Kept for callers that still ask for "the" unicode wordmark.
WORDMARK_UNICODE = WORDMARK_BLOCK

#: ASCII fallback is plain letterspaced text on purpose. A hand-drawn ASCII
#: logo looks like noise at this size, and the splash already names the app.
WORDMARK_ASCII = """\
+--------------------------+
|   D T - C L E A N E R    |
+--------------------------+"""


def wordmark(unicode: bool = True, compact: bool = False) -> str:
    """Pick the wordmark for the current terminal.

    Rows are padded to equal width so the block letters stay square; a ragged
    last row reads as a rendering glitch rather than as a logo.
    """
    if not unicode:
        return _pad(WORDMARK_ASCII)
    return _pad(WORDMARK_COMPACT if compact else WORDMARK_BLOCK)


def _pad(art_text: str) -> str:
    lines = art_text.splitlines()
    width = max(len(line) for line in lines)
    return "\n".join(line.ljust(width) for line in lines)
