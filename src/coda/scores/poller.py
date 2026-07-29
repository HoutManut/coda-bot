"""The score poll loop: read recent plays off the wire, store the new ones.

Both paths run in one cycle, each with its own unit (``scores/keys.py``): the
friend path polls a BOT ACCOUNT -- one ``/friend/me`` returns every friend it
holds, and the own path polls a credentialed PLAYER, one ``/user/me`` each,
which is the only source of pure/far/lost. The paths do not overlap: a player
the own path covers is dropped from the friend path's results (``_friend_scores``),
so exactly one path authors any given play.

Traffic shape is deliberate. A fixed-period sweep firing every account
back-to-back from one IP is the most script-shaped pattern possible against an
API Cloudflare fronts, and the bot accounts are hand-made and unreplaceable. So
each key keeps its own due time (``scores/schedule.py``), jittered and nudged
apart from its neighbors, and a tick normally polls one key. Slow and irregular
beats fast and metronomic -- scores are read minutes after the fact at worst, and
an impatient user has ``/recent``, which refreshes just their own account on
demand.
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import replace

import hikari
from sqlalchemy.ext.asyncio import AsyncSession

from coda.arcaea import endpoints
from coda.arcaea.dto import ScoreResult, parse_friends, parse_me
from coda.arcaea.errors import ArcaeaError, InvalidCredentials
from coda.catalog.chart_resolution import resolve_chart
from coda.config import config
from coda.db.session import async_session
from coda.players.session import PlayerSessionProvider
from coda.scores.coordinator import PollCoordinator
from coda.scores.keys import BOT, OWN, PollKey
from coda.scores.observations import ObservationCache
from coda.scores.poster import PostQueue, submit
from coda.scores.schedule import PollSchedule
from coda.scores.service import ScoreStore
from coda.sessions.pool import SessionPool
from coda.settings import REGISTRY, ConfigService, Scope
from coda.settings.service import GLOBAL_SCOPE_ID

logger = logging.getLogger(__name__)

# Seconds to idle BETWEEN keys that came due together, so a cold start or a
# backlog does not fire as one burst. Never before the first key -- it has
# nothing to stagger against -- and never on a targeted refresh, where one
# account is polled and a user is waiting on it.
STAGGER = (3.0, 12.0)

# What one path saw: the recent plays, plus every account it covered mapped to
# its live PTT (None = the player hides it). Ratings are reported for accounts
# with no recent play too -- "no play" says nothing about whether PTT is hidden.
type _Observed = tuple[list[ScoreResult], dict[int, float | None]]


async def run(
    coordinator: PollCoordinator,
    observations: ObservationCache,
    app: hikari.RESTAware,
    posts: PostQueue | None = None,
    *,
    interval: float | None = None,
) -> None:
    """Poll forever: sleep until the earliest key is due, poll it, signal waiters.

    Periodic polling is gated by the bot-wide ``polling`` config key, read fresh
    every tick so ``/run config set polling on|off`` takes effect within one
    interval and never needs a restart. With it off, due keys are pushed forward
    unpolled -- the clock keeps running and no requests are spent; an on-demand
    refresh (``/recent``) still runs, which is exactly on-demand-only.
    """
    schedule = PollSchedule(
        config.poll_interval if interval is None else interval)
    store = ScoreStore()

    while True:
        pollable = await _pollable_keys(app)
        schedule.sync(key for key, scheduled in pollable.items() if scheduled)

        targets = await coordinator.wait_for_trigger(schedule.seconds_until_due())
        periodic = targets is None
        # A target is polled as named, not filtered against `pollable`: that
        # snapshot predates the wake, so filtering would drop an account
        # registered while the loop slept. A key with no usable session costs
        # one no-op DB read in _poll_key.
        keys = schedule.due_keys() if periodic else list(targets)

        covered: set[PollKey] = set()
        try:
            if periodic and not await _polling_enabled():
                logger.debug(
                    "polling is off; skipping %d due key(s)", len(keys))
            else:
                covered = await _run_cycle(
                    store, observations, keys, app, periodic, posts
                )
        except Exception:
            logger.exception("poll cycle failed; retrying next tick")
        finally:
            schedule.reschedule(keys)
            await coordinator.mark_cycle_done(covered)


async def _polling_enabled() -> bool:
    """Whether bot-wide periodic polling is currently switched on.

    Read at ``Scope.GLOBAL`` directly rather than through
    :meth:`ConfigService.resolve`: this key has no Discord context, and feeding
    resolve a made-up channel/user id to get one would be a lie. Unset means the
    registry default.
    """
    async with async_session() as db:
        value = await ConfigService().get_at_scope(
            db, "polling", Scope.GLOBAL, GLOBAL_SCOPE_ID
        )
    return (REGISTRY["polling"].default if value is None else value) == "on"


async def _run_cycle(
    store: ScoreStore,
    observations: ObservationCache,
    keys: list[PollKey],
    app: hikari.RESTAware,
    periodic: bool,
    posts: PostQueue | None,
) -> set[PollKey]:
    """Poll the given keys and return the ones actually reached.

    ``periodic`` distinguishes a scheduled tick from an on-demand refresh: it
    controls the stagger and the log label, nothing else. A key that fails is
    left out of the return so the coordinator never reports it as fresh.
    """
    keys = list(keys)
    random.shuffle(keys)  # order within a tick must not be stable

    covered: set[PollKey] = set()
    total_scores = 0
    total_new = 0
    for index, key in enumerate(keys):
        if periodic and index:
            await asyncio.sleep(random.uniform(*STAGGER))
        try:
            seen, new = await _poll_key(store, observations, key, app, posts)
        except ArcaeaError:
            # One bad key never blocks the others, and stays uncovered.
            logger.exception("poll: %s failed; skipping", key)
            continue
        covered.add(key)
        total_scores += seen
        total_new += new

    logger.info(
        "poll cycle (%s): %d key(s), %d recent score(s), %d new play(s)",
        "scheduled" if periodic else "on-demand",
        len(covered),
        total_scores,
        total_new,
        extra={'file': total_new > 0}
    )
    return covered


async def _pollable_keys(app: hikari.RESTAware) -> dict[PollKey, bool]:
    """Everything pollable right now -> whether it belongs on the schedule.

    A tracking-disabled account maps to ``False``: its scores are never stored,
    so a scheduled ``/user/me`` for it spends a request on a result that is
    guaranteed to be discarded, but a targeted refresh still runs -- ``/recent``
    may fetch for such an account, it just renders the observation instead of a
    stored row. The same filter must not move into
    ``PlayerSessionProvider._pollable``, which ``session_for`` shares.

    The friend path has no equivalent KEY to skip: one ``/friend/me`` covers
    every friend of a bot account, so the request is spent either way -- it
    filters its RESULTS instead (``_friend_scores``). ``ingest`` is what enforces
    the tracking opt-out for both.
    """
    async with async_session() as db:
        keys: dict[PollKey, bool] = {
            (BOT, s.account_id): True for s in await SessionPool(db).active()
        }
        async for account, _ in PlayerSessionProvider(db, app).poll_sessions():
            keys[(OWN, account.id)] = account.tracking_enabled
    return keys


async def _poll_key(
    store: ScoreStore,
    observations: ObservationCache,
    key: PollKey,
    app: hikari.RESTAware,
    posts: PostQueue | None,
) -> tuple[int, int]:
    """Poll one key on whichever path owns it. Returns (seen, new).

    Each key gets its own short-lived DB session: a cycle spends most of its
    wall time asleep between keys, and one session spanning that would hold a
    Postgres connection idle for minutes.
    """
    namespace, target_id = key
    async with async_session() as db:
        if namespace == BOT:
            results, ratings = await _friend_scores(db, target_id, app)
        else:
            results, ratings = await _own_scores(db, target_id, app)
        for arc_user_id, rating in ratings.items():
            observations.record_rating(arc_user_id, rating)
        new_play_ids = await _store(store, observations, db, results)

    # Submitted outside the session: the poster opens its own, and a wedged
    # poster must never hold this one open. Non-blocking by construction.
    submit(posts, new_play_ids)
    return len(results), len(new_play_ids)


async def _friend_scores(
    db: AsyncSession, bot_account_id: int, app: hikari.RESTAware
) -> _Observed:
    """Every friend's recent play from one bot account, tier-1 detail.

    Plays of players the own path covers are DROPPED, not merged. Both paths
    see the same play, and whichever lands first is the one that gets inserted,
    posted and cached -- so a friend sighting winning that race publishes a play
    with no note counts, health or clear type, and the own sighting that follows
    enriches the row silently, too late to fix the post or the cache. Yielding
    is what makes the own path the sole author of those players' plays.

    The cost is one play per own-poll interval: a player who finishes a second
    chart before their own key comes due loses the first, since ``/user/me``
    only ever returns the latest. Accepted -- the own path is also the only
    thing that can tell a hard-gauge death from a low score, so a dropped play
    would have been recorded wrong anyway.

    Ratings are reported for every friend regardless: a PTT reading is
    current state, not a play, and a second sighting of it costs nothing.
    """
    session = await SessionPool(db).get(bot_account_id)
    if session is None:
        logger.debug(
            "poll: bot account %s no longer active; skipping", bot_account_id)
        return [], {}

    friends = parse_friends(await session.call(endpoints.fetch_friends))
    plays = [f.recent_score for f in friends if f.recent_score is not None]
    covered = await PlayerSessionProvider(db, app).own_covered(
        p.arc_user_id for p in plays
    )
    if covered:
        logger.debug(
            "poll: bot account %s yielding %d play(s) to the own path",
            bot_account_id,
            sum(p.arc_user_id in covered for p in plays),
        )
    return (
        [p for p in plays if p.arc_user_id not in covered],
        {f.arc_user_id: f.rating for f in friends},
    )


async def _own_scores(
    db: AsyncSession, arcaea_account_id: int, app: hikari.RESTAware
) -> _Observed:
    """One credentialed player's own recent play, full detail.

    A terminal 403 has already flipped ``is_valid=False`` -- durably, in the
    adapter's own transaction -- by the time it surfaces, so the credential
    drops out of the next sweep on its own; all that is left is telling the
    owner, once.
    """
    provider = PlayerSessionProvider(db, app)
    pair = await provider.session_for(arcaea_account_id)
    if pair is None:
        logger.debug(
            "poll: account %s has no usable login; skipping", arcaea_account_id)
        return [], {}

    account, session = pair
    try:
        me = parse_me(await session.call(endpoints.fetch_me))
    except InvalidCredentials:
        await provider.handle_invalid(account)
        raise

    scores = [] if me.recent_score is None else [me.recent_score]
    return scores, {me.arc_user_id: me.rating}


async def _store(
    store: ScoreStore,
    observations: ObservationCache,
    db: AsyncSession,
    results: list[ScoreResult],
) -> list[int]:
    """Resolve each play's chart and ingest; return the genuinely-new row ids.

    Every resolved play is recorded in the observation cache first, whether or
    not ``ingest`` goes on to store it: an account with tracking off gets no row,
    and the cache is the only thing ``/recent`` can then show it.

    Sorted by ``time_played`` before ingest, not after: ``ingest`` preserves
    input order, so this is what makes the returned ids -- and therefore the
    live feed -- read in the order the plays actually happened. One friend-path
    cycle can yield many plays at once, and iteration order is not that order.
    """
    resolved = [
        replace(r, difficulty_id=await resolve_chart(db, r.song_id, r.difficulty))
        for r in results
    ]
    resolved.sort(key=lambda r: r.time_played)
    for result in resolved:
        observations.record(result)
    new_play_ids = await store.ingest(db, resolved)
    await db.commit()  # ingest does not commit
    return new_play_ids
