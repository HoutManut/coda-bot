"""Turn a newly-stored play into a Discord message.

Input is play ids handed over by the poller after its commit -- never ORM rows:
the poller's session is short-lived by design and anything it returns is
detached moments later, so the poster opens its own.

The hand-off is deliberately non-blocking. A bounded queue with ``put_nowait``
means a wedged poster drops plays and logs; it can never stall the poll loop,
and the queue can only fill if the poster is already broken.

What actually posts is decided in ``filters.py``. This module is routing, order
and delivery: who is linked to the account, where each of them wants their
updates, one message per DESTINATION rather than per linked user, and a stagger
so a channel several players point at is not machine-gunned.
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from time import monotonic

import hikari
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from coda.catalog.jackets import is_night
from coda.db.models import ArcaeaAccount, PlayerLink, PlayScore, Song, SongDifficulty
from coda.db.session import async_session
from coda.players.live import LiveUpdateService
from coda.scores.observations import ObservationCache
from coda.scores.potential import PotentialService
from coda.scores.potential_stat import potential_stat_line
from coda.scores.filters import ChannelFloor, Filters, PlayFacts, evaluate
from coda.catalog.spoilers import chart_spoilered
from coda.scores.embed import PlayerIdentity, append_line, score_embed
from coda.scores.suppression import Destination, PostSuppressor
from coda.settings import ConfigService
from coda.settings.zone import effective_zone
from coda.utils.container import as_container
from coda.utils.dm import send_dm

logger = logging.getLogger(__name__)

# Play ids awaiting a post. Bounded: see the module docstring.
type PostQueue = asyncio.Queue[int]

QUEUE_MAXSIZE = 256

# Jittered pause before the first send of a batch. Costs nothing on a feed
# already minutes behind the wire, and it is what closes the /recent race
# without a second mechanism: the poster cannot send before /recent's own read
# has completed and marked the play.
INITIAL_DELAY = (3.0, 8.0)

# Minimum seconds between two sends to the SAME destination. Different
# destinations are never held up by each other.
SPACING = 5.0

_CHANNEL = "channel"
_DM = "dm"


def new_queue() -> PostQueue:
    return asyncio.Queue(maxsize=QUEUE_MAXSIZE)


def submit(posts: PostQueue | None, play_ids: list[int]) -> None:
    """Hand new plays to the poster. Never blocks, never raises."""
    if posts is None or not play_ids:
        return
    for play_id in play_ids:
        try:
            posts.put_nowait(play_id)
        except asyncio.QueueFull:
            logger.warning("post queue full; dropping play %s", play_id)


async def run(
    posts: PostQueue,
    app: hikari.RESTAware,
    suppressor: PostSuppressor,
    observations: ObservationCache,
) -> None:
    """Consume new plays forever and post each where its players asked.

    Plays arrive already ordered by ``time_played`` (``poller._store`` sorts
    before ingest). Planning stays IN this loop rather than moving into the
    per-send tasks: planning is several awaits deep, so two plays planned
    concurrently would reach a shared destination's lock in whichever order
    finished first. Planned in sequence, the send tasks are created in play
    order and take an uncontended lock without yielding, so the FIFO waiter
    queue preserves that order. Only the sends -- which sleep for the stagger --
    run concurrently, which is where the parallelism actually matters.
    """
    sender = _Sender(app, suppressor)
    pending: set[asyncio.Task[None]] = set()
    try:
        while True:
            batch = [await posts.get()]
            await asyncio.sleep(random.uniform(*INITIAL_DELAY))
            batch.extend(_drain(posts))
            for play_id in batch:
                for delivery in await _plan_play(play_id, app, observations):
                    task = asyncio.create_task(_send(sender, delivery))
                    pending.add(task)
                    task.add_done_callback(pending.discard)
    finally:
        for task in pending:
            task.cancel()


def _drain(posts: PostQueue) -> list[int]:
    """Everything already queued, in order. The batch its INITIAL_DELAY covered."""
    drained: list[int] = []
    while True:
        try:
            drained.append(posts.get_nowait())
        except asyncio.QueueEmpty:
            return drained


@dataclass(frozen=True)
class _Delivery:
    """One rendered message and where it goes."""

    destination: Destination
    play_score_id: int
    embed: hikari.Embed
    # A live post has no viewer to make it ephemeral for, so a spoilered chart
    # still posts -- blurred, and revealed by whoever chooses to.
    spoiler: bool = False


async def _plan_play(
    play_id: int, app: hikari.RESTAware, observations: ObservationCache
) -> list[_Delivery]:
    """Everything one play should send. One bad play never stops the loop."""
    try:
        async with async_session() as db:
            return await _plan(db, app, observations, play_id)
    except Exception:
        logger.exception("live: planning play %s failed", play_id)
        return []


async def _send(sender: _Sender, delivery: _Delivery) -> None:
    """Deliver one message. Sends run outside any DB session: the stagger can
    sleep for seconds and must not pin a Postgres connection while it does."""
    try:
        await sender.send(delivery)
    except Exception:
        logger.exception(
            "live: sending play %s to %s failed",
            delivery.play_score_id,
            delivery.destination,
        )


async def _plan(
    db: AsyncSession,
    app: hikari.RESTAware,
    observations: ObservationCache,
    play_id: int,
) -> list[_Delivery]:
    """Every message this play earns, deduplicated by destination.

    Filters are evaluated per linked Discord user -- their preferences are their
    own -- but the messages are collected onto the UNION of the destinations
    that passed. Two users linking one account and both pointing at the same
    channel put one message in it, not two.
    """
    loaded = await _load_play(db, play_id)
    if loaded is None:
        logger.debug("live: play %s vanished before posting", play_id)
        return []
    row, chart, song = loaded

    links = await _links(db, row.arcaea_account_id)
    if not links:
        return []

    live = LiveUpdateService()
    potential = PotentialService()
    facts = PlayFacts(db, potential, row, chart)
    passed: dict[Destination, ChannelFloor | None] = {}
    for discord_id, _ in links:
        enabled, channel_id = await live.resolve_destination(db, discord_id)
        if not enabled:
            continue
        pref = await live.get_pref(db, discord_id)
        filters = Filters.of(pref) if pref is not None else _DEFAULT_FILTERS
        floor = (
            None if channel_id is None else await live.floor_for(db, channel_id)
        )
        if not await evaluate(row, chart, filters, floor, facts):
            continue
        destination: Destination = (
            (_DM, discord_id) if channel_id is None else (_CHANNEL, channel_id)
        )
        passed.setdefault(destination, floor)

    if not passed:
        return []

    player = await _identity(db, app, row.arcaea_account_id, links)
    impact = await _impact_line(db, potential, observations, row, chart, links)
    spoiler = chart is not None and song is not None and chart_spoilered(song, chart)
    return [
        _Delivery(
            destination=destination,
            play_score_id=row.id,
            embed=await _render(
                db, row, chart, song, destination, floor, player, impact
            ),
            spoiler=spoiler,
        )
        for destination, floor in passed.items()
    ]


# A user who enabled updates before filters existed, or whose pref row somehow
# went missing: personal bests, which is the same default the column carries.
_DEFAULT_FILTERS = Filters(
    post_all=False,
    post_pb=True,
    post_pm=False,
    post_fr=False,
    best_of=None,
    min_grade=None,
    min_level=None,
)


async def _render(
    db: AsyncSession,
    row: PlayScore,
    chart: SongDifficulty | None,
    song: Song | None,
    destination: Destination,
    floor: ChannelFloor | None,
    player: PlayerIdentity | None,
    impact: str | None,
) -> hikari.Embed:
    """The embed for one destination, on that destination's own clock.

    English, alone among the render paths: ``score_embed`` wants a viewer's
    locale, every other caller reads one off ``interaction.locale``, and a post
    nobody asked for has no interaction to read. A channel post has no single
    viewer either. Remembering a user's locale from their last interaction would
    serve the DM destination, and is worth building the day one exists.
    """
    kind, target = destination
    is_dm = kind == _DM
    settings = ConfigService()
    guild_id = None if floor is None else floor.guild_id
    channel_id = 0 if is_dm else target
    user_id = target if is_dm else 0
    zone = await effective_zone(
        db, settings, guild_id=guild_id, channel_id=channel_id, user_id=user_id
    )
    embed, _ = score_embed(
        row,
        chart,
        song,
        locale="en",
        night=is_night(zone),
        player=player,
        live=True,
    )
    append_line(embed, impact)
    return embed


async def _impact_line(
    db: AsyncSession,
    potential: PotentialService,
    observations: ObservationCache,
    row: PlayScore,
    chart: SongDifficulty | None,
    links: list[tuple[int, bool]],
) -> str | None:
    """The /recent potential line, on the OWNER's ``recent_b50_stat``.

    Once per play, not per destination: it is a fact about the account, and the
    owner is the one whose PTT it discloses -- another linked user's preference
    must not publish it. No owner link falls back to the bot-wide value.
    """
    account = await db.get(ArcaeaAccount, row.arcaea_account_id)
    if account is None:
        return None
    mode = await ConfigService().resolve(
        db,
        "recent_b50_stat",
        guild_id=None,
        channel_id=0,
        user_id=_owner_of(links) or 0,
        is_dm=True,
    )
    return await potential_stat_line(
        db, potential, row, chart, mode=mode, account=account, observations=observations
    )


def _owner_of(links: list[tuple[int, bool]]) -> int | None:
    """The owning Discord user among an account's links, if one exists."""
    return next((discord_id for discord_id, owner in links if owner), None)


async def _load_play(
    db: AsyncSession, play_id: int
) -> tuple[PlayScore, SongDifficulty | None, Song | None] | None:
    """The stored row plus its chart and song, if the chart resolved."""
    found = (
        await db.execute(
            select(PlayScore, SongDifficulty, Song)
            .outerjoin(
                SongDifficulty, SongDifficulty.id == PlayScore.song_difficulty_id
            )
            .outerjoin(Song, Song.song_id == SongDifficulty.song_id)
            .where(PlayScore.id == play_id)
        )
    ).first()
    return None if found is None else (found[0], found[1], found[2])


async def _links(db: AsyncSession, account_id: int) -> list[tuple[int, bool]]:
    """Every Discord user linked to this account, as ``(discord_id, is_owner)``."""
    rows = await db.execute(
        select(PlayerLink.discord_id, PlayerLink.is_owner).where(
            PlayerLink.arcaea_account_id == account_id
        )
    )
    return [(discord_id, is_owner) for discord_id, is_owner in rows]


async def _identity(
    db: AsyncSession,
    app: hikari.RESTAware,
    account_id: int,
    links: list[tuple[int, bool]],
) -> PlayerIdentity | None:
    """Who to credit the play to, degrading rather than failing.

    The OWNER link, not "the recipient": an account can carry several links, so
    the recipient is not a stable answer and the same play could show two
    different faces in two channels. ``is_owner`` is unique per account and is
    already how ``notify.py`` picks who speaks for one.

    Falls back to the Arcaea in-game name, then to no author line at all. Never
    to the friend code -- that is how anyone adds the player in-game, and
    publishing it to a channel is a disclosure nobody consented to by turning
    live updates on.
    """
    owner_id = _owner_of(links)
    if owner_id is not None:
        identity = await _discord_identity(app, owner_id)
        if identity is not None:
            return identity

    display_name = await db.scalar(
        select(ArcaeaAccount.display_name).where(ArcaeaAccount.id == account_id)
    )
    return None if not display_name else PlayerIdentity(name=display_name)


async def _discord_identity(
    app: hikari.RESTAware, discord_id: int
) -> PlayerIdentity | None:
    """A Discord user's global name and avatar. None if they cannot be fetched.

    Guild nicknames and per-guild avatars are deliberately not used: they need a
    member fetch per destination, and one identity everywhere keeps the feed
    consistent for anyone following the same player in two places.
    """
    user = None
    if isinstance(app, hikari.CacheAware):
        user = app.cache.get_user(discord_id)
    if user is None:
        try:
            user = await app.rest.fetch_user(discord_id)
        except hikari.HikariError:
            logger.info("live: could not fetch Discord user %s", discord_id)
            return None
    return PlayerIdentity(
        name=user.global_name or user.username,
        avatar_url=str(user.display_avatar_url),
    )


class _Sender:
    """Delivers messages, spacing out repeats to the same destination.

    One lock per destination rather than one queue per destination:
    ``asyncio.Lock`` releases its waiters FIFO, so order is preserved for free
    while different destinations proceed in parallel. The dicts grow with
    distinct destinations, which at this project's scale is bounded -- no reaper.
    """

    def __init__(self, app: hikari.RESTAware, suppressor: PostSuppressor) -> None:
        self._app = app
        self._suppressor = suppressor
        self._locks: dict[Destination, asyncio.Lock] = {}
        self._last_sent: dict[Destination, float] = {}

    async def send(self, delivery: _Delivery) -> None:
        destination = delivery.destination
        lock = self._locks.setdefault(destination, asyncio.Lock())
        async with lock:
            await self._wait_turn(destination)
            # Checked here, not at plan time: /recent may have displayed this
            # play while we were sleeping, which is precisely the race.
            if self._suppressor.suppressed(destination, delivery.play_score_id):
                logger.debug(
                    "live: %s already showed play %s; skipping",
                    destination,
                    delivery.play_score_id,
                )
                return
            await self._deliver(destination, delivery.embed, delivery.spoiler)
            self._last_sent[destination] = monotonic()

    async def _wait_turn(self, destination: Destination) -> None:
        last = self._last_sent.get(destination)
        if last is None:
            return
        remaining = SPACING - (monotonic() - last)
        if remaining > 0:
            await asyncio.sleep(remaining)

    async def _deliver(
        self, destination: Destination, embed: hikari.Embed, spoiler: bool
    ) -> None:
        kind, target = destination
        # A Components V2 message carries no embed; the jacket travels as the
        # container's own attachment, recovered from the embed's thumbnail.
        component = as_container(embed, [], spoiler=spoiler)
        if kind == _DM:
            await send_dm(self._app, target, component=component)
            return
        try:
            await self._app.rest.create_message(target, component=component)
        except hikari.HikariError:
            # A deleted channel or a lost send permission must not take the task
            # down, and must not hold up any other destination.
            logger.info("live: cannot post in channel %s", target)
