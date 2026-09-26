"""The hot lane: a key an open tournament round wants polled faster.

The trap this guards is the handover, not the arithmetic. A key that goes hot
already holds a due time up to a full interval away, so without pulling it
forward the "faster" cadence does not start until the slow gap it was already
serving has run out.
"""

from __future__ import annotations

from time import monotonic

from coda.scores.keys import BOT, OWN
from coda.scores.schedule import HOT_INTERVAL, PollSchedule

INTERVAL = 90.0
COLD = (BOT, 1)
HOT = (BOT, 2)


def schedule(*, hot=frozenset(), keys=(COLD, HOT)) -> PollSchedule:
    sched = PollSchedule(INTERVAL)
    sched.sync(keys, hot)
    return sched


class TestGap:
    def test_a_hot_key_reschedules_inside_its_own_gap(self):
        sched = schedule(hot={HOT})
        sched.reschedule([HOT])
        assert sched._due[HOT] - monotonic() <= HOT_INTERVAL * 1.4 + 0.1

    def test_a_cold_key_keeps_the_normal_gap(self):
        sched = schedule(hot={HOT})
        sched.reschedule([COLD])
        assert sched._due[COLD] - monotonic() > HOT_INTERVAL * 2

    def test_going_cold_restores_the_normal_gap(self):
        sched = schedule(hot={HOT})
        sched.sync([COLD, HOT], frozenset())
        sched.reschedule([HOT])
        assert sched._due[HOT] - monotonic() > HOT_INTERVAL * 2


class TestHandover:
    def test_going_hot_pulls_an_existing_key_forward(self):
        """The whole point: a round opening must not wait out the slow slot."""
        sched = schedule()
        sched.reschedule([HOT])
        assert sched._due[HOT] - monotonic() > HOT_INTERVAL

        sched.sync([COLD, HOT], {HOT})
        assert sched._due[HOT] - monotonic() <= HOT_INTERVAL

    def test_a_key_already_due_soon_is_not_pushed_back(self):
        sched = schedule()
        sched._due[HOT] = monotonic() + 1.0
        sched.sync([COLD, HOT], {HOT})
        assert sched._due[HOT] - monotonic() <= 1.0

    def test_a_hot_newcomer_does_not_land_on_the_slow_lattice(self):
        sched = PollSchedule(INTERVAL)
        sched.sync([(BOT, 10 + i) for i in range(10)] + [HOT], {HOT})
        assert sched._due[HOT] - monotonic() <= HOT_INTERVAL

    def test_hot_keys_that_are_not_pollable_are_ignored(self):
        """A participant whose account went inactive drops off the schedule;
        naming it hot must not resurrect it."""
        sched = PollSchedule(INTERVAL)
        sched.sync([COLD], {(OWN, 999)})
        assert (OWN, 999) not in sched._due


class TestSpread:
    def test_a_hot_key_does_not_drag_cold_phases(self):
        """The spread compares phases modulo ONE interval; a 15 s key's phase
        says nothing on the 90 s lattice."""
        sched = PollSchedule(INTERVAL)
        # Ids disjoint from HOT: a key that is in both lists is a hot key, and
        # would be rescheduled onto the hot gap it is being checked against.
        keys = [(BOT, 10 + i) for i in range(4)]
        sched.sync(keys + [HOT], {HOT})
        before = {k: sched._due[k] for k in keys}
        sched.reschedule(keys)
        assert all(sched._due[k] != before[k] for k in keys)
        assert all(sched._due[k] - monotonic() > HOT_INTERVAL for k in keys)
