"""PollSchedule phase math -- pure, no DB, and it regresses silently."""

from __future__ import annotations

import statistics

import pytest

from coda.scores import schedule as schedule_module
from coda.scores.schedule import PollSchedule

INTERVAL = 90.0


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    fake = FakeClock()
    monkeypatch.setattr(schedule_module, "monotonic", fake)
    return fake


@pytest.fixture
def no_jitter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(schedule_module.random, "uniform", lambda low, high: 1.0)


def keys(count: int) -> list[tuple[str, int]]:
    return [("bot", index) for index in range(count)]


def test_cold_start_spreads_across_the_interval(clock: FakeClock) -> None:
    poll_schedule = PollSchedule(INTERVAL)
    poll_schedule.sync(keys(5))

    offsets = sorted(due - clock.now for due in poll_schedule._due.values())
    assert offsets == pytest.approx([18.0, 36.0, 54.0, 72.0, 90.0])


def test_no_key_is_due_at_startup(clock: FakeClock) -> None:
    poll_schedule = PollSchedule(INTERVAL)
    poll_schedule.sync(keys(5))

    assert poll_schedule.due_keys() == []
    assert poll_schedule.seconds_until_due() == pytest.approx(18.0)


def test_joining_never_moves_an_existing_phase(clock: FakeClock) -> None:
    poll_schedule = PollSchedule(INTERVAL)
    poll_schedule.sync(keys(5))
    before = dict(poll_schedule._due)

    clock.now += 10.0
    poll_schedule.sync(keys(6))

    newcomer = ("bot", 5)
    assert {k: v for k, v in poll_schedule._due.items() if k != newcomer} == before
    assert poll_schedule._due[newcomer] - clock.now == pytest.approx(INTERVAL / 6)


def test_departed_keys_are_dropped(clock: FakeClock) -> None:
    poll_schedule = PollSchedule(INTERVAL)
    poll_schedule.sync(keys(3))
    poll_schedule.sync(keys(2))

    assert set(poll_schedule._due) == set(keys(2))


def test_empty_schedule_waits_one_interval(clock: FakeClock) -> None:
    assert PollSchedule(INTERVAL).seconds_until_due() == INTERVAL


def test_reschedule_never_leaves_a_key_due_in_the_past(clock: FakeClock) -> None:
    poll_schedule = PollSchedule(INTERVAL)
    poll_schedule.sync(keys(4))

    clock.now += INTERVAL * 2  # everything overdue
    due = poll_schedule.due_keys()
    assert len(due) == 4

    poll_schedule.reschedule(due)
    assert poll_schedule.due_keys() == []
    assert poll_schedule.seconds_until_due() > 0


def test_reschedule_of_an_unscheduled_key_creates_nothing(clock: FakeClock) -> None:
    poll_schedule = PollSchedule(INTERVAL)
    poll_schedule.sync(keys(2))

    poll_schedule.reschedule([("own", 99)])

    assert set(poll_schedule._due) == set(keys(2))


def test_clustered_phases_pull_apart(clock: FakeClock, no_jitter: None) -> None:
    poll_schedule = PollSchedule(INTERVAL)
    poll_schedule.sync(keys(4))
    for key in keys(4):  # every key on the same phase
        poll_schedule._due[key] = clock.now + INTERVAL

    for _ in range(8):
        clock.now = min(poll_schedule._due.values())
        poll_schedule.reschedule(poll_schedule.due_keys())

    assert min(_phase_gaps(poll_schedule)) > 5.0  # was 0 -- the cluster dissolved


def test_gaps_stay_irregular_under_jitter(clock: FakeClock) -> None:
    """A perfect lattice is its own fingerprint -- convergence here is the bug."""
    poll_schedule = PollSchedule(INTERVAL)
    poll_schedule.sync(keys(4))

    spreads = []
    for round_index in range(400):
        clock.now = min(poll_schedule._due.values())
        poll_schedule.reschedule(poll_schedule.due_keys())
        if round_index > 50:
            spreads.append(statistics.pstdev(_phase_gaps(poll_schedule)))

    assert statistics.mean(spreads) > 5.0


def test_mean_period_stays_on_the_interval(clock: FakeClock) -> None:
    """Catches a one-directional correction: the bug 12 exists to remove."""
    poll_schedule = PollSchedule(INTERVAL)
    poll_schedule.sync(keys(5))
    watched = ("bot", 0)

    gaps = []
    for _ in range(8000):  # enough samples that jitter's own spread cannot fake a bias
        clock.now = min(poll_schedule._due.values())
        before = poll_schedule._due[watched]
        poll_schedule.reschedule(poll_schedule.due_keys())
        if poll_schedule._due[watched] != before:
            gaps.append(poll_schedule._due[watched] - before)

    assert statistics.mean(gaps) == pytest.approx(INTERVAL, rel=0.03)


def _phase_gaps(poll_schedule: PollSchedule) -> list[float]:
    ordered = sorted(due % INTERVAL for due in poll_schedule._due.values())
    return [later - earlier for earlier, later in zip(ordered, ordered[1:])]
