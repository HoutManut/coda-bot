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
from coda.catalog.spoilers import chart_spoilered
from coda.db.models import (
    ArcaeaAccount,
    PlayerLink,
    PlayScore,
    Song,
    SongDifficulty,
)
from coda.arcaea.dto.score import ScoreResult
from coda.db.session import async_session
from coda.players.live import LiveUpdateService
from coda.scores import PotentialService, ObservationCache, PollCoordinator
from coda.scores.potential_stat import StatMode, potential_stat_line
from coda.scores.embed import PlayerIdentity, append_line, score_embed
from coda.scores.routing import poll_key_for
from coda.scores.service import row_values
from coda.scores.suppression import PostSuppressor
from coda.utils.container import as_container
from coda.settings import ConfigService
from coda.settings.zone import effective_zone

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()

_NOT_REGISTERED = "You're not registered yet. Run `/register` first."
_NOT_POLLED = (
    "That account isn't being tracked right now. Run `/register` again to restart it."
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
        settings: ConfigService,
        potential: PotentialService,
        suppressor: PostSuppressor,
    ) -> None:
        # Both checks run before the defer, and both are single indexed reads.
        # A deferred response fixes its flags at defer time, so anything sent
        # after it fills that placeholder and loses ``ephemeral``.
        async with async_session() as db:
            account = await _account_of(db, int(ctx.user.id))
            if account is None:
                await ctx.respond(_NOT_REGISTERED, ephemeral=True)
                return
            key = await poll_key_for(db, account)
            account_id = account.id
            arc_user_id = account.arc_user_id
            tracking_enabled = account.tracking_enabled

        if key is None:
            await ctx.respond(_NOT_POLLED, ephemeral=True)
            return

        await ctx.defer()

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
            player_name = ctx.user.display_name or None
            zone = await effective_zone(
                db,
                settings,
                guild_id=int(ctx.guild_id) if ctx.guild_id is not None else None,
                channel_id=int(ctx.channel_id),
                user_id=int(ctx.user.id),
            )
            embed, _ = score_embed(
                row,
                chart,
                song,
                locale=ctx.interaction.locale,
                night=is_night(zone),
                player=None if player_name is None else PlayerIdentity(
                    name=player_name,
                    avatar_url=str(ctx.user.display_avatar_url),
                ),
                untracked=not tracking_enabled,
            )
            append_line(
                embed,
                await potential_stat_line(
                    db,
                    potential,
                    row,
                    chart,
                    mode=await _stat_mode(db, settings, ctx),
                    account=account,
                    observations=observations,
                ),
            )
            await _mark_shown(db, ctx, suppressor, row)
        # No ephemeral option to flip, and none could be added: the defer above
        # fixes the flags before ``request_refresh`` has said which play this
        # is. Making it ephemeral would also break post suppression -- the
        # channel's live post is marked shown by a reply nobody there saw. So
        # the blur is the whole protection here.
        spoiler = chart is not None and song is not None and chart_spoilered(song, chart)
        await ctx.respond(components=[as_container(embed, [], spoiler=spoiler)])


async def _mark_shown(
    db: AsyncSession,
    ctx: lightbulb.Context,
    suppressor: PostSuppressor,
    row: PlayScore,
) -> None:
    """Tell the poster this surface has already displayed the play.

    This command *causes* the duplicate it prevents: ``request_refresh`` drives
    a real poll cycle, which ingests the play, which is exactly what the poster
    consumes. Marked only when the reply is going to the very place the user's
    live updates go -- a different channel has shown nothing and still deserves
    its post, and the DM stays the user's archive when this ran in a channel.

    A play rendered from the observation cache alone (tracking off) has no row
    id, and nothing will ever post it, so there is nothing to mark.
    """
    if row.id is None:
        return
    enabled, channel_id = await LiveUpdateService().resolve_destination(
        db, int(ctx.user.id)
    )
    if not enabled:
        return
    if channel_id is not None:
        if channel_id == int(ctx.channel_id):
            suppressor.mark(("channel", channel_id), row.id)
        return
    if ctx.guild_id is None:
        suppressor.mark(("dm", int(ctx.user.id)), row.id)


async def _stat_mode(
    db: AsyncSession, settings: ConfigService, ctx: lightbulb.Context
) -> StatMode:
    """The caller's resolved ``recent_b50_stat`` preference."""
    return await settings.resolve(
        db,
        "recent_b50_stat",
        guild_id=int(ctx.guild_id) if ctx.guild_id is not None else None,
        channel_id=int(ctx.channel_id),
        user_id=int(ctx.user.id),
        is_dm=ctx.guild_id is None,
    )


async def _account_of(db: AsyncSession, discord_id: int) -> ArcaeaAccount | None:
    """The one account this Discord user links, or None."""
    row = await db.execute(
        select(ArcaeaAccount)
        .join(PlayerLink, PlayerLink.arcaea_account_id == ArcaeaAccount.id)
        .where(PlayerLink.discord_id == discord_id)
    )
    return row.scalar_one_or_none()


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
