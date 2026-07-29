"""Resolving a typed guess to a chart, and recording it.

Deterministic and picker-free: naming the right song always counts, an ambiguous
title cycles through its readings, and anything unresolvable is free. Chardle
owns no matching of its own — ranking is ``SearchService``'s.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from coda.catalog.labels import CLASS_ORDER
from coda.catalog.query import parse
from coda.catalog.search import (
    ChartHit,
    ChartList,
    ChartPick,
    DidYouMean,
    Resolution,
    SearchService,
    SongDupes,
    SongHit,
)
from coda.chardle.tiers import Tier
from coda.db.enums import ChardleState
from coda.db.models import ChardleGuess, ChardlePuzzle, ChardleSession, SongDifficulty


@dataclass(frozen=True)
class Invalid:
    """No playable reading of what they typed. Costs nothing."""

    reason: str


@dataclass(frozen=True)
class Duplicate:
    """Already on this board. Costs nothing."""


@dataclass(frozen=True)
class Searched:
    """A level or filter query — a search over the catalog, not a song name.

    Always free, *including* when it narrows to a single chart: the player was
    describing what they remember, not naming a song, and silently spending an
    attempt on a query that happened to be specific is impossible to undo.
    """

    count: int
    truncated: bool = False

    def describe(self) -> str:
        if not self.count:
            return "Nothing matches that."
        if self.count == 1 and not self.truncated:
            return "1 chart matches — name a song to guess."
        total = f"{self.count}+" if self.truncated else str(self.count)
        return f"{total} charts match — name a song to guess."


@dataclass(frozen=True)
class Accepted:
    difficulty_id: int
    state: ChardleState


Outcome = Invalid | Duplicate | Searched | Accepted

_NO_MATCH = "No song by that name."
_NOT_PLAYABLE = "That song has no chart in this puzzle's difficulty."

_ANSWER_TERM_SQL = text(
    """
    SELECT 1 FROM search_index
    WHERE lower(term) = :q AND song_id = :song_id
    LIMIT 1
    """
)


class GuessService:
    """Stateless; takes an ``AsyncSession`` per call."""

    def __init__(self, search: SearchService | None = None) -> None:
        self._search = search or SearchService()

    async def submit(
        self,
        db: AsyncSession,
        puzzle: ChardlePuzzle,
        session: ChardleSession,
        tier: Tier,
        typed: str,
        *,
        discord_id: int,
    ) -> Outcome:
        """Resolve ``typed``, append it to the board if it costs an attempt."""
        parsed = parse(typed)
        if parsed.error is not None:
            return Invalid(parsed.error)

        played = await self._board_charts(db, session.id)

        if await self._names_answer(db, puzzle, typed):
            return await self._win(db, puzzle, session, played, discord_id)

        resolution = await self._search.resolve(
            db, typed, include_hidden=tier.include_hidden
        )
        if parsed.filters or isinstance(resolution, ChartList):
            return _searched(resolution)

        song_ids, chart_ids, exact_tier = _candidate_refs(resolution)
        song_ids = await self._widen_to_songs(db, song_ids, chart_ids)
        if not song_ids:
            return Invalid(_NO_MATCH)

        charts = await self._playable_charts(db, song_ids, puzzle, tier)
        if not charts:
            return Invalid(_NOT_PLAYABLE)

        if puzzle.song_difficulty_id in charts:
            return await self._win(db, puzzle, session, played, discord_id)

        chosen = _pick(charts, played, cycling=exact_tier)
        if chosen is None:
            return Duplicate()
        return await self._record(db, puzzle, session, chosen, played, discord_id)

    async def _win(
        self,
        db: AsyncSession,
        puzzle: ChardlePuzzle,
        session: ChardleSession,
        played: list[int],
        discord_id: int,
    ) -> Outcome:
        """Naming the answer, whichever rule got here.

        Recording the answer sets ``won``, so a board holding it is finished and
        the caller should never reach this — but let it be a duplicate rather
        than a unique-violation traceback if one does.
        """
        if puzzle.song_difficulty_id in played:
            return Duplicate()
        return await self._record(
            db, puzzle, session, puzzle.song_difficulty_id, played, discord_id
        )

    async def _names_answer(
        self, db: AsyncSession, puzzle: ChardlePuzzle, typed: str
    ) -> bool:
        """Rule 0: naming the answer wins even when the catalog has since cloaked
        it. Exact tier only — a fuzzy match here would hand the win to a
        near-miss."""
        song_id = await db.scalar(
            select(SongDifficulty.song_id).where(
                SongDifficulty.id == puzzle.song_difficulty_id
            )
        )
        hit = await db.execute(
            _ANSWER_TERM_SQL, {"q": typed.strip().lower(), "song_id": song_id}
        )
        return hit.first() is not None

    async def _board_charts(self, db: AsyncSession, session_id: int) -> list[int]:
        rows = await db.execute(
            select(ChardleGuess.song_difficulty_id)
            .where(ChardleGuess.session_id == session_id)
            .order_by(ChardleGuess.ordinal)
        )
        return list(rows.scalars().all())

    async def _widen_to_songs(
        self, db: AsyncSession, song_ids: list[str], chart_ids: list[int]
    ) -> list[str]:
        """A chart-shaped match still names a song, and the puzzle's own
        difficulty overrides whichever one they typed."""
        if chart_ids:
            rows = await db.execute(
                select(SongDifficulty.id, SongDifficulty.song_id).where(
                    SongDifficulty.id.in_(chart_ids)
                )
            )
            by_id = {chart_id: song_id for chart_id, song_id in rows.all()}
            song_ids = song_ids + [
                by_id[chart_id] for chart_id in chart_ids if chart_id in by_id
            ]
        return list(dict.fromkeys(song_ids))

    async def _playable_charts(
        self,
        db: AsyncSession,
        song_ids: list[str],
        puzzle: ChardlePuzzle,
        tier: Tier,
    ) -> list[int]:
        """The puzzle's difficulty is forced onto every guess, so each candidate
        song contributes at most one chart — or none, which drops it."""
        result = await db.execute(
            select(SongDifficulty).where(
                SongDifficulty.song_id.in_(song_ids),
                SongDifficulty.difficulty.in_(tier.classes),
            )
        )
        rows = result.scalars().all()
        by_song: dict[str, list[SongDifficulty]] = {}
        for chart in rows:
            by_song.setdefault(chart.song_id, []).append(chart)

        order = {klass: i for i, klass in enumerate(CLASS_ORDER)}
        charts: list[int] = []
        for song_id in song_ids:
            options = by_song.get(song_id)
            if not options:
                continue
            ids = [chart.id for chart in options]
            if puzzle.song_difficulty_id in ids:
                charts.append(puzzle.song_difficulty_id)
                continue
            options.sort(key=lambda c: (order.get(c.difficulty, 99), c.id))
            charts.append(options[0].id)
        return charts

    async def _record(
        self,
        db: AsyncSession,
        puzzle: ChardlePuzzle,
        session: ChardleSession,
        difficulty_id: int,
        played: list[int],
        discord_id: int,
    ) -> Accepted:
        ordinal = len(played) + 1
        db.add(
            ChardleGuess(
                session_id=session.id,
                ordinal=ordinal,
                song_difficulty_id=difficulty_id,
                discord_id=discord_id,
            )
        )
        state = _state_after(puzzle, difficulty_id, ordinal)
        if state is not ChardleState.PLAYING:
            session.state = state
            session.finished_at = datetime.now(UTC)
        await db.commit()
        return Accepted(difficulty_id, state)


def _state_after(
    puzzle: ChardlePuzzle, difficulty_id: int, ordinal: int
) -> ChardleState:
    if difficulty_id == puzzle.song_difficulty_id:
        return ChardleState.WON
    if puzzle.max_attempts is not None and ordinal >= puzzle.max_attempts:
        return ChardleState.LOST
    return ChardleState.PLAYING


def _pick(charts: list[int], played: list[int], *, cycling: bool) -> int | None:
    """The next reading not already on the board, or ``None`` for a duplicate.

    Cycling walks the exact-match tier only. Unbounded, retyping a song already
    guessed would skip to an unrelated fuzzy candidate and charge for a song the
    player never named.
    """
    if not cycling:
        return None if charts[0] in played else charts[0]
    remaining = [chart for chart in charts if chart not in played]
    return remaining[0] if remaining else None


def _searched(resolution: Resolution) -> Searched:
    """How many charts the query named, whatever shape the resolver returned."""
    match resolution:
        case ChartList(difficulty_ids=ids, truncated=truncated):
            return Searched(len(ids), truncated)
        case ChartHit():
            return Searched(1)
        case _:
            return Searched(0)


def _candidate_refs(resolution: Resolution) -> tuple[list[str], list[int], bool]:
    """Candidates in rank order, plus whether they came from the exact tier (the
    only tier cycling may walk).

    ``ChartList`` never reaches here — ``submit`` answers it with ``Searched``.
    """
    match resolution:
        case SongHit(song_id=song_id):
            return [song_id], [], True
        case SongDupes(song_ids=song_ids):
            return list(song_ids), [], True
        case ChartHit(difficulty_id=difficulty_id):
            return [], [difficulty_id], True
        case ChartPick(difficulty_ids=difficulty_ids):
            return [], list(difficulty_ids), True
        case DidYouMean(candidates=candidates):
            return [c.song_id for c in candidates], [], False
        case _:
            return [], [], True
