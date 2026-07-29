"""Tier pools and the class clue column.

Both regress silently: a byd tier that forgot BYD_2 quietly drops one of Last's
two Beyonds from a mode meant to cover them, and a class column gated on a tier
*name* rather than the hidden flag is either dead-green on every row or missing
from the one tier that needs it.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from coda.chardle import tiers
from coda.chardle.columns import Clue, select_columns
from coda.chardle.facts import load_pool
from coda.db.enums import DifficultyClass


def test_beyond_tier_includes_the_second_beyond_slot() -> None:
    # byd_2 is a storage slot, not a class: both of Last's Beyonds are Beyond.
    assert tiers.get("byd").classes == {
        DifficultyClass.BYD,
        DifficultyClass.BYD_2,
    }


def test_extras_still_merges_all_three_slots() -> None:
    assert tiers.get("extras").classes == {
        DifficultyClass.BYD,
        DifficultyClass.BYD_2,
        DifficultyClass.ETR,
    }


def test_only_extras_hides_its_class() -> None:
    hidden = {n for n in tiers.TIERS if tiers.get(n).class_is_hidden}
    assert hidden == {"extras"}


def test_picker_offers_the_standalone_extras() -> None:
    assert {"byd", "etr", "extras"} <= set(tiers.playable_names())


def test_extras_picker_name_differs_from_its_board_label() -> None:
    # The dropdown must say what it merges; the board must not.
    extras = tiers.get("extras")
    assert (extras.pick_label, extras.label) == ("ETR + BYD", "Extra")


def test_standalone_tiers_are_not_in_the_daily_rotation() -> None:
    assert not {"byd", "etr"} & set(tiers._DAILY_WEIGHTS)


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["byd", "etr", "extras"])
async def test_class_column_appears_only_where_the_class_is_hidden(
    db: AsyncSession, name: str
) -> None:
    tier = tiers.get(name)
    pool = await load_pool(db, tier.classes, allow_sentinels=tier.allow_sentinels)
    assert pool, f"{name} drew an empty pool"
    columns = select_columns(pool, pool[0], class_is_hidden=tier.class_is_hidden)
    assert (Clue.CLASS in columns) is tier.class_is_hidden


@pytest.mark.asyncio
async def test_extras_pool_is_beyond_plus_eternal(db: AsyncSession) -> None:
    async def size(name: str) -> int:
        tier = tiers.get(name)
        return len(await load_pool(db, tier.classes, allow_sentinels=False))

    assert await size("extras") == await size("byd") + await size("etr")
