"""Clue columns: what they are, which order they render in, and which ones a
given answer pool can actually support.

Membership is rolled per puzzle and frozen on it. **Order is a canonical
constant** — a player learns the layout once, and the emoji share grid means the
same thing on every board.
"""

from __future__ import annotations

import enum
import random
from collections.abc import Sequence

from coda.chardle.facts import ChartFacts


class Clue(enum.StrEnum):
    TITLE = "title"
    ARTIST = "artist"
    LEVEL = "level"
    RATING = "rating"
    PACK = "pack"
    VERSION = "version"
    CHARTER = "charter"
    SIDE = "side"
    BPM = "bpm"
    NOTE = "note"


# The jacket is an identifier rather than a clue, so it is not a column here.
CANONICAL_ORDER: tuple[Clue, ...] = (
    Clue.TITLE,
    Clue.ARTIST,
    Clue.LEVEL,
    Clue.RATING,
    Clue.PACK,
    Clue.VERSION,
    Clue.CHARTER,
    Clue.SIDE,
    Clue.BPM,
    Clue.NOTE,
)

MAX_COLUMNS = 7

# At most one from each: CC determines level, and a pack ships at a version.
REDUNDANT_GROUPS: tuple[tuple[Clue, ...], ...] = (
    (Clue.LEVEL, Clue.RATING),
    (Clue.PACK, Clue.VERSION),
    (Clue.BPM, Clue.NOTE),
)

ORDERED_CLUES = frozenset(
    {Clue.LEVEL, Clue.RATING, Clue.VERSION, Clue.BPM, Clue.NOTE}
)

LABELS: dict[Clue, str] = {
    Clue.TITLE: "Title",
    Clue.ARTIST: "Artist",
    Clue.LEVEL: "Level",
    Clue.RATING: "CC",
    Clue.PACK: "Pack",
    Clue.VERSION: "Version",
    Clue.CHARTER: "Charter",
    Clue.SIDE: "Side",
    Clue.BPM: "BPM",
    Clue.NOTE: "Notes",
}

_FILLERS: tuple[Clue, ...] = (
    Clue.ARTIST,
    Clue.CHARTER,
    Clue.SIDE,
    Clue.BPM,
    Clue.NOTE,
)


def in_render_order(columns: Sequence[str]) -> list[Clue]:
    """Stored membership, sorted into the canonical render sequence.

    Names that are no longer clues are dropped rather than raised on: membership
    is persisted per puzzle, so retiring a column would otherwise brick every
    board already rolled with it.
    """
    present = {Clue(name) for name in columns if name in Clue.__members__.values()}
    return [clue for clue in CANONICAL_ORDER if clue in present]


def select_columns(
    pool: Sequence[ChartFacts],
    answer: ChartFacts,
    *,
    max_columns: int = MAX_COLUMNS,
    rng: random.Random | None = None,
) -> list[Clue]:
    """Roll a column set this pool and this answer can actually support."""
    # A column that does not vary across the pool carries zero information and is
    # dropped -- which is how an err puzzle loses level and rating without
    # special-casing, both being -1 on all seven charts.
    rng = rng or random.Random()
    eligible = {clue for clue in _FILLERS if _informative(pool, answer, clue)}
    chosen = [Clue.TITLE]

    for group in REDUNDANT_GROUPS:
        usable = [clue for clue in group if _informative(pool, answer, clue)]
        if usable:
            chosen.append(rng.choice(usable))

    fillers = list(eligible)
    rng.shuffle(fillers)
    chosen.extend(fillers[: max(0, max_columns - len(chosen))])
    return in_render_order([str(clue) for clue in chosen])


def _informative(pool: Sequence[ChartFacts], answer: ChartFacts, clue: Clue) -> bool:
    """Whether this column varies across the pool and the answer has a value."""
    # A *guess* missing the value is fine -- feedback.evaluate renders that one
    # row's cell ⬛ and the column keeps working for everyone else. An *answer*
    # missing it makes every row ⬛, a dead column wearing a live one's clothes.
    # Judging the pool on "unknown anywhere" instead cost charter on every tier
    # and artist on all but byd, over a handful of charts with no links.
    if _value(answer, clue) is None:
        return False
    values = {_value(fact, clue) for fact in pool}
    return len(values - {None}) > 1


def _value(fact: ChartFacts, clue: Clue):
    """The comparable value, or ``None`` when it is a sentinel/unknown."""
    match clue:
        case Clue.ARTIST:
            return fact.artists or None
        case Clue.CHARTER:
            return fact.charters or None
        case Clue.LEVEL:
            return fact.level if fact.level > 0 else None
        case Clue.RATING:
            return fact.rating if fact.rating > 0 else None
        case Clue.PACK:
            return fact.pack_id
        case Clue.VERSION:
            return fact.version or None
        case Clue.SIDE:
            return fact.side
        case Clue.BPM:
            return fact.bpm if fact.bpm > 0 else None
        case Clue.NOTE:
            return fact.note if fact.note > 0 else None
        case _:
            return fact.song_id
