"""Play-rating maths and the best-50 pool.

Every assertion here regresses silently: a wrong bonus, a wrong divisor or a
wrongly-selected row all produce a plausible number, never an error. The clear
bonus in particular makes rating non-monotone in score, so the row a chart is
represented by is now a real decision rather than a MAX() -- see
``d-clear-bonus-impossible-friend-path``.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from coda.arcaea.dto.enums import ClearType
from coda.db.enums import DifficultyClass
from coda.db.models import PlayScore, Song, SongDifficulty
from coda.scores.clears import reviewable
from coda.scores.potential import (
    POOL,
    PotentialEntry,
    PotentialResult,
    PotentialService,
)
from coda.utils.scoring import (
    AA,
    EX,
    PURE_MEMORY,
    ClearBasis,
    ClearStatus,
    calculate_play_rating,
    resolve_clear,
)


# --- play rating ------------------------------------------------------------


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (AA, 10.0),
        (EX, 11.0),
        (PURE_MEMORY, 12.0),
        (9_900_000, 11.5),
    ],
)
def test_base_formula_at_the_boundaries(score: int, expected: float) -> None:
    assert calculate_play_rating(score, 10.0, cleared=False) == expected


@pytest.mark.parametrize("score", [AA, EX, 9_900_000, PURE_MEMORY])
def test_the_clear_bonus_is_flat_across_the_whole_score_range(score: int) -> None:
    """Confirmed live 2026-08-31: not scaled by score, CC or formula segment."""
    failed = calculate_play_rating(score, 10.0, cleared=False)
    cleared = calculate_play_rating(score, 10.0, cleared=True)
    assert round(cleared - failed, 5) == 0.2


def test_a_rating_never_goes_negative_even_with_the_bonus() -> None:
    assert calculate_play_rating(0, 1.0, cleared=True) == 0.0
    assert calculate_play_rating(0, 1.0, cleared=False) == 0.0


# --- clear resolution -------------------------------------------------------


def test_wire_clear_type_beats_an_override() -> None:
    """A wire clear_type is fact, so an override on that row is stale, not a fix."""
    status = resolve_clear(ClearType.CLEAR, False, 100)
    assert status.cleared
    assert status.basis is ClearBasis.WIRE


def test_track_lost_is_the_only_wire_type_that_loses_the_bonus() -> None:
    assert not resolve_clear(ClearType.TRACK_LOST, None, PURE_MEMORY).cleared
    for clear_type in ClearType:
        if clear_type is not ClearType.TRACK_LOST:
            assert resolve_clear(clear_type, None, 0).cleared


def test_an_override_beats_the_heuristic() -> None:
    assert resolve_clear(None, False, PURE_MEMORY) == ClearStatus(
        False, ClearBasis.OVERRIDE
    )
    assert resolve_clear(None, True, 0) == ClearStatus(True, ClearBasis.OVERRIDE)


def test_the_heuristic_threshold_sits_at_nine_million() -> None:
    assert not resolve_clear(None, None, 8_999_999).cleared
    assert resolve_clear(None, None, 9_000_000).cleared
    assert resolve_clear(None, None, 9_000_000).basis is ClearBasis.ASSUMED


# --- the pool ---------------------------------------------------------------


async def _chart(db: AsyncSession, index: int, cc: float) -> SongDifficulty:
    """One song with one Future chart, at a CC of ``cc``."""
    song_id = f"potentialtest{index}"
    db.add(
        Song(
            song_id=song_id,
            idx=900_000 + index,
            pack_name="test",
            name_en=song_id,
            name_jp="",
            artist="test",
            bpm="100",
            bpm_base=100.0,
            time=100,
            side=0,
            bg="",
            date=0,
            version="1.0",
            jacket="",
        )
    )
    # Flushed before the chart: the project declares no relationship() anywhere,
    # so SQLAlchemy has no FK dependency to order these two inserts by.
    await db.flush()
    chart = SongDifficulty(
        song_id=song_id,
        difficulty=DifficultyClass.FTR,
        level=10,
        rating=round(cc * 10),
        note=1000,
    )
    db.add(chart)
    await db.flush()
    return chart


async def _play(
    db: AsyncSession,
    account_id: int,
    chart: SongDifficulty,
    score: int,
    *,
    time_played: int = 1,
    clear_type: ClearType | None = None,
    clear_override: bool | None = None,
) -> PlayScore:
    play = PlayScore(
        arcaea_account_id=account_id,
        wire_song_id=chart.song_id,
        wire_difficulty=2,
        score=score,
        time_played=time_played,
        song_difficulty_id=chart.id,
        clear_type=clear_type,
        clear_override=clear_override,
        source="friend",
    )
    db.add(play)
    await db.flush()
    return play


async def test_potential_divides_by_sixty_with_the_top_ten_counted_twice(
    db: AsyncSession, make_account
) -> None:
    account = await make_account(910_001, "910000001")
    # 12 charts at descending CC, every score a PM, so each play rating is
    # cc + 2 + 0.2 and the expected sums are arithmetic rather than a fixture.
    ratings = []
    for index in range(12):
        chart = await _chart(db, index, 11.0 - index * 0.1)
        await _play(db, account.id, chart, PURE_MEMORY)
        ratings.append(round(11.0 - index * 0.1, 5) + 2 + 0.2)
    ratings.sort(reverse=True)

    result = await PotentialService().compute(db, account.id)

    assert result.pool_sum == pytest.approx(sum(ratings))
    assert result.top_sum == pytest.approx(sum(ratings[:10]))
    assert result.potential == pytest.approx(
        (sum(ratings) + sum(ratings[:10])) / 60
    )


async def test_an_underfilled_pool_still_divides_by_sixty(
    db: AsyncSession, make_account
) -> None:
    """Unfilled slots contribute 0, mirroring the game -- never divide by the
    number of entries actually held."""
    account = await make_account(910_002, "910000002")
    chart = await _chart(db, 100, 10.0)
    await _play(db, account.id, chart, PURE_MEMORY)

    result = await PotentialService().compute(db, account.id)

    # One entry, in the pool and in its top 10, so it is counted twice.
    assert result.potential == pytest.approx(12.2 * 2 / 60)


async def test_the_pool_takes_one_entry_per_chart(
    db: AsyncSession, make_account
) -> None:
    account = await make_account(910_003, "910000003")
    chart = await _chart(db, 200, 10.0)
    await _play(db, account.id, chart, 9_500_000, time_played=1)
    await _play(db, account.id, chart, PURE_MEMORY, time_played=2)

    result = await PotentialService().compute(db, account.id)

    assert len(result.entries) == 1
    assert result.entries[0].score == PURE_MEMORY


async def test_a_higher_score_does_not_win_a_chart_when_it_rates_lower(
    db: AsyncSession, make_account
) -> None:
    """The worked example from d-clear-bonus-impossible-friend-path.

    9,900,000 as a wire-known fail rates 11.5; 9,890,000 as a wire-known clear
    rates 11.65. Selecting the chart's entry by MAX(score) picks the wrong PLAY,
    not merely a wrong number for the right one.
    """
    account = await make_account(910_004, "910000004")
    chart = await _chart(db, 300, 10.0)
    await _play(
        db, account.id, chart, 9_900_000, time_played=1, clear_type=ClearType.TRACK_LOST
    )
    await _play(
        db, account.id, chart, 9_890_000, time_played=2, clear_type=ClearType.CLEAR
    )

    result = await PotentialService().compute(db, account.id)

    assert result.entries[0].score == 9_890_000
    assert result.entries[0].play_rating == pytest.approx(11.65)


async def test_an_override_can_promote_a_previously_buried_row(
    db: AsyncSession, make_account
) -> None:
    """Both rows are tier-1, so both are assumed cleared and the higher score
    wins. Marking that row a fail must re-pick the chart's entry, not just
    restate the loser's rating."""
    account = await make_account(910_005, "910000005")
    chart = await _chart(db, 400, 10.0)
    higher = await _play(db, account.id, chart, 9_900_000, time_played=1)
    await _play(db, account.id, chart, 9_890_000, time_played=2)

    before = await PotentialService().compute(db, account.id)
    assert before.entries[0].score == 9_900_000
    assert before.assumed_count == 1

    higher.clear_override = False
    await db.flush()

    after = await PotentialService().compute(db, account.id)
    assert after.entries[0].score == 9_890_000
    assert after.entries[0].play_rating == pytest.approx(11.65)


async def test_a_tba_chart_is_excluded_and_counted_never_rated_from_a_sentinel(
    db: AsyncSession, make_account
) -> None:
    account = await make_account(910_006, "910000006")
    tba = await _chart(db, 500, 0.0)
    await _play(db, account.id, tba, PURE_MEMORY)

    result = await PotentialService().compute(db, account.id)

    assert result.entries == []
    assert result.tba_excluded_count == 1
    assert result.potential == 0.0


async def test_a_limit_never_changes_the_sums_it_only_truncates_the_entries(
    db: AsyncSession, make_account
) -> None:
    account = await make_account(910_007, "910000007")
    for index in range(5):
        chart = await _chart(db, 600 + index, 10.0 + index)
        await _play(db, account.id, chart, PURE_MEMORY)

    full = await PotentialService().compute(db, account.id, limit=POOL)
    clipped = await PotentialService().compute(db, account.id, limit=2)

    assert len(clipped.entries) == 2
    assert clipped.pool_sum == pytest.approx(full.pool_sum)
    assert clipped.potential == pytest.approx(full.potential)


# --- the review queue -------------------------------------------------------


def _entry(basis: ClearBasis, *, rank: int = 1, counted: bool = True) -> PotentialEntry:
    """A ranked entry, narrowed to the two fields the queue filter reads."""
    return PotentialEntry(
        song_difficulty=SongDifficulty(),
        song=Song(),
        play_score_id=rank,
        score=PURE_MEMORY,
        play_rating=12.2,
        clear=ClearStatus(True, basis),
        rank=rank,
        counted=counted,
    )


def _result(entries: list[PotentialEntry]) -> PotentialResult:
    return PotentialResult(
        entries=entries,
        limit=POOL,
        pool_sum=0.0,
        top_sum=0.0,
        assumed_count=0,
        tba_excluded_count=0,
        unresolved_excluded_count=0,
    )


def test_a_wire_confirmed_row_is_never_asked_about() -> None:
    """lowiro already said. Neither mode may put it to the owner."""
    result = _result([_entry(ClearBasis.WIRE)])
    assert reviewable(result, "unconfirmed") == []
    assert reviewable(result, "all") == []


def test_an_answered_row_leaves_the_queue_but_stays_correctable() -> None:
    """`all` is the only way back to an override -- without it, answering a row
    (or accepting every guess at once) would be a one-way door."""
    result = _result([_entry(ClearBasis.OVERRIDE)])
    assert reviewable(result, "unconfirmed") == []
    assert len(reviewable(result, "all")) == 1


def test_only_counted_entries_are_asked_about() -> None:
    """A play outside the pool contributes nothing, so it asks nothing. This is
    what bounds the queue to pool size rather than to play history."""
    result = _result(
        [
            _entry(ClearBasis.ASSUMED, rank=1),
            _entry(ClearBasis.ASSUMED, rank=POOL + 1, counted=False),
        ]
    )
    assert [entry.rank for entry in reviewable(result, "unconfirmed")] == [1]


def test_the_queue_keeps_the_pool_ranking() -> None:
    entries = [_entry(ClearBasis.ASSUMED, rank=rank) for rank in (1, 2, 3)]
    assert reviewable(_result(entries), "unconfirmed") == entries


async def test_entries_carry_their_place_in_the_ranking(
    db: AsyncSession, make_account
) -> None:
    account = await make_account(910_008, "910000008")
    for index in range(3):
        chart = await _chart(db, 700 + index, 10.0 + index)
        await _play(db, account.id, chart, PURE_MEMORY)

    result = await PotentialService().compute(db, account.id)

    assert [entry.rank for entry in result.entries] == [1, 2, 3]
    assert all(entry.counted for entry in result.entries)
