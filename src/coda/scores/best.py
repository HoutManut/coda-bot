"""Personal bests read back out of ``play_scores``.

Only what was observed exists: the wire exposes one play at a time, so a chart
the account played before it registered has no row here and no way to get one.
"No score" therefore means "the bot never saw one", never "you never played it".

Best is by score alone, which is right for DISPLAY and wrong for anything that
feeds the rating calc. Since 7.0 a clear adds a flat bonus, so play rating is no
longer monotone in score across rows: a lower-scoring real clear can outrate a
higher-scoring fail on the same chart. :mod:`coda.scores.potential` therefore
picks a chart's entry by resolved rating over every stored row, and must never
be handed this query's answer instead
(``d-clear-bonus-impossible-friend-path``).
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from coda.db.models import PlayScore


async def best_play(
    db: AsyncSession, account_id: int, difficulty_id: int
) -> PlayScore | None:
    """The account's best stored play on one chart.

    Ties break to the earliest play: that is the run that set the record, and
    the later ones only matched it.
    """
    return await db.scalar(
        select(PlayScore)
        .where(
            PlayScore.arcaea_account_id == account_id,
            PlayScore.song_difficulty_id == difficulty_id,
        )
        .order_by(PlayScore.score.desc(), PlayScore.time_played.asc())
        .limit(1)
    )


async def scored_charts(
    db: AsyncSession, account_id: int, difficulty_ids: Sequence[int]
) -> set[int]:
    """Which of those charts the account has any stored play on."""
    if not difficulty_ids:
        return set()
    rows = await db.execute(
        select(PlayScore.song_difficulty_id)
        .where(
            PlayScore.arcaea_account_id == account_id,
            PlayScore.song_difficulty_id.in_(difficulty_ids),
        )
        .distinct()
    )
    return set(rows.scalars())
