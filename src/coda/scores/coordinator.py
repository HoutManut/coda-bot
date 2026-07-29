"""PollCoordinator -- single-writer gate between the poll loop and /recent.

The poller is the ONLY code that calls lowiro; a command that wants fresh data
does not fetch, it asks here for a recent cycle and then reads Postgres. That
keeps exactly one fetcher, so an on-demand refresh never competes with the loop
for the shared rate limiter. No DB, no lowiro -- plain asyncio.

Refreshes are **targeted**: a caller names the poll key it needs fresh (the bot
account holding that player) and only that one is swept, so an on-demand refresh
costs one request instead of a full sweep. The key is opaque here -- the
coordinator never interprets it, which is what keeps the
``bot_account_id``-lives-in-``sessions/`` rule intact.

Refreshes are also **budgeted**, per key and not per user: the resource being
spent is a bot account's request allowance, and one such account is shared by
every player it holds, so no per-command or per-user limit can see the spend.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from time import monotonic

from coda.config import config
from coda.scores.keys import PollKey

logger = logging.getLogger(__name__)

# How long request_refresh waits for a cycle before giving up and letting the
# caller read whatever the DB already has: a wedged poller must never hang a
# command. Queueing on the budget below is NOT this condition -- it is the
# system working as designed -- and must not be logged as a fault.
_WEDGED_POLLER_TIMEOUT = 20.0

# Default freshness a caller accepts. Short enough that a play made seconds ago
# shows up, long enough that a spam of commands coalesces onto one cycle. It
# coalesces a BURST; it is not a rate limit -- that is _RefreshBudget's job.
DEFAULT_MAX_AGE = 5.0

# Sustained on-demand fetch rate per key, and how much of it can be saved up.
# Without a floor, /recent every 6 s drives one bot account at ~15x the poller's
# own cadence, indefinitely -- the only unbounded traffic path in the bot, on
# accounts that are hand-made and unreplaceable.
_REFILLS_PER_INTERVAL = 2.0
_BUDGET_CAP = 3.0


class _RefreshBudget:
    """Per-key token bucket: one token per fetch that reaches the wire."""

    def __init__(self, rate: float, cap: float) -> None:
        self._rate = rate
        self._cap = cap
        # poll key -> (tokens at last spend, monotonic time of that spend).
        self._buckets: dict[PollKey, tuple[float, float]] = {}

    def _level(self, key: PollKey, now: float) -> float:
        tokens, since = self._buckets.get(key, (self._cap, now))
        return min(self._cap, tokens + (now - since) * self._rate)

    async def spend(self, key: PollKey) -> None:
        """Take a token for ``key``, waiting for one when the bucket is empty.

        Waiting rather than serving stale: ``/recent`` defers before it calls in,
        so a correct answer late beats a wrong answer now. The wait is bounded by
        ``1 / rate`` by construction -- an empty bucket is at worst one refill
        away.
        """
        now = monotonic()
        level = self._level(key, now)
        if level < 1.0:
            delay = (1.0 - level) / self._rate
            logger.info("refresh budget: %s queued for %.0fs", key, delay)
            await asyncio.sleep(delay)
            now, level = monotonic(), 1.0
        self._buckets[key] = (level - 1.0, now)


class PollCoordinator:
    """Coalesces on-demand refresh requests onto the poll loop's next cycle."""

    def __init__(self) -> None:
        self._wake = asyncio.Event()
        self._done = asyncio.Condition()
        self._cycle_seq = 0
        # poll key -> monotonic time of the last cycle that reached it.
        self._last_covered: dict[PollKey, float] = {}
        self._pending: set[PollKey] = set()
        self._budget = _RefreshBudget(
            _REFILLS_PER_INTERVAL / config.poll_interval, _BUDGET_CAP
        )

    async def wait_for_trigger(self, timeout: float | None) -> set[PollKey] | None:
        """Sleep until the next tick or an on-demand wake, whichever is first.

        Returns the keys an on-demand caller is waiting on, or ``None`` for a
        plain periodic tick, which means a full sweep. ``timeout=None`` blocks
        until an on-demand wake -- that is how polling-disabled is expressed.
        """
        try:
            await asyncio.wait_for(self._wake.wait(), timeout=timeout)
        except TimeoutError:
            return None  # the normal periodic tick, not a failure
        self._wake.clear()
        targets = set(self._pending)
        self._pending.clear()
        return targets

    async def mark_cycle_done(self, covered: Iterable[PollKey]) -> None:
        """Record which keys a finished cycle reached and release its waiters.

        Only keys that genuinely succeeded belong in ``covered`` -- an account
        that errored must not be stamped fresh, or the next refresh for it
        returns instantly on data that was never fetched.
        """
        now = monotonic()
        async with self._done:
            for key in covered:
                self._last_covered[key] = now
            self._cycle_seq += 1
            self._done.notify_all()

    async def request_refresh(
        self, key: PollKey, *, max_age: float = DEFAULT_MAX_AGE
    ) -> None:
        """Ensure ``key`` was polled within ``max_age`` seconds; block until so.

        Returns at once when it is already fresh enough -- the debounce that
        stops repeated calls from forcing redundant cycles, and the reason a
        served-from-freshness call spends no budget. Otherwise it queues on the
        key's budget, wakes the loop, and waits for a cycle that COVERED this
        key, bounded so a stuck poller can't hang the caller. Concurrent callers
        coalesce: same key onto one cycle, different keys onto one cycle
        covering both.
        """
        # Wait on coverage, not on a sequence bump: a cycle can finish without
        # reaching this key (it errored, or it raced ahead of the pending set)
        # and that must not count as served.
        def covered() -> bool:
            stamped = self._last_covered.get(key)
            return stamped is not None and monotonic() - stamped <= max_age

        if covered():
            return

        await self._budget.spend(key)
        if covered():  # another caller's cycle landed while we queued
            return

        async with self._done:
            self._pending.add(key)
            self._wake.set()
            try:
                await asyncio.wait_for(
                    self._done.wait_for(covered), timeout=_WEDGED_POLLER_TIMEOUT
                )
            except TimeoutError:
                logger.warning(
                    "request_refresh(%s) timed out after %.0fs; "
                    "serving possibly-stale data",
                    key,
                    _WEDGED_POLLER_TIMEOUT,
                )
