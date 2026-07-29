"""Score display and play-rating math.

Play rating is computed at read time, never stored: a chart's CC refines over
time, so a stored rating silently goes stale (``play_score.py``).
"""

from __future__ import annotations

# The in-game grades
PURE_MEMORY = 10_000_000
EX_PLUS = 9_900_000
EX = 9_800_000
AA = 9_500_000
A = 9_200_000
B = 8_900_000
C = 8_500_000


# A score is 10M plus one point per shiny pure, so the note count is the ceiling.
# The catalog's densest chart holds 2221 notes today; this carries headroom so a
# future chart doesn't make the bot reject a score a player really got.
MAX_NOTES = 4000
MAX_SCORE = PURE_MEMORY + MAX_NOTES


_GROUP = 3
_DIVIDER = "'"


def format_score(score: int) -> str:
    """Group an 8-digit score for reading: ``9123456`` -> ``09'123'456``.

    Zero-padded to 8 digits, because a score IS 8 digits in game -- and
    ``score: 0`` is a real score, never an empty one.
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


def format_rating(value: float) -> str:
    """Trim a rating to its shortest exact form, keeping one decimal minimum."""
    text = f"{value:.5f}".rstrip("0")
    return f"{text}0" if text.endswith(".") else text
