"""Mascot rendering invariants.

The first version of BYTE drifted out of alignment because different moods
substituted characters of different widths into a box-drawing figure. These
tests make that class of bug impossible to reintroduce.
"""

from __future__ import annotations

import pytest

from dtcleaner.i18n import set_language
from dtcleaner.ui import mascot
from dtcleaner.ui.mascot import Mood


@pytest.mark.parametrize("mood", list(Mood))
def test_art_has_identical_shape_in_every_mood(mood: Mood) -> None:
    """Every mood must produce the same line widths, or the figure warps."""
    baseline = [len(line) for line in mascot.art(Mood.IDLE).splitlines()]
    widths = [len(line) for line in mascot.art(mood).splitlines()]
    assert widths == baseline, f"{mood} changes the silhouette"


@pytest.mark.parametrize("mood", list(Mood))
def test_face_slots_are_single_characters(mood: Mood) -> None:
    """A two-character eye would push the whole row out of line."""
    for frame in range(mascot.frames_for(mood)):
        left, snout, right = mascot._face(mood, frame)
        assert len(left) == len(snout) == len(right) == 1, f"{mood} frame {frame}"


@pytest.mark.parametrize("mood", list(Mood))
def test_animation_frames_keep_the_shape(mood: Mood) -> None:
    baseline = [len(line) for line in mascot.art(mood, frame=0).splitlines()]
    for frame in range(mascot.frames_for(mood)):
        widths = [len(line) for line in mascot.art(mood, frame=frame).splitlines()]
        assert widths == baseline


def test_art_is_pure_ascii() -> None:
    """The art must render identically on every terminal, so no Unicode."""
    for mood in Mood:
        mascot.art(mood).encode("ascii")  # raises if a non-ASCII glyph slipped in


def test_art_stays_small() -> None:
    """Screen space belongs to the data. Keep the mascot compact."""
    lines = mascot.art(Mood.IDLE).splitlines()
    assert len(lines) <= 6
    assert max(len(line) for line in lines) <= 12


def test_chip_is_one_line_and_narrow() -> None:
    for mood in Mood:
        chip = mascot.chip(mood)
        assert "\n" not in chip
        assert len(chip) <= 10


def test_every_mood_has_a_line_in_both_languages() -> None:
    for code in ("en", "pt_br"):
        set_language(code)
        for mood in Mood:
            text = mascot.line(mood)
            assert text and not text.startswith("mascot."), f"{code}/{mood}"
    set_language("en")


@pytest.mark.parametrize(
    "kwargs", [{}, {"compact": True}, {"unicode": False}], ids=["block", "compact", "ascii"]
)
def test_wordmark_rows_are_aligned(kwargs) -> None:
    widths = {len(line) for line in mascot.wordmark(**kwargs).splitlines()}
    assert len(widths) == 1, f"{kwargs} wordmark is ragged"


def test_block_wordmark_fits_the_normal_breakpoint() -> None:
    """It is only shown from 90 columns up, so it must fit inside that."""
    width = max(len(line) for line in mascot.wordmark().splitlines())
    assert width <= 88


def test_compact_wordmark_fits_a_small_terminal() -> None:
    width = max(len(line) for line in mascot.wordmark(compact=True).splitlines())
    assert width <= 58


def test_ascii_wordmark_is_pure_ascii() -> None:
    mascot.wordmark(unicode=False).encode("ascii")
