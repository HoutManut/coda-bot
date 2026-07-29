"""Assembling a renderable board from its rows.

Feedback is recomputed here on every render rather than stored: it is a pure
function of (guess, answer, column), so persisting it would duplicate catalog
data the admin editor can edit underneath it.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from coda.chardle import tiers
from coda.chardle.columns import in_render_order
from coda.chardle.facts import ChartFacts, load_facts
from coda.chardle.feedback import Windows, evaluate
from coda.chardle.views import Board, BoardRow
from coda.db.models import (
    ChardleGuess,
    ChardlePuzzle,
    ChardleSession,
    Song,
    SongDifficulty,
)
from coda.utils.encoding import decode_level


async def build(
    db: AsyncSession,
    puzzle: ChardlePuzzle,
    session: ChardleSession,
    windows: Windows,
    *,
    shared_names: set[str] | None = None,
) -> Board:
    """Everything the renderers need, read fresh from the catalog.

    ``shared_names`` is catalog-wide and identical for every board: pass it when
    building several at once so its group-by runs once, not per board.
    """
    columns = in_render_order(puzzle.clue_columns)
    guessed_ids = list(
        (
            await db.execute(
                select(ChardleGuess.song_difficulty_id)
                .where(ChardleGuess.session_id == session.id)
                .order_by(ChardleGuess.ordinal)
            )
        )
        .scalars()
        .all()
    )
    facts = await load_facts(db, [puzzle.song_difficulty_id, *guessed_ids])
    answer = facts[puzzle.song_difficulty_id]
    if shared_names is None:
        shared_names = await load_shared_names(db)

    rows = [
        _row(facts[chart_id], answer, columns, windows, shared_names)
        for chart_id in guessed_ids
        if chart_id in facts
    ]
    tier = tiers.get(puzzle.tier)
    return Board(
        tier=tier.name,
        tier_label=tier_label(tier, puzzle),
        columns=columns,
        rows=rows,
        max_attempts=puzzle.max_attempts,
        state=session.state,
        answer=answer,
        puzzle_number=puzzle.puzzle_number,
        filters_note=_filters_note(puzzle),
    )


def _row(
    guess: ChartFacts,
    answer: ChartFacts,
    columns,
    windows: Windows,
    shared_names: set[str],
) -> BoardRow:
    # No jacket on a text board, so the label is the only thing separating two
    # rows that a cycled ambiguous title left both reading "Quon".
    label = guess.pack_name if guess.name.lower() in shared_names else None
    return BoardRow(
        name=guess.name,
        label=label,
        cells=[evaluate(clue, guess, answer, windows) for clue in columns],
        facts=guess,
    )


async def load_shared_names(db: AsyncSession) -> set[str]:
    """Lowercased titles that more than one song answers to."""
    # Read off the effective name, not songs.name_en: a per-difficulty override
    # renames the chart on the board (Ignotus -> Ignotus Afterburn), so comparing
    # a row's rendered name against song titles alone both misses a collision
    # between two overrides and claims one for a chart that renamed itself out of
    # the clash. Counted over distinct *songs*: a song's own difficulties share a
    # title and cannot both appear, because GuessService._playable_charts
    # contributes at most one chart per song_id -- including Last, whose two
    # Beyonds are both in the byd pool.
    name = func.lower(func.coalesce(SongDifficulty.name_en, Song.name_en))
    rows = (
        await db.execute(
            select(name)
            .join(Song, Song.song_id == SongDifficulty.song_id)
            .group_by(name)
            .having(func.count(func.distinct(SongDifficulty.song_id)) > 1)
        )
    ).all()
    return {value for (value,) in rows}


def tier_label(tier: tiers.Tier, puzzle: ChardlePuzzle) -> str:
    """What the board says it is, e.g. ``Future 10+``. Also the thread name."""
    filters = puzzle.filters or {}
    level = filters.get("level")
    if level is None:
        return tier.label
    return f"{tier.label} {decode_level(level)}"


def _filters_note(puzzle: ChardlePuzzle) -> str | None:
    if not puzzle.filters:
        return None
    return "Filtered board — not counted in stats."
