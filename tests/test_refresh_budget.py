"""The per-key on-demand refresh budget: the only bound on /recent's traffic."""

from __future__ import annotations

import pytest

from coda.scores import coordinator as coordinator_module
from coda.scores.coordinator import _BUDGET_CAP, _RefreshBudget

RATE = 2.0 / 90.0
KEY = ("bot", 1)


class FakeClock:
    def __init__(self) -> None:
        self.now = 500.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    fake = FakeClock()
    monkeypatch.setattr(coordinator_module, "monotonic", fake)
    return fake


@pytest.fixture
def waits(monkeypatch: pytest.MonkeyPatch, clock: FakeClock) -> list[float]:
    """Record every sleep the budget asks for and advance the clock by it."""
    recorded: list[float] = []

    async def fake_sleep(delay: float) -> None:
        recorded.append(delay)
        clock.now += delay

    monkeypatch.setattr(coordinator_module.asyncio, "sleep", fake_sleep)
    return recorded


@pytest.mark.asyncio
async def test_first_spend_on_a_cold_key_never_waits(waits: list[float]) -> None:
    await _RefreshBudget(RATE, _BUDGET_CAP).spend(KEY)

    assert waits == []


@pytest.mark.asyncio
async def test_a_burst_drains_the_cap_then_queues(waits: list[float]) -> None:
    budget = _RefreshBudget(RATE, _BUDGET_CAP)

    for _ in range(int(_BUDGET_CAP)):
        await budget.spend(KEY)
    assert waits == []

    await budget.spend(KEY)
    assert waits == [pytest.approx(1 / RATE)]


@pytest.mark.asyncio
async def test_sustained_spend_settles_at_the_refill_rate(
    clock: FakeClock, waits: list[float]
) -> None:
    budget = _RefreshBudget(RATE, _BUDGET_CAP)
    start = clock.now

    for _ in range(20):
        await budget.spend(KEY)

    elapsed = clock.now - start
    assert elapsed * RATE == pytest.approx(20 - _BUDGET_CAP, abs=0.01)


@pytest.mark.asyncio
async def test_idle_time_refills_but_never_past_the_cap(
    clock: FakeClock, waits: list[float]
) -> None:
    budget = _RefreshBudget(RATE, _BUDGET_CAP)
    await budget.spend(KEY)

    clock.now += 10 * 90.0  # long idle -- 20 tokens' worth of refill
    for _ in range(int(_BUDGET_CAP)):
        await budget.spend(KEY)

    assert waits == []
    await budget.spend(KEY)
    assert waits == [pytest.approx(1 / RATE)]


@pytest.mark.asyncio
async def test_keys_have_separate_budgets(waits: list[float]) -> None:
    budget = _RefreshBudget(RATE, _BUDGET_CAP)

    for _ in range(int(_BUDGET_CAP) + 1):
        await budget.spend(KEY)
    waits.clear()

    await budget.spend(("own", 7))

    assert waits == []
