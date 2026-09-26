"""Which accounts an open round makes hot. The module's one output to the poller.

A union across ALL open rounds, never per-round: the poller consumes a set of
keys and does not know what a tournament is. Hot is cheap on the friend path --
one request covers up to ten participants -- so nothing here rations it; the
global limiter still caps total throughput.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from coda.db.enums import RoundState
from coda.db.models import TournamentParticipant, TournamentRound
from coda.db.session import async_session
from coda.scores.keys import PollKey
from coda.scores.routing import poll_keys_for

LIVE = (RoundState.OPEN, RoundState.GRACE)


async def hot_accounts(db: AsyncSession) -> set[int]:
    """Every ``arcaea_account_id`` in a live round."""
    rows = await db.execute(
        select(TournamentParticipant.arcaea_account_id)
        .join(
            TournamentRound,
            TournamentRound.match_id == TournamentParticipant.match_id,
        )
        .where(TournamentRound.state.in_(LIVE))
        .distinct()
    )
    return set(rows.scalars())


async def hot_keys() -> set[PollKey]:
    """The poller's hot set. Opens its own session -- the poll loop calls this
    once a tick, outside any session of its own."""
    async with async_session() as db:
        return await poll_keys_for(db, await hot_accounts(db))
