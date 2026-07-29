"""Grade boundaries and live-update filter evaluation.

Both regress silently: a wrong grade boundary or an inverted gate produces a
feed that is merely quieter or noisier than intended, never an error. The
evaluation here is exercised against a stub :class:`PlayFacts`, so no database
is involved -- the queries it stands in for are covered by their own callers.
"""

from __future__ import annotations

import pytest

from coda.scores.filters import ChannelFloor, Filters, evaluate
from coda.utils.scoring import AA, EX, EX_PLUS, PURE_MEMORY, Grade, grade_of


class _Row:
    """The three PlayScore fields the filters read."""

    def __init__(self, score: int, lost_count: int | None = None) -> None:
        self.score = score
        self.lost_count = lost_count


class _Chart:
    def __init__(self, level: int) -> None:
        self.level = level


class _Facts:
    """A PlayFacts stand-in: the account-level answers, already decided."""

    def __init__(
        self,
        previous_best: int | None = None,
        rank: int | None = None,
    ) -> None:
        self._previous_best = previous_best
        self._rank = rank

    async def previous_best(self) -> int | None:
        return self._previous_best

    async def is_pb(self) -> bool:
        return self._previous_best is None or self._score > self._previous_best

    async def previous_grade(self) -> Grade | None:
        return None if self._previous_best is None else grade_of(self._previous_best)

    async def rank(self) -> int | None:
        return self._rank

    def against(self, row: _Row) -> _Facts:
        self._score = row.score
        return self


def _filters(**overrides) -> Filters:
    base = dict(
        post_all=False,
        post_pb=False,
        post_pm=False,
        post_fr=False,
        best_of=None,
        min_grade=None,
        min_level=None,
    )
    return Filters(**(base | overrides))


async def _check(row, chart, filters, facts, floor=None) -> bool:
    return await evaluate(row, chart, filters, floor, facts.against(row))


# --- grades -------------------------------------------------------------


@pytest.mark.parametrize(
    "score,expected",
    [
        (0, Grade.D),
        (8_499_999, Grade.D),
        (8_500_000, Grade.C),
        (8_900_000, Grade.B),
        (9_200_000, Grade.A),
        (AA, Grade.AA),
        (EX - 1, Grade.AA),
        (EX, Grade.EX),
        (EX_PLUS, Grade.EX_PLUS),
        (PURE_MEMORY - 1, Grade.EX_PLUS),
        (PURE_MEMORY, Grade.PM),
        (PURE_MEMORY + 500, Grade.PM),
    ],
)
def test_grade_of_boundaries(score: int, expected: Grade) -> None:
    assert grade_of(score) is expected


def test_grades_are_ordered() -> None:
    assert Grade.D < Grade.C < Grade.B < Grade.A < Grade.AA < Grade.EX
    assert Grade.EX < Grade.EX_PLUS < Grade.PM


# --- triggers -----------------------------------------------------------


async def test_pb_is_strict() -> None:
    """An equal score is a distinct row, but it is not a new achievement."""
    filters = _filters(post_pb=True)
    equal = await _check(_Row(9_800_000), _Chart(20), filters, _Facts(9_800_000))
    better = await _check(_Row(9_800_001), _Chart(20), filters, _Facts(9_800_000))
    assert equal is False
    assert better is True


async def test_first_ever_play_on_a_chart_is_a_pb() -> None:
    assert await _check(_Row(1), _Chart(20), _filters(post_pb=True), _Facts(None))


async def test_pm_needs_no_note_counts() -> None:
    """Score-derivable, so it fires identically on the friend path."""
    filters = _filters(post_pm=True)
    assert await _check(_Row(PURE_MEMORY), None, filters, _Facts(PURE_MEMORY))
    assert not await _check(_Row(PURE_MEMORY - 1), None, filters, _Facts(None))


async def test_fr_cannot_fire_without_note_counts() -> None:
    """A friend-tier row has lost_count None, which is not a full recall."""
    filters = _filters(post_fr=True)
    assert await _check(_Row(9_000_000, lost_count=0), None, filters, _Facts(None))
    assert not await _check(_Row(9_000_000, lost_count=None), None, filters, _Facts(None))
    assert not await _check(_Row(9_000_000, lost_count=3), None, filters, _Facts(None))


async def test_best_of_requires_a_pb() -> None:
    """bX implies pb: a play that doesn't beat the chart's best can't move rank."""
    filters = _filters(best_of=10)
    ranked_but_not_pb = await _check(
        _Row(9_000_000), _Chart(20), filters, _Facts(previous_best=9_500_000, rank=3)
    )
    ranked_and_pb = await _check(
        _Row(9_600_000), _Chart(20), filters, _Facts(previous_best=9_500_000, rank=3)
    )
    assert ranked_but_not_pb is False
    assert ranked_and_pb is True


async def test_best_of_respects_the_cutoff() -> None:
    filters = _filters(best_of=10)
    assert not await _check(
        _Row(9_600_000), _Chart(20), filters, _Facts(previous_best=None, rank=11)
    )


async def test_best_of_cannot_fire_on_an_unresolved_chart() -> None:
    """No CC means no play rating means no rank. Arithmetic, not policy."""
    assert not await _check(
        _Row(9_900_000), None, _filters(best_of=30), _Facts(previous_best=None, rank=None)
    )


async def test_grade_up_fires_on_a_crossing_only() -> None:
    filters = _filters(min_grade=Grade.EX)
    crossing = await _check(_Row(EX), _Chart(20), filters, _Facts(previous_best=AA))
    already_there = await _check(
        _Row(EX + 1000), _Chart(20), filters, _Facts(previous_best=EX)
    )
    assert crossing is True
    assert already_there is False


async def test_grade_up_respects_its_floor() -> None:
    """Picking EX+ notifies on EX+ crossings only, not on AA or EX ones."""
    filters = _filters(min_grade=Grade.EX_PLUS)
    assert not await _check(_Row(EX), _Chart(20), filters, _Facts(previous_best=AA))
    assert await _check(_Row(EX_PLUS), _Chart(20), filters, _Facts(previous_best=EX))


async def test_no_trigger_enabled_posts_nothing() -> None:
    assert not await _check(_Row(PURE_MEMORY), _Chart(24), _filters(), _Facts(None))


# --- gates --------------------------------------------------------------


async def test_level_gate_beats_every_trigger() -> None:
    """A level-3 pure memory does not post when the user asked for 10+ only."""
    filters = _filters(post_all=True, post_pm=True, min_level=21)
    assert not await _check(_Row(PURE_MEMORY), _Chart(6), filters, _Facts(None))
    assert await _check(_Row(PURE_MEMORY), _Chart(21), filters, _Facts(None))


async def test_level_gate_fails_closed_on_an_unresolved_chart() -> None:
    """No level known, no post -- deliberate, and the one thing worth revisiting."""
    filters = _filters(post_all=True, min_level=21)
    assert not await _check(_Row(PURE_MEMORY), None, filters, _Facts(None))
    assert await _check(_Row(PURE_MEMORY), None, _filters(post_all=True), _Facts(None))


async def test_guild_floor_only_narrows() -> None:
    floor = ChannelFloor(guild_id=1, min_level=21, min_grade=None)
    filters = _filters(post_all=True)
    assert not await _check(_Row(PURE_MEMORY), _Chart(20), filters, _Facts(None), floor)
    assert await _check(_Row(PURE_MEMORY), _Chart(22), filters, _Facts(None), floor)


async def test_guild_grade_floor_gates_the_score() -> None:
    floor = ChannelFloor(guild_id=1, min_level=None, min_grade=Grade.EX)
    filters = _filters(post_all=True)
    assert not await _check(_Row(AA), _Chart(20), filters, _Facts(None), floor)
    assert await _check(_Row(EX), _Chart(20), filters, _Facts(None), floor)


async def test_the_stricter_of_the_two_level_bars_wins() -> None:
    floor = ChannelFloor(guild_id=1, min_level=23, min_grade=None)
    filters = _filters(post_all=True, min_level=19)
    assert not await _check(_Row(PURE_MEMORY), _Chart(21), filters, _Facts(None), floor)
