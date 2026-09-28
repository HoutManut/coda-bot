"""The potential lines appended under a score embed.

Not part of ``embed.py``: that renders a play from its rows alone and is shared
with the live-update poster, while these need DB round-trips of their own.
"""

from __future__ import annotations

from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from coda.db.models import ArcaeaAccount, PlayScore, SongDifficulty
from coda.scores.observations import ObservationCache
from coda.scores.potential import POOL, PotentialResult, PotentialService
from coda.utils.scoring import ASSUMED_MARK, format_rating

# The reach settings (`recent_b50_stat`, `score_rank_depth`) resolve to. Their
# registry entries list these same values -- an unlisted one KeyErrors below.
type StatMode = Literal["never", "b50", "b60", "b100", "always"]

# How far down the ranking each mode still has something to say. None is no
# floor at all -- "#200 best" is a real answer to where a play stands.
_MODE_REACH: dict[StatMode, int | None] = {
    "b50": POOL,
    "b60": 60,
    "b100": 100,
    "always": None,
}

# Past this rank the 50th-place rating stops being a target and is just a
# number, so the line reports position alone. Only `always` ever reaches here.
_TARGET_DEPTH = 100

async def potential_stat_line(
    db: AsyncSession,
    service: PotentialService,
    play: PlayScore,
    chart: SongDifficulty | None,
    *,
    mode: StatMode,
    account: ArcaeaAccount,
    observations: ObservationCache,
) -> str | None:
    """What this play did to the account's potential, or None to render nothing."""
    if mode == "never":
        return None
    if chart is None or chart.rating <= 0:
        return None
    if play.id is None or not account.tracking_enabled:
        return None
    if not _rating_visible(observations, account.arc_user_id):
        return None

    # limit=POOL is enough for every line here: the sums are independent of it,
    # and the deep rank rides along on `requested_rank` rather than the entries.
    result = await service.compute(
        db, account.id, limit=POOL, rank_for_difficulty_id=chart.id
    )
    # A play that is not its chart's best moved nothing: the rank and PTT both
    # belong to the older play, and printing them here would credit this one.
    if result.requested_play_score_id != play.id:
        return None
    rank = result.requested_rank
    reach = _MODE_REACH[mode]
    if rank is None or (reach is not None and rank > reach):
        return None
    detail = (
        await _potential_detail(db, service, account.id, play.id, result)
        if rank <= POOL
        else _target_detail(result, rank)
    )
    return f"#**{rank}** best" + (f" · {detail}" if detail else "")


def _rating_visible(observations: ObservationCache, arc_user_id: int) -> bool:
    """Whether the account's PTT was freshly seen as public.

    Read live every call, never remembered: a player who hides their PTT must
    stop seeing this line on the very next render. "Unknown" counts as hidden.
    """
    rating, observed = observations.latest_rating(arc_user_id)
    return observed and rating is not None


async def rank_line(
    db: AsyncSession,
    service: PotentialService,
    chart: SongDifficulty,
    *,
    mode: StatMode,
    account_id: int,
) -> str | None:
    """Where this chart's best sits in the account's ranking, or None.

    Needs none of the PTT-visibility gating :func:`potential_stat_line` does: a
    position is not a rating, and the only rating its embed shows is the one
    anyone can compute from the score and CC already printed there.
    """
    if mode == "never" or chart.rating <= 0:
        return None

    # limit=1: only `requested_rank` is read, and that comes off the full sorted
    # pass rather than the returned entries.
    result = await service.compute(
        db, account_id, limit=1, rank_for_difficulty_id=chart.id
    )
    rank = result.requested_rank
    reach = _MODE_REACH[mode]
    if rank is None or (reach is not None and rank > reach):
        return None
    return f"#**{rank}** best"


async def _potential_detail(
    db: AsyncSession,
    service: PotentialService,
    account_id: int,
    play_id: int,
    after: PotentialResult,
) -> str:
    """Potential before and after, recomputed exactly rather than approximated.

    The second pass drops this one play, which is the only way to get the
    "before" right when it improved a chart that was already in the pool.
    """
    before = await service.compute(
        db, account_id, limit=POOL, exclude_score_id=play_id
    )
    if before.potential == after.potential:
        return "PTT: **KEEP**"
    mark = ASSUMED_MARK if after.assumed_count else ""
    delta = after.potential - before.potential
    return (
        f"PTT: {format_rating(before.potential)} → "
        f"**{mark}{format_rating(after.potential)}** (+{format_rating(delta)})"
    )


def _target_detail(result: PotentialResult, rank: int) -> str:
    """The 50th-place bar, while it is still a bar rather than trivia.

    Only reachable when ``rank`` exceeds the pool, which guarantees a 50th entry
    exists -- no short-pool case to handle.
    """
    if rank > _TARGET_DEPTH:
        return ""
    last_counted = result.entries[POOL - 1].play_rating
    return f"50th: **{format_rating(last_counted)}**"
