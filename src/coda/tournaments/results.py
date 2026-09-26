"""Who won a round. The only place a score is read.

Ranking is raw ``score``, ties break on earlier ``time_played``, and that is
all: no play rating, no CC, no clear bonus, no gauge, on any tier. The query
below joins none of those columns, which makes the rule structural rather than
a policy someone has to remember -- there is nothing in scope to weight a play
by. It is also what makes a round tier-agnostic: every field it needs is on the
friend path.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from coda.db.models import (
    PlayScore,
    TournamentChart,
    TournamentParticipant,
    TournamentRound,
)


@dataclass(frozen=True)
class Standing:
    """One participant's answer to one round. ``rank`` is None when they never
    played -- a no-score is a row the board draws, never an omission."""

    arcaea_account_id: int
    side_index: int
    score: int | None
    time_played: int | None
    song_difficulty_id: int | None

    @property
    def scored(self) -> bool:
        return self.score is not None


async def standings(db: AsyncSession, round_: TournamentRound) -> list[Standing]:
    """Every participant, ranked, highest first, no-scores last."""
    if round_.start_ms is None or round_.end_ms is None:
        rows = await _participants(db, round_.match_id)
        return [Standing(account, side, None, None, None) for account, side in rows]

    charts = select(TournamentChart.song_difficulty_id).where(
        TournamentChart.round_id == round_.id
    )
    counting = and_(
        PlayScore.arcaea_account_id == TournamentParticipant.arcaea_account_id,
        PlayScore.song_difficulty_id.in_(charts),
        PlayScore.time_played >= round_.start_ms,
        PlayScore.time_played <= round_.end_ms,
    )
    rows = await db.execute(
        select(
            TournamentParticipant.arcaea_account_id,
            TournamentParticipant.side_index,
            PlayScore.score,
            PlayScore.time_played,
            PlayScore.song_difficulty_id,
        )
        # LEFT: a participant who never played must still reach the board.
        .outerjoin(PlayScore, counting)
        .where(TournamentParticipant.match_id == round_.match_id)
        .distinct(TournamentParticipant.arcaea_account_id)
        # The FIRST valid play is the one that counts, so the DISTINCT ON picks
        # the earliest -- a later play is never read, whatever it scored.
        .order_by(
            TournamentParticipant.arcaea_account_id,
            PlayScore.time_played.asc().nullslast(),
        )
    )
    return rank([Standing(*row) for row in rows.all()])


def rank(rows: list[Standing]) -> list[Standing]:
    """Highest score first, earlier play breaking a tie, no-scores last."""
    return sorted(
        rows,
        key=lambda s: (
            s.score is None,
            -(s.score or 0),
            s.time_played if s.time_played is not None else 0,
        ),
    )


def winner_side(rows: list[Standing]) -> tuple[int | None, bool]:
    """``(side, tied)``. A tie on both score and time_played has no winner.

    Identical ``time_played`` to the millisecond is the only way this happens
    on a real pair of plays, so the tie is a genuine draw rather than a
    tie-break that was not tried.
    """
    scored = [row for row in rows if row.scored]
    if not scored:
        return None, False
    best = scored[0]
    contenders = [
        row
        for row in scored
        if row.score == best.score and row.time_played == best.time_played
    ]
    if len(contenders) > 1:
        return None, True
    return best.side_index, False


def all_scored(rows: list[Standing]) -> bool:
    """Whether every participant has a valid score -- the early ``open -> grace``
    exit, past which no further play can change any result."""
    return bool(rows) and all(row.scored for row in rows)


async def _participants(db: AsyncSession, match_id: int) -> list[tuple[int, int]]:
    rows = await db.execute(
        select(
            TournamentParticipant.arcaea_account_id, TournamentParticipant.side_index
        ).where(TournamentParticipant.match_id == match_id)
    )
    return [(row[0], row[1]) for row in rows.all()]
