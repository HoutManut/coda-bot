"""Streaks, guess distribution and the guild leaderboard.

All derived on read — no denormalised stats table. Only dailies count, which is
just ``puzzle_number IS NOT NULL``; a custom challenge is ineligible by
construction because filters can only sit on a non-daily.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from coda.chardle.tiers import ERR_TIER
from coda.db.enums import ChardleState
from coda.db.models import ChardleGuess, ChardlePuzzle, ChardleSession


@dataclass(frozen=True)
class PlayerStats:
    played: int
    solved: int
    current_streak: int
    longest_streak: int
    distribution: dict[int, int] = field(default_factory=dict)

    @property
    def win_rate(self) -> float:
        return self.solved / self.played if self.played else 0.0


class StatsService:
    """Stateless; takes an ``AsyncSession`` per call."""

    async def player(
        self, db: AsyncSession, discord_id: int, *, current_number: int | None = None
    ) -> PlayerStats:
        rows = (
            await db.execute(
                select(
                    ChardlePuzzle.puzzle_number,
                    ChardlePuzzle.tier,
                    ChardleSession.state,
                )
                .join(ChardlePuzzle, ChardlePuzzle.id == ChardleSession.puzzle_id)
                .where(
                    ChardleSession.discord_id == discord_id,
                    ChardlePuzzle.puzzle_number.is_not(None),
                )
            )
        ).all()
        solved = sorted(
            number for number, tier, state in rows if _counts_for_streak(tier, state)
        )
        return PlayerStats(
            played=len(rows),
            solved=len(solved),
            current_streak=_current_streak(solved, current_number),
            longest_streak=_longest_streak(solved),
            distribution=await self._distribution(db, discord_id),
        )

    async def _distribution(
        self, db: AsyncSession, discord_id: int
    ) -> dict[int, int]:
        """Solve-in-N over won dailies. err dailies are excluded — a histogram
        denominated in 6 cannot hold a 3-attempt result."""
        guesses = (
            select(
                ChardleGuess.session_id.label("session_id"),
                func.count().label("taken"),
            )
            .group_by(ChardleGuess.session_id)
            .subquery()
        )
        rows = (
            await db.execute(
                select(guesses.c.taken, func.count())
                .select_from(ChardleSession)
                .join(ChardlePuzzle, ChardlePuzzle.id == ChardleSession.puzzle_id)
                .join(guesses, guesses.c.session_id == ChardleSession.id)
                .where(
                    ChardleSession.discord_id == discord_id,
                    ChardleSession.state == ChardleState.WON,
                    ChardlePuzzle.puzzle_number.is_not(None),
                    ChardlePuzzle.tier != ERR_TIER,
                )
                .group_by(guesses.c.taken)
            )
        ).all()
        return {int(taken): int(count) for taken, count in rows}

    async def leaderboard(
        self, db: AsyncSession, guild_id: int, *, limit: int = 10
    ) -> list[tuple[int, int]]:
        """(discord_id, dailies solved), best first.

        Stats themselves are global — solving in DMs counts. ``guild_id`` is only
        the membership filter, and "has played here" is the membership proxy: the
        real member list needs a privileged intent this bot does not request.
        """
        members = (
            select(ChardleSession.discord_id)
            .where(
                ChardleSession.guild_id == guild_id,
                ChardleSession.discord_id.is_not(None),
            )
            .distinct()
            .subquery()
        )
        rows = (
            await db.execute(
                select(ChardleSession.discord_id, func.count())
                .join(ChardlePuzzle, ChardlePuzzle.id == ChardleSession.puzzle_id)
                .where(
                    ChardleSession.discord_id.in_(select(members.c.discord_id)),
                    ChardlePuzzle.puzzle_number.is_not(None),
                    (ChardleSession.state == ChardleState.WON)
                    | (ChardlePuzzle.tier == ERR_TIER),
                )
                .group_by(ChardleSession.discord_id)
                .order_by(func.count().desc())
                .limit(limit)
            )
        ).all()
        return [(int(user), int(count)) for user, count in rows]


def _counts_for_streak(tier: str, state: ChardleState) -> bool:
    """An *attempted* err daily advances the streak whether it was won or lost.
    April-1-only exception: it forgives losing the joke, not skipping it."""
    return state is ChardleState.WON or tier == ERR_TIER


def _current_streak(solved: list[int], current_number: int | None) -> int:
    """The trailing run, but only while it is still live.

    Without ``current_number`` a player who solved #1-#5 and then stopped would
    read "streak 5" forever; today's puzzle being unplayed yet is not a break,
    so the run survives one gap.
    """
    if not solved:
        return 0
    if current_number is not None and solved[-1] < current_number - 1:
        return 0
    streak = 1
    for index in range(len(solved) - 1, 0, -1):
        if solved[index] - solved[index - 1] != 1:
            break
        streak += 1
    return streak


def _longest_streak(solved: list[int]) -> int:
    longest = current = 0
    previous: int | None = None
    for number in solved:
        current = current + 1 if previous is not None and number - previous == 1 else 1
        longest = max(longest, current)
        previous = number
    return longest
