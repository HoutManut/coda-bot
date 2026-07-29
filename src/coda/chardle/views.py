"""What the renderers are handed. Data only: no Discord, no PIL, no I/O.

Separate from the renderers because both of them read these -- the embed writer
and the image compositor -- and a renderer that imported the other's module
would close a cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from coda.chardle.columns import Clue
from coda.chardle.facts import ChartFacts
from coda.chardle.feedback import Cell
from coda.db.enums import ChardleState


@dataclass(frozen=True)
class BoardRow:
    name: str
    label: str | None
    cells: list[Cell]
    facts: ChartFacts


@dataclass(frozen=True)
class Board:
    """Everything the renderers need. Built by the caller; no I/O in here."""

    tier: str
    tier_label: str
    columns: list[Clue]
    rows: list[BoardRow]
    max_attempts: int | None
    state: ChardleState
    answer: ChartFacts
    puzzle_number: int | None = None
    filters_note: str | None = None


@dataclass(frozen=True)
class ScoreboardEntry:
    discord_id: int
    state: ChardleState
    taken: int
    # None while the board is still live: an unfinished grid would leak how many
    # guesses are left as well as how the player is doing.
    grid: list[str] | None


@dataclass(frozen=True)
class DailyScoreboard:
    """Everything the scoreboard renderers need. Built by the caller; no I/O."""

    puzzle_number: int
    tier_label: str
    max_attempts: int | None
    entries: list[ScoreboardEntry]
    resets_at: datetime | None
