"""/recent -- refresh the caller's account, then show their latest play.

The command never touches lowiro itself: it asks the poller for a targeted cycle
(:meth:`PollCoordinator.request_refresh`) and then reads back what that cycle
produced, which keeps exactly one fetcher against the shared rate limiter.

Own path first when the user has credentials -- one request instead of a whole
bot account's friend list, and it is the only path that carries pure/far/lost.

Two sources are read back, and the newer play wins: the stored row, and the
poller's :class:`ObservationCache`. They agree for a tracked account. For one
with tracking off nothing was stored, so the cache is the only place the play
the wire just returned exists -- it is rendered from a detached ``PlayScore``
that is never added to the session.
"""

from __future__ import annotations

import logging

import lightbulb
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from coda.catalog.jackets import is_night
from coda.db.models import (
    ArcaeaAccount,
    PlayerCredential,
    PlayerLink,
    PlayScore,
    Song,
    SongDifficulty,
)
from coda.arcaea.dto.score import ScoreResult
from coda.db.session import async_session
from coda.scores import ObservationCache, PollCoordinator
from coda.scores.embed import score_embed
from coda.scores.keys import OWN, PollKey
from coda.scores.service import row_values
from coda.sessions.pool import SessionPool

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()

_NOT_REGISTERED = "You're not registered yet -- run `/register` first."
_NOT_POLLED = (
    "That account isn't being tracked right now. Run `/register` again to re-link it."
)
_NO_PLAYS = (
    "No plays recorded yet, play a chart and try again."
)

# One play, plus its chart and song when the chart resolved.
type _Play = tuple[PlayScore, SongDifficulty | None, Song | None]


@loader.command
class Recent(
    lightbulb.SlashCommand,
    name="recent",
    description="Show your most recent play",
):
    @lightbulb.invoke
    async def invoke(
        self,
        ctx: lightbulb.Context,
        coordinator: PollCoordinator,
        observations: ObservationCache,
    ) -> None:
        # A refresh waits on a poll cycle, well past the 3s interaction budget.
        await ctx.defer()

        async with async_session() as db:
            account = await _account_of(db, int(ctx.user.id))
            if account is None:
                await ctx.respond(_NOT_REGISTERED, ephemeral=True)
                return
            key = await _poll_key(db, account)
            account_id = account.id
            arc_user_id = account.arc_user_id

        if key is None:
            await ctx.respond(_NOT_POLLED, ephemeral=True)
            return

        # Outside any DB session: a cycle can run for tens of seconds and must
        # not pin a Postgres connection while it does.
        await coordinator.request_refresh(key)

        async with async_session() as db:
            play = await _newest_play(
                db, account_id, observations.latest(arc_user_id)
            )
            if play is None:
                await ctx.respond(_NO_PLAYS, ephemeral=True)
                return
            row, chart, song = play
            embed, _ = score_embed(
                row,
                chart,
                song,
                locale=ctx.interaction.locale,
                night=is_night(int(ctx.user.id)),
            )
        await ctx.respond(embed=embed)


async def _account_of(db: AsyncSession, discord_id: int) -> ArcaeaAccount | None:
    """The one account this Discord user links, or None."""
    row = await db.execute(
        select(ArcaeaAccount)
        .join(PlayerLink, PlayerLink.arcaea_account_id == ArcaeaAccount.id)
        .where(PlayerLink.discord_id == discord_id)
    )
    return row.scalar_one_or_none()


async def _poll_key(db: AsyncSession, account: ArcaeaAccount) -> PollKey | None:
    """Which path to refresh this account on -- own if it can, else friend.

    None means neither is available (strayed, or the slot was released), which
    is a plain error: there is nothing to refresh and nothing new to show.
    """
    if not account.is_active:
        return None
    credential = await db.scalar(
        select(PlayerCredential.id).where(
            PlayerCredential.arcaea_account_id == account.id,
            PlayerCredential.is_valid.is_(True),
        )
    )
    if credential is not None:
        return (OWN, account.id)
    return SessionPool(db).poll_key(account)


async def _newest_play(
    db: AsyncSession, account_id: int, observed: ScoreResult | None
) -> _Play | None:
    """The newer of the stored play and the freshly-observed one.

    Comparing on ``time_played`` rather than preferring one source: it is
    server-assigned and immutable, so it orders the two truthfully. A tracked
    account's cache entry and stored row are the same play and either branch
    renders the same thing.
    """
    stored = await _latest_play(db, account_id)
    if observed is None:
        return stored
    if stored is not None and stored[0].time_played >= observed.time_played:
        return stored
    return await _observed_play(db, account_id, observed)


async def _observed_play(
    db: AsyncSession, account_id: int, observed: ScoreResult
) -> _Play:
    """Render-ready rows for a play that was seen but never stored.

    The ``PlayScore`` is built from the same column mapping ingest uses and is
    deliberately NOT added to the session -- it is a value object here, and
    persisting it is exactly what the account opted out of.
    """
    row = PlayScore(**row_values(observed, account_id))
    if observed.difficulty_id is None:
        return row, None, None
    chart = (
        await db.execute(
            select(SongDifficulty, Song)
            .outerjoin(Song, Song.song_id == SongDifficulty.song_id)
            .where(SongDifficulty.id == observed.difficulty_id)
        )
    ).first()
    return (row, None, None) if chart is None else (row, chart[0], chart[1])


async def _latest_play(db: AsyncSession, account_id: int) -> _Play | None:
    """The newest stored play and its chart, if the chart resolved.

    An outer join, not two queries: an unresolved chart is routine and must
    still render, just without the catalog half.
    """
    row = (
        await db.execute(
            select(PlayScore, SongDifficulty, Song)
            .outerjoin(
                SongDifficulty, SongDifficulty.id == PlayScore.song_difficulty_id
            )
            .outerjoin(Song, Song.song_id == SongDifficulty.song_id)
            .where(PlayScore.arcaea_account_id == account_id)
            .order_by(PlayScore.time_played.desc())
            .limit(1)
        )
    ).first()
    return None if row is None else (row[0], row[1], row[2])
