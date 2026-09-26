"""Display strings for difficulty classes and charts. Shared by every embed.

``byd_2`` is an app-defined slot for a second Beyond chart, so it displays as
plain "Beyond" -- the distinction is ours, not the game's, and a user reading a
score has no use for it.

Some Beyond charts carry lowiro's "Inscribed" alt appearance
(``SongDifficulty.alt``) -- not a class, just a different name/color for the
same chart. :func:`class_full`/:func:`class_short` resolve it; the raw
``CLASS_FULL``/``CLASS_SHORT`` dicts stay for call sites that only have a bare
class (no chart row) to work with.
"""

from __future__ import annotations

from coda.db.enums import DifficultyClass
from coda.db.models import SongDifficulty
from coda.utils.encoding import decode_level, decode_rating
from coda.utils.scoring import (
    ASSUMED_MARK,
    ClearBasis,
    ClearStatus,
    calculate_play_rating,
    format_rating,
)

CLASS_FULL: dict[DifficultyClass, str] = {
    DifficultyClass.PST: "Past",
    DifficultyClass.PRS: "Present",
    DifficultyClass.FTR: "Future",
    DifficultyClass.BYD: "Beyond",
    DifficultyClass.BYD_2: "Beyond",
    DifficultyClass.ETR: "Eternal",
    DifficultyClass.ERR: "Error",
}

CLASS_SHORT: dict[DifficultyClass, str] = {
    DifficultyClass.PST: "PST",
    DifficultyClass.PRS: "PRS",
    DifficultyClass.FTR: "FTR",
    DifficultyClass.BYD: "BYD",
    DifficultyClass.BYD_2: "BYD",
    DifficultyClass.ETR: "ETR",
}

ALT_CLASS_FULL: dict[DifficultyClass, str] = {
    DifficultyClass.BYD: "Inscribed",
    DifficultyClass.BYD_2: "Inscribed",
}

ALT_CLASS_SHORT: dict[DifficultyClass, str] = {
    DifficultyClass.BYD: "INS",
    DifficultyClass.BYD_2: "INS",
}


def class_full(difficulty: DifficultyClass, alt: bool = False) -> str:
    """A difficulty class's full name, or its alt appearance's name when flagged."""
    if alt and difficulty in ALT_CLASS_FULL:
        return ALT_CLASS_FULL[difficulty]
    return CLASS_FULL[difficulty]


def class_short(difficulty: DifficultyClass, alt: bool = False) -> str:
    """A difficulty class's short label, or its alt appearance's when flagged."""
    if alt and difficulty in ALT_CLASS_SHORT:
        return ALT_CLASS_SHORT[difficulty]
    return CLASS_SHORT[difficulty]

# Deterministic display order (code index): byd=3, etr=4; err omitted.
CLASS_ORDER: tuple[DifficultyClass, ...] = (
    DifficultyClass.PST,
    DifficultyClass.PRS,
    DifficultyClass.FTR,
    DifficultyClass.ETR,
    DifficultyClass.BYD,
    DifficultyClass.BYD_2,
)

# Slash-command option value -> class. ``byd_2`` and ``err`` are not offered.
CLASS_OPTIONS: dict[str, DifficultyClass] = {
    "pst": DifficultyClass.PST,
    "prs": DifficultyClass.PRS,
    "ftr": DifficultyClass.FTR,
    "etr": DifficultyClass.ETR,
    "byd": DifficultyClass.BYD,
}


def sorted_charts(charts: list[SongDifficulty]) -> list[SongDifficulty]:
    """Charts in :data:`CLASS_ORDER`; anything unlisted (err) sorts last."""
    order = {cls: i for i, cls in enumerate(CLASS_ORDER)}
    return sorted(charts, key=lambda c: order.get(c.difficulty, 99))


def format_cc(rating: int) -> str | None:
    """Human CC, or ``None`` when unknown (TBA/N-A). Delisted (``< -1``) recovers
    the historical value from the negated sentinel."""
    if rating in (0, -1):
        return None
    if rating < -1:
        return f"{abs(rating) / 10:.1f}"
    return f"{rating / 10:.1f}"


def chart_rating_line(
    score: int, chart: SongDifficulty, clear: ClearStatus | None = None
) -> str:
    """Difficulty class, then CC and the rating that score earns on it.

    ``clear`` is None for a HYPOTHETICAL score (``/calc``), which has no play to
    read a clear status from -- both ratings are shown, since as of 7.0 the score
    alone no longer determines one. A real play passes its resolved status and
    gets the single number, marked when that status was inferred rather than read
    off the wire.

    A chart can have no CC (``<= 0``: TBA, or a delisted chart's negated
    sentinel). Then the line falls back to the level -- always known -- and drops
    the rating: one computed from a sentinel is a plausible-looking wrong number.
    """
    label = class_full(chart.difficulty, chart.alt)
    cc = decode_rating(chart.rating)
    if cc <= 0:
        return f"{label} {decode_level(chart.level)} (Unknown CC)"
    return f"{label} {cc:.1f} → {rating_text(score, cc, clear)}"


def rating_text(score: int, cc: float, clear: ClearStatus | None) -> str:
    """The rating a score earns on a KNOWN cc, disclosing how clear status was got."""
    if clear is None:
        failed = calculate_play_rating(score, cc, cleared=False)
        cleared = calculate_play_rating(score, cc, cleared=True)
        return f"**{format_rating(failed)}** / **{format_rating(cleared)}** (cleared)"
    rating = calculate_play_rating(score, cc, cleared=clear.cleared)
    mark = ASSUMED_MARK if clear.basis is ClearBasis.ASSUMED else ""
    return f"**{mark}{format_rating(rating)}**"
