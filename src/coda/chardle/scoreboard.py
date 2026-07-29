"""Today's daily, as one guild sees it.

DB-only and Discord-free, so the renderer is the only thing that changes if the
text board is ever replaced by an image one.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from coda.chardle import board as board_builder
from coda.chardle import render, tiers
from coda.chardle.feedback import Windows
from coda.chardle.views import DailyScoreboard, ScoreboardEntry
from coda.db.enums import ChardleState
from coda.db.models import ChardlePuzzle, ChardleSession
from coda.settings import ConfigService


async def build(
    db: AsyncSession,
    settings: ConfigService,
    *,
    guild_id: int,
    puzzle: ChardlePuzzle,
) -> DailyScoreboard:
    """Every daily session opened in this guild for this puzzle."""
    sessions = list(
        (
            await db.execute(
                select(ChardleSession)
                .where(
                    ChardleSession.puzzle_id == puzzle.id,
                    ChardleSession.guild_id == guild_id,
                    ChardleSession.is_daily.is_(True),
                )
                .order_by(ChardleSession.started_at)
            )
        )
        .scalars()
        .all()
    )
    shared_names = await board_builder.load_shared_names(db)
    entries = [
        await _entry(db, settings, session, puzzle, shared_names)
        for session in sessions
    ]
    return DailyScoreboard(
        puzzle_number=puzzle.puzzle_number,
        tier_label=board_builder.tier_label(tiers.get(puzzle.tier), puzzle),
        max_attempts=puzzle.max_attempts,
        entries=sorted(entries, key=_rank),
        resets_at=max(
            (s.expires_at for s in sessions if s.expires_at is not None), default=None
        ),
    )


async def _entry(
    db: AsyncSession,
    settings: ConfigService,
    session: ChardleSession,
    puzzle: ChardlePuzzle,
    shared_names: set[str],
) -> ScoreboardEntry:
    board = await board_builder.build(
        db,
        puzzle,
        session,
        await _windows(db, settings, session),
        shared_names=shared_names,
    )
    finished = session.state is not ChardleState.PLAYING
    return ScoreboardEntry(
        discord_id=session.discord_id,
        state=session.state,
        taken=len(board.rows),
        grid=[render.cells(row.cells) for row in board.rows] if finished else None,
    )


async def _windows(
    db: AsyncSession, settings: ConfigService, session: ChardleSession
) -> Windows:
    """Resolved per player, not once per scoreboard: the bpm/note windows are
    scoped settings, so two people in one guild can legitimately hold different
    ones and a shared value would draw a grid neither of them saw."""

    async def value(key: str) -> int:
        return int(
            await settings.resolve(
                db,
                key,
                guild_id=session.guild_id,
                channel_id=session.board_channel_id,
                user_id=session.discord_id,
                is_dm=session.guild_id is None,
            )
        )

    return Windows(bpm=await value("chardle_bpm_window"), note=await value("chardle_note_window"))


_STATE_ORDER = {ChardleState.WON: 0, ChardleState.PLAYING: 1, ChardleState.LOST: 2}


def _rank(entry: ScoreboardEntry) -> tuple[int, int]:
    """Solved first and fewest-guesses-first, then whoever is still going, then
    the losses -- where more guesses means got further, not did worse."""
    if entry.state is ChardleState.LOST:
        return _STATE_ORDER[entry.state], -entry.taken
    return _STATE_ORDER[entry.state], entry.taken
