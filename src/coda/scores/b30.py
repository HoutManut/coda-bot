"""Compute a player's best-30 on demand from accumulated ``play_scores``.

b30 is a pure function of best-ever score per chart -- no r10, no recent-pool
admission rules, no ``clear_type``/``modifier`` checks. Play rating is monotone
non-decreasing in score for a fixed CC, so max score per chart == max rating
per chart (``handoff-09-b30.md``). Never call this PTT: PTT also averages in
r10, which is impossible to reconstruct on the friend path
(``d-r10-impossible-friend-path``).

Nothing here is cached or stored -- a chart's CC can refine, so a stored
rating (or a stored b30) would go stale silently. Computed fresh every call
from an indexed scan of one account's rows, which is cheap at this project's
scale.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from coda.catalog.search import is_delisted
from coda.db.models import PlayScore, Song, SongDifficulty
from coda.utils.encoding import decode_rating
from coda.utils.scoring import calculate_play_rating

# Hard ceiling on the requested limit -- b40/b50-style "what to target next"
# views are the use case, not an unbounded dump.
_MAX_LIMIT = 50

# How many top entries actually count toward the b30 sum, regardless of how
# many were requested.
_COUNTED = 30


@dataclass(frozen=True)
class B30Entry:
    """One ranked chart. Always resolved -- delisted/TBA/unresolved charts
    never reach this type, they are dropped or counted before it."""

    song_difficulty: SongDifficulty
    song: Song
    score: int
    play_rating: float
    counts_toward_b30: bool


@dataclass(frozen=True)
class B30Result:
    entries: list[B30Entry]  # up to `limit`, ranked by play_rating desc
    limit: int
    b30_sum: float  # always the true top-30, independent of `limit`
    tba_excluded_count: int
    unresolved_excluded_count: int
    # 1-based position of `rank_for_difficulty_id` in the FULL ranking, which
    # can sit far past `limit`. None when unrequested or the chart has no
    # ranked score.
    requested_rank: int | None = None


def _rank_in(
    candidates: list[tuple[SongDifficulty, Song, int, float]],
    difficulty_id: int | None,
) -> int | None:
    """1-based place of a chart in the already-sorted candidate list."""
    if difficulty_id is None:
        return None
    for position, (chart, *_) in enumerate(candidates, start=1):
        if chart.id == difficulty_id:
            return position
    return None


class B30Service:
    """Stateless; takes the session per call, like TrackingService."""

    async def compute(
        self,
        db: AsyncSession,
        account_id: int,
        limit: int = 30,
        exclude_score_id: int | None = None,
        rank_for_difficulty_id: int | None = None,
    ) -> B30Result:
        """``exclude_score_id`` answers "b30 as if that one play never happened".

        ``rank_for_difficulty_id`` reports one chart's place in the full ranking
        -- read off the same sorted pass, so a rank of 200 costs no more than a
        rank of 3 and needs no second query.
        """
        limit = min(limit, _MAX_LIMIT)

        best_by_chart, unresolved_excluded_count = await self._best_scores(
            db, account_id, exclude_score_id
        )
        charts = await self._load_charts(db, best_by_chart.keys())

        # (chart, song, score, play_rating) -- ranked before B30Entry exists,
        # since counts_toward_b30 depends on the rank we're computing.
        candidates: list[tuple[SongDifficulty, Song, int, float]] = []
        tba_excluded_count = 0
        for difficulty_id, score in best_by_chart.items():
            chart, song = charts[difficulty_id]
            if is_delisted(song):
                continue
            if chart.rating <= 0:
                tba_excluded_count += 1
                continue
            rating = calculate_play_rating(score, decode_rating(chart.rating))
            candidates.append((chart, song, score, rating))

        candidates.sort(key=lambda c: (-c[3], c[1].name_en.lower()))
        b30_sum = sum(rating for *_, rating in candidates[:_COUNTED])
        entries = [
            B30Entry(chart, song, score, rating, i < _COUNTED)
            for i, (chart, song, score, rating) in enumerate(candidates[:limit])
        ]

        return B30Result(
            entries=entries,
            limit=limit,
            b30_sum=b30_sum,
            tba_excluded_count=tba_excluded_count,
            unresolved_excluded_count=unresolved_excluded_count,
            requested_rank=_rank_in(candidates, rank_for_difficulty_id),
        )

    async def _best_scores(
        self, db: AsyncSession, account_id: int, exclude_score_id: int | None = None
    ) -> tuple[dict[int, int], int]:
        """Max score per resolved ``song_difficulty_id``, plus a count of
        distinct unresolved wire charts (``song_difficulty_id IS NULL``)."""
        query = select(
            PlayScore.song_difficulty_id,
            PlayScore.wire_song_id,
            PlayScore.wire_difficulty,
            PlayScore.score,
        ).where(PlayScore.arcaea_account_id == account_id)
        if exclude_score_id is not None:
            query = query.where(PlayScore.id != exclude_score_id)
        rows = await db.execute(query)
        best: dict[int, int] = {}
        unresolved: set[tuple[str, int]] = set()
        for difficulty_id, wire_song_id, wire_difficulty, score in rows:
            if difficulty_id is None:
                unresolved.add((wire_song_id, wire_difficulty))
                continue
            if score > best.get(difficulty_id, -1):
                best[difficulty_id] = score
        return best, len(unresolved)

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
