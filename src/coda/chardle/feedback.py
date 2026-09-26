"""Per-column feedback. Pure — no I/O, no DB, no Discord.

Arrows show on **both** yellow and red: direction is never withheld, which is
what keeps a 6-attempt board solvable.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from coda.chardle.columns import Clue
from coda.chardle.facts import ChartFacts
from coda.db.enums import Side

# Yellow window, in stored units: level is x2 (±4 = ±2 game levels).
LEVEL_WINDOW = 4

# The game presents all three as one side, so naming the wrong one of them is a
# near miss rather than a wrong answer. Light and Conflict stand alone.
SIDE_FAMILY = frozenset(
    {Side.ACHROMIC.to_id(), Side.LEPHON.to_id(), Side.DARK_LEPHON.to_id()}
)


class Color(enum.Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"
    UNKNOWN = "unknown"


class Arrow(enum.Enum):
    NONE = "none"
    UP = "up"
    DOWN = "down"


@dataclass(frozen=True)
class Cell:
    color: Color
    arrow: Arrow = Arrow.NONE


UNKNOWN_CELL = Cell(Color.UNKNOWN)


@dataclass(frozen=True)
class Windows:
    """The two yellow thresholds that are tuning numbers rather than facts."""

    bpm: int
    note: int


def evaluate(
    clue: Clue, guess: ChartFacts, answer: ChartFacts, windows: Windows
) -> Cell:
    """Feedback for one column of one guess row."""
    match clue:
        case Clue.TITLE:
            return _equality(guess.song_id == answer.song_id)
        case Clue.ARTIST:
            return _sets(guess.artists, answer.artists)
        case Clue.CHARTER:
            return _sets(guess.charters, answer.charters)
        case Clue.PACK:
            return _pack(guess, answer)
        case Clue.SIDE:
            return _side(guess.side, answer.side)
        case Clue.VERSION:
            return _version(guess.version, answer.version)
        case Clue.LEVEL:
            return _ordered(guess.level, answer.level, LEVEL_WINDOW, positive=True)
        case Clue.RATING:
            return _rating(guess.rating, answer.rating)
        case Clue.BPM:
            return _ordered(guess.bpm, answer.bpm, windows.bpm, positive=True)
        case Clue.NOTE:
            return _ordered(guess.note, answer.note, windows.note, positive=True)


def _equality(match: bool) -> Cell:
    return Cell(Color.GREEN if match else Color.RED)


def _side(guess: int, answer: int) -> Cell:
    if guess == answer:
        return Cell(Color.GREEN)
    if guess in SIDE_FAMILY and answer in SIDE_FAMILY:
        return Cell(Color.YELLOW)
    return Cell(Color.RED)


def _sets(guess: frozenset[str], answer: frozenset[str]) -> Cell:
    if not guess or not answer:
        return UNKNOWN_CELL
    if guess == answer:
        return Cell(Color.GREEN)
    if guess & answer:
        return Cell(Color.YELLOW)
    return Cell(Color.RED)


def _pack(guess: ChartFacts, answer: ChartFacts) -> Cell:
    if guess.pack_id is not None and guess.pack_id == answer.pack_id:
        return Cell(Color.GREEN)
    # Appended packs ("alice", "alice_append_1") share a pack NAME, which is the
    # only series relation the catalog actually records.
    if guess.pack_name == answer.pack_name:
        return Cell(Color.YELLOW)
    return Cell(Color.RED)


def _version(guess: str, answer: str) -> Cell:
    guessed, answered = _version_parts(guess), _version_parts(answer)
    if guessed is None or answered is None:
        return UNKNOWN_CELL
    arrow = _arrow(guessed, answered)
    if guessed == answered:
        return Cell(Color.GREEN)
    if guessed[0] == answered[0]:
        return Cell(Color.YELLOW, arrow)
    return Cell(Color.RED, arrow)


def _version_parts(version: str) -> tuple[int, ...] | None:
    """``"5.10"`` is newer than ``"5.9"``, so compare part-wise, never as a float."""
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError:
        return None


def _rating(guess: int, answer: int) -> Cell:
    """Same whole CC number is yellow, regardless of raw distance -- CC is stored
    x10, so ``guess // 10`` is the digit before the decimal point."""
    if guess <= 0 or answer <= 0:
        return UNKNOWN_CELL
    if guess == answer:
        return Cell(Color.GREEN)
    arrow = _arrow(guess, answer)
    if guess // 10 == answer // 10:
        return Cell(Color.YELLOW, arrow)
    return Cell(Color.RED, arrow)


def _ordered(guess, answer, window, *, positive: bool) -> Cell:
    if positive and (guess <= 0 or answer <= 0):
        return UNKNOWN_CELL
    if guess == answer:
        return Cell(Color.GREEN)
    arrow = _arrow(guess, answer)
    if abs(guess - answer) <= window:
        return Cell(Color.YELLOW, arrow)
    return Cell(Color.RED, arrow)


def _arrow(guess, answer) -> Arrow:
    return Arrow.UP if answer > guess else Arrow.DOWN
