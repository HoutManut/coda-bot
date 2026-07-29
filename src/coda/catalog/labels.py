"""Display strings for difficulty classes and charts. Shared by every embed.

``byd_2`` is an app-defined slot for a second Beyond chart, so it displays as
plain "Beyond" -- the distinction is ours, not the game's, and a user reading a
score has no use for it.
"""

from __future__ import annotations

from coda.db.enums import DifficultyClass
from coda.db.models import SongDifficulty
from coda.utils.encoding import decode_level, decode_rating
from coda.utils.scoring import calculate_play_rating, format_rating

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
    DifficultyClass.BYD_2: "BYD 2",
    DifficultyClass.ETR: "ETR",
}

# Deterministic display order (code index): byd=3, etr=4; err omitted.
CLASS_ORDER: tuple[DifficultyClass, ...] = (
    DifficultyClass.PST,
    DifficultyClass.PRS,
    DifficultyClass.FTR,
    DifficultyClass.BYD,
    DifficultyClass.BYD_2,
    DifficultyClass.ETR,
)

# Slash-command option value -> class. ``byd_2`` and ``err`` are not offered.
CLASS_OPTIONS: dict[str, DifficultyClass] = {
    "pst": DifficultyClass.PST,
    "prs": DifficultyClass.PRS,
    "ftr": DifficultyClass.FTR,
    "byd": DifficultyClass.BYD,
    "etr": DifficultyClass.ETR,
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


def chart_rating_line(score: int, chart: SongDifficulty) -> str:
    """Difficulty class, then CC and the rating that score earns on it.

    A chart can have no CC (``<= 0``: TBA, or a delisted chart's negated
    sentinel). Then the line falls back to the level -- always known -- and drops
    the rating: one computed from a sentinel is a plausible-looking wrong number.
    """
    label = CLASS_FULL[chart.difficulty]
    cc = decode_rating(chart.rating)
    if cc <= 0:
        return f"{label} {decode_level(chart.level)} (Unknown CC)"
    rating = calculate_play_rating(score, cc)
    return f"{label} {cc:.1f} → **{format_rating(rating)}**"
