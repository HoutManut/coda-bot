"""PollSchedule -- when each poll key is next due. In-memory, no I/O.

The unit is the KEY, not the sweep: ``poll_interval`` is the gap between two
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
from collections.abc import Iterable, Set as AbstractSet
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

# The gap for a key an open tournament round has made hot. A round window is
# 200-500 s, so this resolves the board and the early all-scored exit to well
# under 2% of the shortest one. It is not the handoff's 5 s: STAGGER already
# idles seconds between keys inside a tick, so 5 s would need the stagger
# bypassed and _spread rewritten for two moduli, against an unmeasured rate
# limit -- see wiki/questions/h-real-rate-limit-shape-unknown.md.
HOT_INTERVAL = 15.0


class PollSchedule:
    """Monotonic due time per poll key, with phases spread across the interval."""

    def __init__(self, interval: float) -> None:
        self._interval = interval
        self._due: dict[PollKey, float] = {}
        self._hot: frozenset[PollKey] = frozenset()

    def set_interval(self, interval: float) -> None:
        """Adopt a new base gap, set at runtime through the config key.

        Keys pick it up as they reschedule. A shortened gap also pulls in any
        key still parked further out than the new one allows -- otherwise
        going from 600 s to 60 s would sit out one last 600 s gap first.
        """
        if interval == self._interval:
            return
        self._interval = interval
        now = monotonic()
        horizon = now + interval * (1 + JITTER)
        for key, due in self._due.items():
            if key not in self._hot and due > horizon:
                self._due[key] = now + random.uniform(0, interval)

    def sync(
        self, pollable: Iterable[PollKey], hot: AbstractSet[PollKey] = frozenset()
    ) -> None:
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
            # Capped at the key's own gap: a hot newcomer laid out on the
            # 90 s lattice would sit out five gaps before its first poll.
            self._due[key] = now + min(slot * spacing, self._interval_for(key))

        self._hot = frozenset(hot) & keys
        self._pull_forward()

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
            if key not in self._due:
                continue
            proposal = now + self._jittered(key)
            # Hot keys skip the spread: it compares phases against ONE modulus
            # and is undefined across two, and a key polling every 15 s is not
            # the slow metronomic traffic the spread exists to break up.
            self._due[key] = (
                proposal if key in self._hot else self._spread(key, proposal)
            )

    def _interval_for(self, key: PollKey) -> float:
        return HOT_INTERVAL if key in self._hot else self._interval

    def _jittered(self, key: PollKey) -> float:
        return self._interval_for(key) * random.uniform(1 - JITTER, 1 + JITTER)

    def _pull_forward(self) -> None:
        """Bring a key that just went hot forward to its new gap.

        A round opening must not wait out the 90 s slot the key already held,
        or its first hot poll lands after a fifth of the window is gone.
        """
        now = monotonic()
        horizon = now + HOT_INTERVAL
        for key in self._hot:
            if key in self._due and self._due[key] > horizon:
                self._due[key] = now + random.uniform(0, HOT_INTERVAL)

    def _spread(self, key: PollKey, proposal: float) -> float:
        """Nudge one key's proposed due time toward the middle of its own gap.

        Neighbours compared by PHASE (offset modulo the interval), not absolute
        due time -- see wiki/gotchas/d-poll-schedule-absolute-vs-phase.md.
        Hot keys are left out of the comparison as well as skipped by it: they
        run on a different modulus, so their phases say nothing here.
        """
        offsets = [
            (due - proposal) % self._interval
            for other, due in self._due.items()
            if other != key and other not in self._hot
        ]
        if not offsets:
            return proposal

        ahead = min(offsets)
        behind = self._interval - max(offsets)
        return proposal + CORRECTION * (ahead - behind) / 2
