"""PollSchedule -- when each poll key is next due. In-memory, no I/O.

The unit is the KEY, not the sweep: ``POLL_INTERVAL`` is the gap between two
polls of one account, and stays that as accounts are added. A sweep clock makes
the realised period ``interval + cycle_duration``, so every new account silently
stretches every existing account's gap.

Phases are also kept apart. Jitter alone random-walks a key's phase and an
on-demand refresh yanks it, so keys drift into clusters over hours -- two
requests landing together from one IP is the script-shaped traffic the poller
exists to avoid. Each reschedule nudges its own key toward the middle of its gap
and touches nobody else's clock.
"""

from __future__ import annotations

import random
from collections.abc import Iterable
from time import monotonic

from coda.scores.keys import PollKey

# Fraction of the interval a key's next due time swings by, either way: at the
# 90 s default a key is re-polled 54 s-126 s later and no two gaps repeat.
JITTER = 0.4

# How far a rescheduled key moves toward the middle of its gap. Must stay well
# below 1.0: snapping to the midpoint converges on an evenly-spaced lattice,
# which is a cleaner fingerprint than the clustering it fixes. The target is
# irregular but not clustered.
CORRECTION = 0.3


class PollSchedule:
    """Monotonic due time per poll key, with phases spread across the interval."""

    def __init__(self, interval: float) -> None:
        self._interval = interval
        self._due: dict[PollKey, float] = {}

    def sync(self, pollable: Iterable[PollKey]) -> None:
        """Match the schedule to what is pollable, leaving existing phases alone.

        A key joining must never shift anyone else's clock. Newcomers are shuffled
        (arrival order must not decide who polls first) and spread at
        ``k * interval / N`` from now, ``N`` counting the whole schedule after the
        addition: a cold start lays every key out evenly, and a single latecomer
        lands one slot out, in a gap rather than on top of an existing phase.
        """
        keys = set(pollable)
        for departed in self._due.keys() - keys:
            del self._due[departed]

        newcomers = list(keys - self._due.keys())
        random.shuffle(newcomers)
        spacing = self._interval / (len(self._due) + len(newcomers))
        now = monotonic()
        for slot, key in enumerate(newcomers, start=1):
            self._due[key] = now + slot * spacing

    def seconds_until_due(self) -> float:
        """How long until the earliest key comes due.

        An empty schedule returns the full interval rather than blocking: the
        loop re-reads membership each tick, and a newly registered account must
        not wait for someone to run ``/recent``.
        """
        if not self._due:
            return self._interval
        return max(0.0, min(self._due.values()) - monotonic())

    def due_keys(self) -> list[PollKey]:
        """Every key whose due time has passed -- normally one, sometimes a few."""
        now = monotonic()
        return [key for key, due in self._due.items() if due <= now]

    def reschedule(self, keys: Iterable[PollKey]) -> None:
        """Push every ATTEMPTED key to its next due time, failures included.

        A key left due in the past is a key the loop busy-spins on. Keys not on
        the schedule are skipped, not created: a targeted refresh may name a
        tracking-disabled account, which must not thereby rejoin the sweep.
        """
        now = monotonic()
        for key in keys:
            if key in self._due:
                self._due[key] = self._spread(key, now + self._jittered())

    def _jittered(self) -> float:
        return self._interval * random.uniform(1 - JITTER, 1 + JITTER)

    def _spread(self, key: PollKey, proposal: float) -> float:
        """Nudge one key's proposed due time toward the middle of its own gap.

        Neighbours are compared by PHASE (offset modulo the interval), not by
        absolute due time. Every key polls once per interval, so a neighbour's
        due time repeats; measured absolutely, a proposal a full interval out is
        almost always later than everyone else's pending due time and the
        correction only ever pushes it further out -- a one-directional bias that
        walks every key's period past ``POLL_INTERVAL``, which is the bug this
        module exists to fix.
        """
        offsets = [
            (due - proposal) % self._interval
            for other, due in self._due.items()
            if other != key
        ]
        if not offsets:
            return proposal

        ahead = min(offsets)
        behind = self._interval - max(offsets)
        return proposal + CORRECTION * (ahead - behind) / 2
