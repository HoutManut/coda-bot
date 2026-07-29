"""Which clue columns a pool can support.

The wrong rule here regresses silently: a board still renders, still looks
informative, and simply never shows the columns it dropped. The rule that shipped
first read "unknown *anywhere* in the pool" and so deleted `charter` from every
tier over the ~40 charts with no charter link, and `artist` from all but `byd`
over a single one -- leaving four possible board shapes per tier instead of
twenty. See wiki d-chardle-dead-clue-columns.
"""

from __future__ import annotations

import random
from dataclasses import replace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from coda.chardle import tiers
from coda.chardle.columns import Clue, select_columns
from coda.chardle.facts import ChartFacts, load_pool
from coda.db.enums import DifficultyClass

_ROLLS = 200


async def _pool(db: AsyncSession, name: str) -> list[ChartFacts]:
    tier = tiers.get(name)
    pool = await load_pool(db, tier.classes, allow_sentinels=tier.allow_sentinels)
    assert pool, f"{name} drew an empty pool"
    return pool


def _rolled(pool, answer, *, hidden: bool = False) -> set[Clue]:
    """Every column that appears in any roll for this (pool, answer)."""
    rng = random.Random(0)
    seen: set[Clue] = set()
    for _ in range(_ROLLS):
        seen.update(select_columns(pool, answer, class_is_hidden=hidden, rng=rng))
    return seen


@pytest.mark.asyncio
async def test_a_gap_elsewhere_in_the_pool_does_not_kill_a_column(
    db: AsyncSession,
) -> None:
    # ~40 Future charts carry no charter link. Those render one grey cell each;
    # they must not cost every other player the whole column.
    pool = await _pool(db, "ftr")
    assert any(not fact.charters for fact in pool), "no gaps left to regress on"
    answer = next(fact for fact in pool if fact.charters)
    assert Clue.CHARTER in _rolled(pool, answer)


@pytest.mark.asyncio
async def test_a_gap_on_the_answer_does_kill_it(db: AsyncSession) -> None:
    # The other half of the rule: every row would be grey, which is a dead column
    # wearing a live one's clothes.
    pool = await _pool(db, "ftr")
    answer = next(fact for fact in pool if not fact.charters)
    assert Clue.CHARTER not in _rolled(pool, answer)


@pytest.mark.asyncio
async def test_err_still_loses_level_and_rating(db: AsyncSession) -> None:
    # Every err chart stores level = rating = -1, so the *variance* rule drops
    # both on its own -- which is what makes the answer-gap rule above safe to
    # narrow. Arrow arithmetic against an unknown is meaningless.
    pool = await _pool(db, "err")
    rolled = _rolled(pool, pool[0])
    assert not {Clue.LEVEL, Clue.RATING} & rolled


@pytest.mark.asyncio
async def test_a_constant_column_is_dropped(db: AsyncSession) -> None:
    # All seven err charts are Conflict-side, so side says nothing there.
    pool = await _pool(db, "err")
    assert len({fact.side for fact in pool}) == 1
    assert Clue.SIDE not in _rolled(pool, pool[0])


def test_class_reads_the_visible_class_not_the_storage_slot() -> None:
    # byd_2 is a storage slot; both of Last's charts print Beyond. A pool holding
    # only those two varies on difficulty_class and not on the board, so gating
    # the column on the raw value would select one that is green on every row.
    base = ChartFacts(
        difficulty_id=1,
        song_id="last",
        name="Last",
        difficulty_class=DifficultyClass.BYD,
        level=20,
        rating=95,
        note=888,
        bpm=190.0,
        side=1,
        version="1.0",
        pack_id="base",
        pack_name="Arcaea",
        artists=frozenset({"kobaryo"}),
        charters=frozenset({"toaster"}),
    )
    second = replace(base, difficulty_id=2, difficulty_class=DifficultyClass.BYD_2)
    assert Clue.CLASS not in _rolled([base, second], base, hidden=True)
