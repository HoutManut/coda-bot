"""Compute a player's potential on demand from accumulated ``play_scores``.

The 7.0 model: the best 50 play ratings ever, one entry per chart, with that
pool's own top 10 counted a second time, divided by 60 (``potential.md``). r10
and the recent pool are gone, so nothing here is path-dependent -- the result is
a function of stored rows alone.

It is still an ESTIMATE, for two reasons that have nothing to do with the
formula. The bot only knows plays it has observed since registration, and a
tier-1 (friend-path) row carries no ``clear_type``, so its clear bonus rests on
a heuristic (``d-clear-bonus-impossible-friend-path``). Never correct the result
toward the server's own ``rating`` -- divergence is expected, not a defect.

Nothing here is cached or stored -- a chart's CC can refine, and an override can
flip, so a stored rating (or a stored potential) would go stale silently.
Computed fresh every call from an indexed scan of one account's rows, which is
cheap at this project's scale.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from coda.arcaea.dto.enums import ClearType
from coda.catalog.search import is_delisted
from coda.db.models import PlayScore, Song, SongDifficulty
from coda.utils.encoding import decode_rating
from coda.utils.scoring import (
    ClearBasis,
    ClearStatus,
    calculate_play_rating,
    resolve_clear,
)

# Hard ceiling on the requested limit -- "what to target next" views reach past
# the pool, but not without bound.
_MAX_LIMIT = 100

# The counted pool, and the slice of it that counts twice.
POOL = 50
_DOUBLED = 10

# POOL + _DOUBLED. Live-wire confirmed 2026-08-31 against an account's own
# aggregate rating; the /50 alternative missed by 0.04, ruling out coincidence.
_DIVISOR = 60


@dataclass(frozen=True)
class PotentialEntry:
    """One ranked chart. Always resolved -- delisted/TBA/unresolved charts
    never reach this type, they are dropped or counted before it."""

    song_difficulty: SongDifficulty
    song: Song
    play_score_id: int
    score: int
    play_rating: float
    clear: ClearStatus
    rank: int  # 1-based place in the full ranking
    counted: bool


@dataclass(frozen=True)
class PotentialResult:
    entries: list[PotentialEntry]  # up to `limit`, ranked by play_rating desc
    limit: int
    pool_sum: float  # always the true top-50, independent of `limit`
    top_sum: float  # the top-10 within that pool, counted a second time
    assumed_count: int  # counted entries whose clear status is a heuristic guess
    tba_excluded_count: int
    unresolved_excluded_count: int
    # 1-based position of `rank_for_difficulty_id` in the FULL ranking, which
    # can sit far past `limit`. None when unrequested or the chart has no
    # ranked score.
    requested_rank: int | None = None

    @property
    def potential(self) -> float:
        """The PTT-scale average.

        Always the full divisor, even when the pool is underfilled -- unfilled
        slots contribute 0, mirroring the game. Confirmed pre-7.0 and assumed to
        carry forward; the account that confirmed the divisor had a full pool,
        so the underfilled case is inference (``h-7.0-potential-rework`` §2).
        """
        return (self.pool_sum + self.top_sum) / _DIVISOR


@dataclass(frozen=True)
class _Candidate:
    """A chart's winning row, before its rank (and so its weight) is known."""

    chart: SongDifficulty
    song: Song
    play_score_id: int
    score: int
    play_rating: float
    clear: ClearStatus
    time_played: int


@dataclass(frozen=True)
class _Row:
    """One stored play, narrowed to what the ranking reads."""

    play_score_id: int
    difficulty_id: int | None
    wire_song_id: str
    wire_difficulty: int
    score: int
    clear_type: ClearType | None
    clear_override: bool | None
    time_played: int


def _rank_in(candidates: list[_Candidate], difficulty_id: int | None) -> int | None:
    """1-based place of a chart in the already-sorted candidate list."""
    if difficulty_id is None:
        return None
    for position, candidate in enumerate(candidates, start=1):
        if candidate.chart.id == difficulty_id:
            return position
    return None


class PotentialService:
    """Stateless; takes the session per call, like TrackingService."""

    async def compute(
        self,
        db: AsyncSession,
        account_id: int,
        limit: int = POOL,
        exclude_score_id: int | None = None,
        rank_for_difficulty_id: int | None = None,
    ) -> PotentialResult:
        """``exclude_score_id`` answers "potential as if that one play never happened".

        ``rank_for_difficulty_id`` reports one chart's place in the full ranking
        -- read off the same sorted pass, so a rank of 200 costs no more than a
        rank of 3 and needs no second query.
        """
        limit = min(limit, _MAX_LIMIT)

        rows, unresolved_excluded_count = await self._rows(
            db, account_id, exclude_score_id
        )
        charts = await self._load_charts(
            db, {row.difficulty_id for row in rows if row.difficulty_id is not None}
        )
        candidates, tba_excluded_count = self._rank(rows, charts)

        pool = candidates[:POOL]
        return PotentialResult(
            entries=[
                PotentialEntry(
                    candidate.chart,
                    candidate.song,
                    candidate.play_score_id,
                    candidate.score,
                    candidate.play_rating,
                    candidate.clear,
                    rank=position + 1,
                    counted=position < POOL,
                )
                for position, candidate in enumerate(candidates[:limit])
            ],
            limit=limit,
            pool_sum=sum(candidate.play_rating for candidate in pool),
            top_sum=sum(candidate.play_rating for candidate in candidates[:_DOUBLED]),
            assumed_count=sum(
                1 for c in pool if c.clear.basis is ClearBasis.ASSUMED
            ),
            tba_excluded_count=tba_excluded_count,
            unresolved_excluded_count=unresolved_excluded_count,
            requested_rank=_rank_in(candidates, rank_for_difficulty_id),
        )

    def _rank(
        self,
        rows: list[_Row],
        charts: dict[int, tuple[SongDifficulty, Song]],
    ) -> tuple[list[_Candidate], int]:
        """Every chart's best-RATED row, ranked, plus a TBA-chart count.

        Ranking on resolved rating rather than raw score is load-bearing, not a
        refinement: the clear bonus can make a lower-scoring real clear outrank a
        higher-scoring assumed one, so picking a chart's entry by MAX(score)
        selects the wrong PLAY, not merely a slightly wrong number for the right
        one (``d-clear-bonus-impossible-friend-path``).
        """
        best: dict[int, _Candidate] = {}
        tba: set[int] = set()
        for row in rows:
            if row.difficulty_id is None:
                continue
            chart, song = charts[row.difficulty_id]
            if is_delisted(song):
                continue
            if chart.rating <= 0:
                tba.add(chart.id)
                continue
            clear = resolve_clear(row.clear_type, row.clear_override, row.score)
            rating = calculate_play_rating(
                row.score, decode_rating(chart.rating), cleared=clear.cleared
            )
            candidate = _Candidate(
                chart, song, row.play_score_id, row.score, rating, clear, row.time_played
            )
            # Ties to the earliest play: that is the run that set the record, the
            # same rule best_play applies.
            current = best.get(chart.id)
            if current is None or (rating, -row.time_played) > (
                current.play_rating,
                -current.time_played,
            ):
                best[chart.id] = candidate

        candidates = sorted(
            best.values(), key=lambda c: (-c.play_rating, c.song.name_en.lower())
        )
        return candidates, len(tba)

    async def _rows(
        self, db: AsyncSession, account_id: int, exclude_score_id: int | None = None
    ) -> tuple[list[_Row], int]:
        """Every stored play for the account, plus a count of distinct
        unresolved wire charts (``song_difficulty_id IS NULL``).

        Every row, not a MAX(score) per chart: which row wins depends on clear
        status, which the query cannot resolve -- see :meth:`_rank`.
        """
        query = select(
            PlayScore.id,
            PlayScore.song_difficulty_id,
            PlayScore.wire_song_id,
            PlayScore.wire_difficulty,
            PlayScore.score,
            PlayScore.clear_type,
            PlayScore.clear_override,
            PlayScore.time_played,
        ).where(PlayScore.arcaea_account_id == account_id)
        if exclude_score_id is not None:
            query = query.where(PlayScore.id != exclude_score_id)
        result = await db.execute(query)

        rows = [_Row(*values) for values in result]
        unresolved = {
            (row.wire_song_id, row.wire_difficulty)
            for row in rows
            if row.difficulty_id is None
        }
        return rows, len(unresolved)

    async def _load_charts(
        self, db: AsyncSession, difficulty_ids: Iterable[int]
    ) -> dict[int, tuple[SongDifficulty, Song]]:
        ids = list(difficulty_ids)
        if not ids:
            return {}
        rows = await db.execute(
            select(SongDifficulty, Song)
            .join(Song, Song.song_id == SongDifficulty.song_id)
            .where(SongDifficulty.id.in_(ids))
        )
        return {chart.id: (chart, song) for chart, song in rows}
