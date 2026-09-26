"""Tier pools: which difficulty classes each tier draws from.

This regresses silently. A byd tier that forgot BYD_2 quietly drops one of
Last's two Beyonds from a mode meant to cover them, and the board still renders
a perfectly ordinary puzzle over the pool that is left.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from coda.chardle import tiers
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


def test_picker_offers_the_standalone_extras() -> None:
    assert {"byd", "etr", "extras"} <= set(tiers.playable_names())


def test_the_picker_says_what_extras_merges() -> None:
    # A tier named for neither of the classes it draws from tells the player
    # nothing about what they are about to be asked.
    assert tiers.get("extras").pick_label == "Eternal + Beyond"


def test_standalone_tiers_are_not_in_the_daily_rotation() -> None:
    assert not {"byd", "etr"} & set(tiers._DAILY_WEIGHTS)


@pytest.mark.asyncio
async def test_extras_pool_is_beyond_plus_eternal(db: AsyncSession) -> None:
    async def size(name: str) -> int:
        tier = tiers.get(name)
        return len(await load_pool(db, tier.classes, allow_sentinels=False))

    assert await size("extras") == await size("byd") + await size("etr")
