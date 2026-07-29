"""Score display and play-rating math.

Play rating is computed at read time, never stored: a chart's CC refines over
time, so a stored rating silently goes stale (``play_score.py``).
"""

from __future__ import annotations

from enum import IntEnum
from math import isqrt

# The in-game grades
PURE_MEMORY = 10_000_000
EX_PLUS = 9_900_000
EX = 9_800_000
AA = 9_500_000
A = 9_200_000
B = 8_900_000
C = 8_500_000


class Grade(IntEnum):
    """A score's in-game grade, ordered so ``>`` means "better"."""

    D = 0
    C = 1
    B = 2
    A = 3
    AA = 4
    EX = 5
    EX_PLUS = 6
    PM = 7


# Highest first: grade_of returns the first floor the score clears.
_GRADE_FLOORS: tuple[tuple[int, Grade], ...] = (
    (PURE_MEMORY, Grade.PM),
    (EX_PLUS, Grade.EX_PLUS),
    (EX, Grade.EX),
    (AA, Grade.AA),
    (A, Grade.A),
    (B, Grade.B),
    (C, Grade.C),
)


def grade_of(score: int) -> Grade:
    """The grade a score earns. Below C is ``Grade.D``."""
    for floor, grade in _GRADE_FLOORS:
        if score >= floor:
            return grade
    return Grade.D


def _max_notes() -> int:
    """The largest note count on which 10,000,000 still proves a pure memory.

    A note is worth ``10M / n`` (half that for a far), and each shiny pure adds
    one point on top, so an all-shiny run with a single far scores

        floor(10M - 5M/n) + (n - 1)

    which reaches 10M once the shiny bonus covers the far's lost half-note --
    ``n - 1 >= ceil(5M / n)``. Past that count the score no longer distinguishes
    a pure memory from a one-far play, so no chart can exceed it and still let
    the game display a PM honestly. Solving ``n^2 - n - 5M >= 0`` seeds the
    search; the ceiling makes the seed exact rather than off by one.
    """
    half = PURE_MEMORY // 2
    n = (1 + isqrt(1 + 4 * half)) // 2
    while n - 1 < -(-half // n):
        n += 1
    return n


MAX_NOTES = _max_notes()
MAX_SCORE = PURE_MEMORY + MAX_NOTES


_GROUP = 3
_DIVIDER = "'"


def format_score(score: int) -> str:
    """Group an 8-digit score for reading: ``9123456`` -> ``09'123'456``.

    Zero-padded to 8 digits.
    """
    digits = f"{score:08d}"
    head = len(digits) % _GROUP or _GROUP
    groups = [digits[:head]] + [
        digits[i : i + _GROUP] for i in range(head, len(digits), _GROUP)
    ]
    return _DIVIDER.join(groups)


def calculate_play_rating(score: int, chart_cc: float) -> float:
    """The play rating for a score on a chart of constant ``chart_cc``.

    Caller must pass a KNOWN cc (``> 0``); an unknown one has no rating to show
    and must be omitted rather than rendered from a sentinel.
    """
    if score >= PURE_MEMORY:
        modifier = 2.0
    elif score >= EX:
        modifier = 1 + (score - EX) / 200_000
    else:
        modifier = (score - AA) / 300_000
    return max(0.0, round(chart_cc + modifier, 5))


def format_rating(value: float, precision: int = 5) -> str:
    """Trim a rating to its shortest exact form, keeping one decimal minimum."""
    text = f"{round(value, precision)}".rstrip("0")
    return f"{text}0" if text.endswith(".") else text
