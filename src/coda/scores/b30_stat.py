"""The b30-impact line appended under a ``/recent`` embed.

Not part of ``embed.py``: that renders a play from its rows alone and is shared
with the live-update poster, while this needs DB round-trips of its own.

Two different numbers, deliberately. A play inside the b30 reports the b30
itself -- the sum divided by 30, a PTT-scale average, the same "always divide by
the full pool size" convention potential uses. A play outside it reports the
30th-place PLAY RATING instead: the bar that play had to clear, which the
average cannot tell you.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from coda.db.models import PlayScore, SongDifficulty
from coda.scores.b30 import B30Result, B30Service
from coda.utils.scoring import format_rating

_COUNTED = 30

# How far down the ranking each mode still has something to say. None is no
# floor at all -- "#200 best" is a real answer to where a play stands.
_MODE_REACH: dict[str, int | None] = {
    "b30": _COUNTED,
    "b40": 40,
    "b100": 100,
    "always": None,
}

# Past this rank the 30th-place rating stops being a target and is just a
# number, so the line reports position alone. Only `always` ever reaches here.
_TARGET_DEPTH = 50

# True whichever of the three causes applies, so the line never claims a
# specific one it cannot tell apart.
_UNAVAILABLE = "-# b30 stat unavailable -- hidden rating or tracking off."


async def b30_stat_line(
    db: AsyncSession,
    service: B30Service,
    play: PlayScore,
    chart: SongDifficulty | None,
    *,
    mode: str,
    account_id: int,
    tracking_enabled: bool,
    rating_visible: bool,
) -> str | None:
    """What this play did to the account's b30, or None to render nothing.

    ``rating_visible`` must be False whenever the account's current PTT could
    not be freshly confirmed as visible -- "unknown" is treated as hidden.
    """
    if mode == "never":
        return None
    if chart is None or chart.rating <= 0:
        return None
    if play.id is None or not tracking_enabled or not rating_visible:
        return None

    # limit=30 is enough for every line here: the b30 sum is independent of it,
    # and the deep rank rides along on `requested_rank` rather than the entries.
    result = await service.compute(
        db, account_id, limit=_COUNTED, rank_for_difficulty_id=chart.id
    )
    rank = result.requested_rank
    reach = _MODE_REACH[mode]
    if rank is None or (reach is not None and rank > reach):
        return None
    detail = (
        await _b30_detail(db, service, account_id, play.id, result)
        if rank <= _COUNTED
        else _target_detail(result, rank)
    )
    return f"#**{rank}** best" + (f" · {detail}" if detail else "")


async def _b30_detail(
    db: AsyncSession,
    service: B30Service,
    account_id: int,
    play_id: int,
    after: B30Result,
) -> str:
    """b30 before and after, recomputed exactly rather than approximated.

    The second pass drops this one play, which is the only way to get the
    "before" right when it improved a chart that was already in the top 30.
    """
    before = await service.compute(
        db, account_id, limit=_COUNTED, exclude_score_id=play_id
    )
    before_average = before.b30_sum / _COUNTED
    after_average = after.b30_sum / _COUNTED
    if before_average == after_average:
        return f"B30: **{format_rating(after_average)}**"
    delta = after_average - before_average
    return (
        f"B30: {format_rating(before_average)} → "
        f"**{format_rating(after_average)}** (+{format_rating(delta)})"
    )


def _target_detail(result: B30Result, rank: int) -> str:
    """The 30th-place bar, while it is still a bar rather than trivia.

    Only reachable when ``rank`` exceeds 30, which guarantees a 30th entry
    exists -- no short-pool case to handle.
    """
    if rank > _TARGET_DEPTH:
        return ""
    thirtieth = result.entries[_COUNTED - 1].play_rating
    return f"30th: **{format_rating(thirtieth)}**"
