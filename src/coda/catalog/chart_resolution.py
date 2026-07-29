"""Resolve a wire ``(song_id, difficulty)`` to a ``song_difficulties.id``.

This is the join key the score paths hand us (``arcaea-score-mapping.md`` §4).
Order matters: the ``game_song_id`` match MUST come first, because a consolidated
entry like Last | Eternity arrives on the wire as ``song_id: "lasteternity"`` --
a value that exists in no ``songs`` row of ours -- and would fall through the
normal lookup and silently drop a real play.

Returns the row id, or ``None`` for an unknown chart. ``None`` is routine, not an
error: a song can ship in-game before our catalog is seeded, and our ``song_id``
may drift from the game's. The caller stores the play unresolved and a reconcile
pass backfills it later.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from coda.db.enums import DifficultyClass
from coda.db.models import SongDifficulty


async def resolve_chart(
    db: AsyncSession, wire_song_id: str, wire_difficulty: int
) -> int | None:
    """Return the ``song_difficulties.id`` for a wire score, or ``None``."""
    # Step 1: consolidated entry, keyed by game_song_id. Only such rows carry a
    # game_song_id, and each is single-chart in-game, so the match is unique --
    # the wire difficulty int is NOT a usable guard here: byd_2 arrives as int 3
    # (byd) while the row's class is byd_2, so filtering on it would exclude the
    # very row this step exists to catch.
    consolidated = await db.scalar(
        select(SongDifficulty.id).where(
            SongDifficulty.game_song_id == wire_song_id
        )
    )
    if consolidated is not None:
        return consolidated

    # Step 2: normal chart. Our song_id mirrors the game's (may drift -> a miss
    # here, which is a routine staleness signal, not a crash).
    difficulty = DifficultyClass.from_ordinal(wire_difficulty)
    if difficulty is None:
        return None  # wire int outside 0-4: nothing legitimate maps here

    return await db.scalar(
        select(SongDifficulty.id).where(
            SongDifficulty.song_id == wire_song_id,
            SongDifficulty.difficulty == difficulty,
        )
    )
