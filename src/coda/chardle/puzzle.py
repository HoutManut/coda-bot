"""Drawing an answer and freezing a puzzle onto a row."""

from __future__ import annotations

import random
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from coda.chardle import schedule, tiers
from coda.chardle.columns import MAX_COLUMNS, select_columns
from coda.chardle.facts import load_pool
from coda.chardle.tiers import DAILY_ATTEMPTS, Tier
from coda.db.models import ChardlePuzzle


class EmptyPool(Exception):
    """No chart satisfies the requested tier and filters."""


class PuzzleService:
    """Stateless; takes an ``AsyncSession`` per call."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()

    async def daily(
        self, db: AsyncSession, epoch: date, number: int
    ) -> ChardlePuzzle:
        """Puzzle #``number``, created lazily and shared globally."""
        existing = await self._by_number(db, number)
        if existing is not None:
            return existing

        if schedule.is_april_first(epoch, number):
            tier = tiers.get(tiers.ERR_TIER)
            attempts = await tiers.err_attempts(db)
        else:
            tier = tiers.get(tiers.roll_daily_tier(self._rng))
            attempts = DAILY_ATTEMPTS

        puzzle = await self._draw(db, tier, attempts=attempts, number=number)
        try:
            await db.commit()
        except IntegrityError:
            # Two guilds crossed the same rollover second. UNIQUE(puzzle_number)
            # admits one; the loser reads the winner's row rather than erroring.
            await db.rollback()
            winner = await self._by_number(db, number)
            if winner is None:
                raise
            return winner
        return puzzle

    async def free(
        self,
        db: AsyncSession,
        *,
        tier_name: str,
        level: int | None = None,
        side: int | None = None,
        max_attempts: int | None = None,
        max_columns: int = MAX_COLUMNS,
        now: datetime,
        epoch: date,
    ) -> ChardlePuzzle:
        """An on-demand board. Filters make it a custom challenge, and a custom
        challenge is stats-ineligible by construction."""
        if tier_name == tiers.RANDOM_TIER:
            tier_name = tiers.roll_random_tier(self._rng)
        tier = tiers.get(tier_name)
        if tier.name != tiers.ERR_TIER and tiers.roll_err(
            self._rng, in_event_window=schedule.in_april_window(now)
        ):
            tier = tiers.get(tiers.ERR_TIER)
            level = side = None

        if tier.name == tiers.ERR_TIER:
            max_attempts = await tiers.err_attempts(db)

        filters = _filters(level, side)
        puzzle = await self._draw(
            db,
            tier,
            attempts=max_attempts,
            level=level,
            side=side,
            filters=filters,
            max_columns=max_columns,
        )
        await db.commit()
        return puzzle

    async def _by_number(
        self, db: AsyncSession, number: int
    ) -> ChardlePuzzle | None:
        return await db.scalar(
            select(ChardlePuzzle).where(ChardlePuzzle.puzzle_number == number)
        )

    async def _draw(
        self,
        db: AsyncSession,
        tier: Tier,
        *,
        attempts: int | None,
        number: int | None = None,
        level: int | None = None,
        side: int | None = None,
        filters: dict | None = None,
        max_columns: int = MAX_COLUMNS,
    ) -> ChardlePuzzle:
        pool = await load_pool(
            db,
            tier.classes,
            allow_sentinels=tier.allow_sentinels,
            level=level,
            side=side,
        )
        if not pool:
            raise EmptyPool
        answer = self._rng.choice(pool)
        columns = select_columns(pool, answer, max_columns=max_columns, rng=self._rng)
        puzzle = ChardlePuzzle(
            song_difficulty_id=answer.difficulty_id,
            clue_columns=[str(clue) for clue in columns],
            max_attempts=attempts,
            puzzle_number=number,
            tier=tier.name,
            filters=filters,
        )
        db.add(puzzle)
        await db.flush()
        return puzzle


def _filters(level: int | None, side: int | None) -> dict | None:
    chosen = {"level": level, "side": side}
    present = {key: value for key, value in chosen.items() if value is not None}
    return present or None
