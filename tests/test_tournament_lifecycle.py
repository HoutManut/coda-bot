"""A match from draft to closed, driven only by inserted scores.

This is the module's central design claim under test: the tournament layer
never calls the lowiro API, so a whole match must be playable by writing
``play_scores`` rows and letting the sweep run. Nothing here mocks HTTP because
nothing here can reach it.
"""

from __future__ import annotations

from datetime import datetime, timezone

from unittest.mock import patch

import pytest
from sqlalchemy import select

from coda.catalog import spoilers
from coda.db.enums import (
    DifficultyClass,
    MatchState,
    PoolEntryState,
    RoundState,
    ThreadVisibility,
)
from coda.db.models import (
    PlayScore,
    SongDifficulty,
    TournamentChart,
    TournamentPoolEntry,
)
from coda.db.enums import LinkMethod
from coda.tournaments import announce
from coda.tournaments import cadence
from coda.tournaments import match as match_ops
from coda.tournaments import prompts, render, results, service, viewbuild
from coda.tournaments.constants import BREAK_SECONDS, WINDOW_SECONDS
from coda.tournaments.levels import parse_level_range
from coda.tournaments.match import MatchOptions, now_ms
from coda.tournaments.pickban import turn_at


def options(**overrides) -> MatchOptions:
    base = dict(
        levels=parse_level_range("9-10+"),
        difficulty_class=DifficultyClass.FTR,
        best_of=3,
        pick_ban=True,
        open_join=False,
        visibility=ThreadVisibility.PRIVATE,
    )
    return MatchOptions(**{**base, **overrides})


@pytest.fixture
async def crew(db, make_account):
    await spoilers.refresh(db)
    alice = await make_account(900_001, "900000001")
    bob = await make_account(900_002, "900000002")
    return alice, bob


async def open_match(db, crew, **opts):
    alice, bob = crew
    return await match_ops.create(
        db,
        guild_id=1,
        home_channel_id=2,
        thread_id=3,
        creator_discord_id=4,
        roster=[alice.id, bob.id],
        options=options(**opts),
    )


async def play(db, account_id: int, difficulty_id: int, score: int, at: int) -> None:
    chart = await db.get(SongDifficulty, difficulty_id)
    db.add(
        PlayScore(
            arcaea_account_id=account_id,
            wire_song_id=chart.song_id,
            wire_difficulty=0,
            song_difficulty_id=difficulty_id,
            score=score,
            time_played=at,
            source="friend",
        )
    )
    await db.flush()


async def draft_bans(db, match) -> None:
    """Run the two bans off the front of the sequence."""
    await act_next(db, match)
    await act_next(db, match)


async def act_next(db, match):
    """Take whichever turn is owed, on the first entry still on the table."""
    available = await match_ops.entries(
        db, match.id, state=PoolEntryState.AVAILABLE)
    await match_ops.act(db, match, available[0], auto=False)
    return available[0]


async def finish_round(
    db, match, winner_id: int, loser_id: int, *, wait_out_break: bool = True
) -> None:
    """Play one round out and land the clock past its grace and the break.

    The whole window is back-dated rather than just its end: moving ``end_ms``
    alone would put it before ``start_ms``, and the plays written inside the
    window would stop counting.
    """
    await service.tick(db)
    round_ = next(
        r for r in await service.rounds(db, match.id) if r.state == RoundState.OPEN
    )
    window = round_.end_ms - round_.start_ms
    over = BREAK_SECONDS * 1000 + 1 if wait_out_break else 0
    round_.end_ms = now_ms() - round_.grace_ms - over
    round_.start_ms = round_.end_ms - window
    await db.flush()

    chart = await db.scalar(
        select(TournamentChart.song_difficulty_id).where(
            TournamentChart.round_id == round_.id)
    )
    await play(db, winner_id, chart, 9_900_000, round_.start_ms + 10)
    await play(db, loser_id, chart, 9_000_000, round_.start_ms + 20)

    await service.tick(db)   # open -> grace
    await service.tick(db)   # grace -> closed
    assert round_.state == RoundState.CLOSED

    # A round records when it ACTUALLY closed, and the break is measured from
    # that. Back-dating the window alone would leave the break running from
    # real now, and the next round would never open.
    round_.closed_ms = round_.end_ms + round_.grace_ms
    await db.flush()


class TestStart:
    async def test_pool_is_sized_for_the_format(self, db, crew):
        match = await open_match(db, crew)
        assert await match_ops.start(db, match) is None
        assert len(await match_ops.entries(db, match.id)) == 5
        assert match.state == MatchState.PICKBAN

    async def test_impossible_filters_refuse_and_change_nothing(self, db, crew):
        match = await open_match(
            db, crew, difficulty_class=DifficultyClass.ETR,
            levels=parse_level_range("12"))
        shortfall = await match_ops.start(db, match)
        assert shortfall is not None and shortfall.needed == 5
        assert match.state == MatchState.DRAFT
        assert await match_ops.entries(db, match.id) == []

    async def test_banning_off_goes_straight_to_playing(self, db, crew):
        match = await open_match(db, crew, pick_ban=False)
        assert await match_ops.start(db, match) is None
        assert match.state == MatchState.PLAYING
        assert len(await service.rounds(db, match.id)) == 3


class TestPickBan:
    async def test_bans_are_drafted_up_front_and_the_first_pick_follows(
        self, db, crew
    ):
        """Only the bans run back to back. The first pick is asked for
        immediately after them because there is nothing to play yet."""
        match = await open_match(db, crew)
        await match_ops.start(db, match)
        await act_next(db, match)
        assert match.state == MatchState.PICKBAN
        await act_next(db, match)

        assert match.state == MatchState.PICKBAN
        assert turn_at(match.turn_index, match.best_of).action == "pick"
        entries = await match_ops.entries(db, match.id)
        assert sum(e.state == PoolEntryState.BANNED for e in entries) == 2
        assert await service.rounds(db, match.id) == []

    async def test_a_pick_hands_the_match_back_to_play(self, db, crew):
        """One pick, one round: the chart just named is played before the next
        is asked for."""
        match = await open_match(db, crew)
        await match_ops.start(db, match)
        await draft_bans(db, match)
        await act_next(db, match)

        assert match.state == MatchState.PLAYING
        assert match.turn_deadline_ms is None
        assert len(await service.rounds(db, match.id)) == 1
        assert await match_ops.turn_owed(db, match) is True

    async def test_the_next_pick_is_served_between_rounds(self, db, crew):
        alice, bob = crew
        match = await open_match(db, crew)
        await match_ops.start(db, match)
        await draft_bans(db, match)
        await act_next(db, match)
        await finish_round(db, match, alice.id, bob.id)

        await service.tick(db)
        assert match.state == MatchState.PICKBAN
        assert turn_at(match.turn_index, match.best_of).action == "pick"
        assert match.turn_deadline_ms is not None

    async def test_the_second_pick_is_the_other_side(self, db, crew):
        """Sides alternate across the whole sequence, so interleaving cannot
        hand one player both picks."""
        alice, bob = crew
        match = await open_match(db, crew, best_of=5)
        await match_ops.start(db, match)
        await draft_bans(db, match)
        first = turn_at(match.turn_index, match.best_of).side_index
        await act_next(db, match)
        await finish_round(db, match, alice.id, bob.id)
        await service.tick(db)

        assert turn_at(match.turn_index, match.best_of).side_index != first

    async def test_a_pick_answers_the_score(self, db, crew):
        """The whole point of Path A: the pool the picker chooses from is
        smaller, and the scoreboard is already on the board when they do."""
        alice, bob = crew
        match = await open_match(db, crew, best_of=5)
        await match_ops.start(db, match)
        await draft_bans(db, match)
        await act_next(db, match)
        await finish_round(db, match, alice.id, bob.id)
        await service.tick(db)

        # The score is on the board before the pick is asked for, and the pool
        # to pick from has shrunk by the chart already played.
        assert list((await service.wins(db, match.id)).values()) == [1]
        assert len(await match_ops.entries(
            db, match.id, state=PoolEntryState.AVAILABLE)) == 4

    async def test_the_decider_plays_last(self, db, crew):
        alice, bob = crew
        match = await open_match(db, crew)
        await match_ops.start(db, match)
        await draft_bans(db, match)
        survivor = (await match_ops.entries(
            db, match.id, state=PoolEntryState.AVAILABLE))[-1]

        await act_next(db, match)
        await finish_round(db, match, alice.id, bob.id)
        await service.tick(db)
        await act_next(db, match)

        await db.refresh(survivor)
        rounds = await service.rounds(db, match.id)
        assert len(rounds) == 3
        assert survivor.round_id == rounds[-1].id

    async def test_an_expired_turn_auto_acts(self, db, crew):
        match = await open_match(db, crew)
        await match_ops.start(db, match)
        match.turn_deadline_ms = now_ms() - 1
        await db.flush()

        changed = await service.tick(db)
        assert match.id in changed.touched
        assert match.turn_index == 1
        acted = await db.scalar(
            select(TournamentPoolEntry).where(
                TournamentPoolEntry.match_id == match.id,
                TournamentPoolEntry.state != PoolEntryState.AVAILABLE,
            )
        )
        assert acted.auto is True


class TestWindow:
    async def test_first_round_opens_without_waiting(self, db, crew):
        match = await open_match(db, crew, pick_ban=False)
        await match_ops.start(db, match)
        await service.tick(db)

        first = (await service.rounds(db, match.id))[0]
        assert first.state == RoundState.OPEN
        assert first.end_ms - first.start_ms == WINDOW_SECONDS * 1000

    async def test_the_window_is_flat_whatever_the_chart(self, db, crew):
        """No longer derived from chart length. Under `first` the window ends
        when both sides have scored, so it never has to fit two plays."""
        match = await open_match(db, crew, pick_ban=False)
        await match_ops.start(db, match)
        await service.tick(db)
        for round_ in await service.rounds(db, match.id):
            if round_.state == RoundState.OPEN:
                assert round_.end_ms - round_.start_ms == WINDOW_SECONDS * 1000

    async def test_a_later_round_cannot_be_banked_during_an_earlier_one(
        self, db, crew
    ):
        """Every chart is picked before round one opens, so an anchor earlier
        than the round's own open would let a player put a score on round
        three's chart while round one was still running."""
        alice, bob = crew
        match = await open_match(db, crew, pick_ban=False)
        await match_ops.start(db, match)
        await service.tick(db)
        rounds = await service.rounds(db, match.id)
        later = rounds[1]
        chart = await db.scalar(
            select(TournamentChart.song_difficulty_id).where(
                TournamentChart.round_id == later.id)
        )

        await play(db, alice.id, chart, 9_990_000, rounds[0].start_ms + 10)
        assert later.start_ms is None
        assert not any(
            row.scored for row in await results.standings(db, later))


class TestBreak:
    async def test_the_break_runs_from_the_result_not_the_window(self, db, crew):
        """It is a beat to read the result in, so it cannot begin before the
        scores are gathered: it starts past grace, never past end_ms."""
        alice, bob = crew
        match = await open_match(db, crew, pick_ban=False)
        await match_ops.start(db, match)
        await service.tick(db)
        first = (await service.rounds(db, match.id))[0]
        chart = await db.scalar(
            select(TournamentChart.song_difficulty_id).where(
                TournamentChart.round_id == first.id)
        )
        await play(db, alice.id, chart, 9_900_000, first.start_ms + 10)
        await play(db, bob.id, chart, 9_000_000, first.start_ms + 20)

        # Past the window and its grace, but one tick short of the break.
        first.end_ms = now_ms() - first.grace_ms - BREAK_SECONDS * 1000 + 5_000
        first.start_ms = first.end_ms - WINDOW_SECONDS * 1000
        await db.flush()
        await service.tick(db)   # open -> grace
        await service.tick(db)   # grace -> closed
        assert first.state == RoundState.CLOSED
        first.closed_ms = first.end_ms + first.grace_ms
        await db.flush()

        second = (await service.rounds(db, match.id))[1]
        await service.tick(db)
        assert second.state == RoundState.PENDING, "the break was skipped"

        first.end_ms -= 6_000
        first.start_ms = first.end_ms - WINDOW_SECONDS * 1000
        first.closed_ms = first.end_ms + first.grace_ms
        await db.flush()
        await service.tick(db)
        assert second.state == RoundState.OPEN

    async def test_everyone_ready_ends_the_break_early(self, db, crew):
        alice, bob = crew
        match = await open_match(db, crew, pick_ban=False)
        await match_ops.start(db, match)
        await finish_round(db, match, alice.id, bob.id, wait_out_break=False)

        second = (await service.rounds(db, match.id))[1]
        await service.tick(db)
        assert second.state == RoundState.PENDING

        for participant in await match_ops.roster(db, match.id):
            participant.ready_at = datetime.now(timezone.utc)
        await db.flush()
        await service.tick(db)
        assert second.state == RoundState.OPEN

    async def test_the_rest_is_served_before_the_pick(self, db, crew):
        """A turn is the LAST thing between two rounds, never the first.

        Serving it on the result overlapped the pick with the rest and cost no
        wall clock, but it left a Ready to press after the pick -- and a player
        who has just chosen their chart expects to play it, so that ask is the
        one that gets missed.
        """
        alice, bob = crew
        match = await open_match(db, crew)
        await match_ops.start(db, match)
        await draft_bans(db, match)
        await act_next(db, match)
        await finish_round(db, match, alice.id, bob.id, wait_out_break=False)

        await service.tick(db)
        assert match.state == MatchState.PLAYING, "the pick jumped the rest"
        assert match.turn_deadline_ms is None

        view = await viewbuild.build(db, match)
        assert view.phase == "break", "a rest before an unnamed round is a rest"
        assert view.turn is None

        for participant in await match_ops.roster(db, match.id):
            participant.ready_at = datetime.now(timezone.utc)
        await db.flush()
        await service.tick(db)
        assert match.state == MatchState.PICKBAN, "Ready did not serve the pick"

    async def test_a_pick_opens_its_round_with_nothing_left_to_press(
        self, db, crew
    ):
        """The whole point of the reorder: pick, then play.

        The Ready flags that ended the rest are deliberately left standing, so
        the sweep that follows the pick opens the round it just named instead
        of asking for a second confirmation of a rest already spent.
        """
        alice, bob = crew
        match = await open_match(db, crew)
        await match_ops.start(db, match)
        await draft_bans(db, match)
        await act_next(db, match)
        await finish_round(db, match, alice.id, bob.id, wait_out_break=False)

        for participant in await match_ops.roster(db, match.id):
            participant.ready_at = datetime.now(timezone.utc)
        await db.flush()
        await service.tick(db)
        assert match.state == MatchState.PICKBAN

        await act_next(db, match)
        await service.tick(db)
        second = (await service.rounds(db, match.id))[1]
        assert second.state == RoundState.OPEN, "a pick still waited on Ready"

        view = await viewbuild.build(db, match)
        assert view.phase == "open"
        assert prompts.current(view) is None, "an ask outlived the pick"

    async def test_a_spent_rest_is_not_a_break(self, db, crew):
        """A pending round whose predecessor closed long ago is the state a
        match sits in for the seconds between a pick and the sweep. Calling
        that a break posts a Ready prompt counting down to a moment already
        past -- the exact ask this ordering deletes."""
        alice, bob = crew
        match = await open_match(db, crew)
        await match_ops.start(db, match)
        await draft_bans(db, match)
        await act_next(db, match)
        await finish_round(db, match, alice.id, bob.id)

        await service.tick(db)
        assert match.state == MatchState.PICKBAN
        await act_next(db, match)

        view = await viewbuild.build(db, match)
        assert view.phase is None, "the spent rest read as a break"
        assert prompts.current(view) is None

    async def test_opening_a_round_clears_ready(self, db, crew):
        """A new wait begins, so a Ready carried over from the last break must
        not skip the next one before it is offered."""
        alice, bob = crew
        match = await open_match(db, crew, pick_ban=False)
        await match_ops.start(db, match)
        for participant in await match_ops.roster(db, match.id):
            participant.ready_at = datetime.now(timezone.utc)
        await db.flush()

        await service.tick(db)
        assert all(
            p.ready_at is None for p in await match_ops.roster(db, match.id))

    async def test_a_play_outside_the_window_does_not_count(self, db, crew):
        alice, bob = crew
        match = await open_match(db, crew, pick_ban=False)
        await match_ops.start(db, match)
        await service.tick(db)
        round_ = (await service.rounds(db, match.id))[0]
        chart = await db.scalar(
            select(TournamentChart.song_difficulty_id).where(
                TournamentChart.round_id == round_.id)
        )

        await play(db, alice.id, chart, 9_900_000, round_.end_ms + 1)
        assert not results.all_scored(await results.standings(db, round_))

        await play(db, bob.id, chart, 9_800_000, round_.start_ms)
        rows = await results.standings(db, round_)
        assert [r.arcaea_account_id for r in rows] == [bob.id, alice.id]
        assert rows[1].score is None

    async def test_only_the_first_play_counts(self, db, crew):
        alice, bob = crew
        match = await open_match(db, crew, pick_ban=False)
        await match_ops.start(db, match)
        await service.tick(db)
        round_ = (await service.rounds(db, match.id))[0]
        chart = await db.scalar(
            select(TournamentChart.song_difficulty_id).where(
                TournamentChart.round_id == round_.id)
        )

        await play(db, alice.id, chart, 9_500_000, round_.start_ms + 10)
        await play(db, alice.id, chart, 9_900_000, round_.start_ms + 20)
        rows = {r.arcaea_account_id: r for r in await results.standings(db, round_)}
        assert rows[alice.id].score == 9_500_000


class TestFinish:
    async def test_all_scored_closes_the_window_early(self, db, crew):
        alice, bob = crew
        match = await open_match(db, crew, pick_ban=False)
        await match_ops.start(db, match)
        await service.tick(db)
        round_ = (await service.rounds(db, match.id))[0]
        chart = await db.scalar(
            select(TournamentChart.song_difficulty_id).where(
                TournamentChart.round_id == round_.id)
        )
        await play(db, alice.id, chart, 9_900_000, round_.start_ms + 10)
        await play(db, bob.id, chart, 9_800_000, round_.start_ms + 20)

        await service.tick(db)
        assert round_.state == RoundState.CLOSED
        # Early is the whole claim: it never reached its own deadline.
        assert round_.closed_ms < round_.end_ms

    async def test_taking_the_needed_wins_closes_the_match(self, db, crew):
        alice, bob = crew
        match = await open_match(db, crew, pick_ban=False)
        await match_ops.start(db, match)

        for _ in range(match_ops.wins_needed(match.best_of)):
            await finish_round(db, match, alice.id, bob.id)

        assert await service.wins(db, match.id) == {0: 2}
        assert match.state == MatchState.CLOSED

    async def test_a_gap_between_rounds_is_not_the_end_of_the_match(
        self, db, crew
    ):
        """The trap interleaving sets: with the picks spread out there is a
        moment when every round is closed and none is pending, and reading that
        as "nothing left" would close a Bo3 at 1-0."""
        alice, bob = crew
        match = await open_match(db, crew)
        await match_ops.start(db, match)
        await draft_bans(db, match)
        await act_next(db, match)
        await finish_round(db, match, alice.id, bob.id)

        await service.tick(db)
        assert match.state == MatchState.PICKBAN
        assert list((await service.wins(db, match.id)).values()) == [1]

    async def test_a_picked_match_runs_all_the_way_to_a_winner(self, db, crew):
        alice, bob = crew
        match = await open_match(db, crew)
        await match_ops.start(db, match)
        await draft_bans(db, match)
        await act_next(db, match)
        await finish_round(db, match, alice.id, bob.id)
        await service.tick(db)
        await act_next(db, match)
        await finish_round(db, match, alice.id, bob.id)

        assert match.state == MatchState.CLOSED
        assert list((await service.wins(db, match.id)).values()) == [2]
        decider = (await service.rounds(db, match.id))[-1]
        assert decider.state == RoundState.CANCELLED

    async def test_a_decided_match_never_asks_for_another_pick(self, db, crew):
        """A Bo5 taken 3-0 leaves three turns in the sequence. None is served:
        picking charts for rounds nobody will play is exactly the drafting
        Path A exists to stop."""
        alice, bob = crew
        match = await open_match(db, crew, best_of=5)
        await match_ops.start(db, match)
        await draft_bans(db, match)
        for _ in range(match_ops.wins_needed(match.best_of)):
            await act_next(db, match)
            await finish_round(db, match, alice.id, bob.id)
            await service.tick(db)

        assert match.state == MatchState.CLOSED
        assert turn_at(match.turn_index, match.best_of) is not None
        assert await match_ops.entries(
            db, match.id, state=PoolEntryState.AVAILABLE) != []

    async def test_a_match_that_never_picks_is_owed_no_turn(self, db, crew):
        """``turn_index`` never leaves 0 without pick/ban, and the sequence
        alone would read that as a ban still owed -- which would stop every
        such match from ever closing."""
        match = await open_match(db, crew, pick_ban=False)
        await match_ops.start(db, match)
        assert turn_at(match.turn_index, match.best_of) is not None
        assert await match_ops.turn_owed(db, match) is False

    async def test_unplayed_rounds_are_never_opened(self, db, crew):
        alice, bob = crew
        match = await open_match(db, crew, pick_ban=False)
        await match_ops.start(db, match)
        for _ in range(2):
            await finish_round(db, match, alice.id, bob.id)

        third = (await service.rounds(db, match.id))[2]
        assert third.state == RoundState.CANCELLED
        assert third.start_ms is None


class TestSongMode:
    async def test_a_round_holds_every_qualifying_difficulty(self, db, crew):
        match = await open_match(
            db, crew, difficulty_class=None, pick_ban=False,
            levels=parse_level_range("8-11"), best_of=1)
        assert await match_ops.start(db, match) is None
        round_ = (await service.rounds(db, match.id))[0]

        entry = (await match_ops.entries(db, match.id))[0]
        assert entry.song_difficulty_id is None

        rows = await db.execute(
            select(SongDifficulty)
            .join(TournamentChart,
                  TournamentChart.song_difficulty_id == SongDifficulty.id)
            .where(TournamentChart.round_id == round_.id)
        )
        charts = list(rows.scalars())
        assert charts, "song mode must resolve to at least one chart"
        assert {c.song_id for c in charts} == {entry.song_id}
        assert all(16 <= c.level <= 22 for c in charts), \
            "the level band still bounds a casual set"

    async def test_two_sides_on_different_difficulties_both_rank(self, db, crew):
        alice, bob = crew
        # Any level, so the whole of whatever song is drawn qualifies -- every
        # song carries at least PST/PRS/FTR, which makes this deterministic.
        match = await open_match(
            db, crew, difficulty_class=None, pick_ban=False,
            levels=parse_level_range("any"), best_of=1)
        await match_ops.start(db, match)
        await service.tick(db)
        round_ = (await service.rounds(db, match.id))[0]
        rows = await db.execute(
            select(TournamentChart.song_difficulty_id).where(
                TournamentChart.round_id == round_.id)
        )
        charts = list(rows.scalars())
        assert len(charts) >= 2, "a song mode round offers the player a choice"

        await play(db, alice.id, charts[0], 9_800_000, round_.start_ms + 10)
        await play(db, bob.id, charts[1], 9_900_000, round_.start_ms + 20)
        standings = await results.standings(db, round_)
        assert [r.arcaea_account_id for r in standings] == [bob.id, alice.id]


class TestCadence:
    async def test_an_open_round_makes_its_roster_hot(self, db, crew):
        alice, bob = crew
        match = await open_match(db, crew, pick_ban=False)
        await match_ops.start(db, match)
        assert await cadence.hot_accounts(db) == set()

        await service.tick(db)
        assert await cadence.hot_accounts(db) == {alice.id, bob.id}

    async def test_a_closed_match_leaves_the_hot_set(self, db, crew):
        alice, bob = crew
        match = await open_match(db, crew, pick_ban=False, best_of=1)
        await match_ops.start(db, match)
        await finish_round(db, match, alice.id, bob.id)

        assert match.state == MatchState.CLOSED
        assert await cadence.hot_accounts(db) == set()

    async def test_a_cancelled_match_stops_matching(self, db, crew):
        match = await open_match(db, crew, pick_ban=False)
        await match_ops.start(db, match)
        await service.tick(db)
        assert await cadence.hot_accounts(db)

        await service.cancel(db, match)
        assert await cadence.hot_accounts(db) == set()

    async def test_the_query_never_names_a_bot_account(self, db, crew):
        """Roster entries are arcaea_account_id; what polls them is the
        session layer's business and must not leak up here."""
        match = await open_match(db, crew, pick_ban=False)
        await match_ops.start(db, match)
        await service.tick(db)
        assert all(isinstance(i, int) for i in await cadence.hot_accounts(db))


class TestSweepIsolation:
    async def test_a_wedged_match_does_not_stall_the_others(self, db, crew):
        """The sweep is the only thing that makes the clock run, so one match
        that cannot advance must cost only itself."""
        wedged = await open_match(db, crew, pick_ban=False)
        healthy = await open_match(db, crew, pick_ban=False)
        await match_ops.start(db, wedged)
        await match_ops.start(db, healthy)

        real = service._advance_rounds

        async def explode(session, match, changed):
            if match.id == wedged.id:
                changed.note(match.id)
                raise RuntimeError("boom")
            await real(session, match, changed)

        with patch.object(service, "_advance_rounds", explode):
            changed = await service.tick(db)

        assert healthy.id in changed.touched
        assert (await service.rounds(db, healthy.id))[0].state == RoundState.OPEN
        # Rolled back to the savepoint: not redrawn, and not half-advanced.
        assert wedged.id not in changed.touched
        assert (await service.rounds(db, wedged.id))[0].state == RoundState.PENDING


class TestBeats:
    """The two messages a round owes its thread.

    A beat is stamped only once the message lands, so an unposted beat stays
    owed -- including the final result, whose match has already left the live
    set by the time it is announced.
    """

    async def test_an_open_round_owes_its_reveal(self, db, crew):
        match = await open_match(db, crew, pick_ban=False)
        await match_ops.start(db, match)
        changed = await service.tick(db)
        assert changed.beats[match.id] == [announce.Beat("reveal", 1)]

    async def test_a_stamped_beat_stops_being_owed(self, db, crew):
        match = await open_match(db, crew, pick_ban=False)
        await match_ops.start(db, match)
        await service.tick(db)
        first = (await service.rounds(db, match.id))[0]
        announce.stamp(first, announce.Beat("reveal", 1))
        await db.flush()

        assert match.id not in (await service.tick(db)).beats

    async def test_a_closed_match_is_still_swept_while_it_owes_a_result(
        self, db, crew
    ):
        """It leaves the live set on the tick that decides it — the same tick
        its result is announced on — so nothing else would ever retry."""
        alice, bob = crew
        match = await open_match(db, crew, pick_ban=False)
        await match_ops.start(db, match)
        for _ in range(match_ops.wins_needed(match.best_of)):
            await finish_round(db, match, alice.id, bob.id)
        assert match.state == MatchState.CLOSED

        owed = (await service.tick(db)).beats[match.id]
        assert announce.Beat("result", 2) in owed

        for round_ in await service.rounds(db, match.id):
            for beat in announce.owed([round_]):
                announce.stamp(round_, beat)
        await db.flush()
        assert match.id not in (await service.tick(db)).beats


class TestViewBuild:
    """The board's one query path, exercised against the real schema.

    This class exists because it was missing: `Side.discord_id` was wired to a
    column on the wrong table, every pure test built a `Side` by hand, and the
    first thing to notice was `/tournament quick` failing in production.
    """

    async def test_a_board_builds_for_a_fresh_match(self, db, crew):
        match = await open_match(db, crew, pick_ban=False)
        built = await viewbuild.build(db, match)
        # An account with no display_name yet falls back to its id, never to a
        # blank: a nameless side is still a row the board has to draw.
        assert all(side.arcaea_name.startswith("player ") for side in built.sides)

    async def test_the_mention_comes_from_the_player_link(
        self, db, crew, make_link
    ):
        """discord_id lives on player_links — many Discord users may share one
        Arcaea account, so it cannot live on the account."""
        alice, bob = crew
        await make_link(555, alice, linked_via=LinkMethod.ACCOUNT, is_owner=True)
        match = await open_match(db, crew, pick_ban=False)

        built = await viewbuild.build(db, match)
        assert [side.discord_id for side in built.sides] == [555, None]
        assert announce.mention_ids(built) == [555]

    async def test_the_owner_link_speaks_for_a_shared_account(
        self, db, crew, make_link
    ):
        """Many Discord users -> one account is legal. `is_owner` marks the
        single link that speaks for it, so that is the one that gets pinged."""
        alice, _ = crew
        await make_link(111, alice, linked_via=LinkMethod.CODE, is_owner=False)
        await make_link(222, alice, linked_via=LinkMethod.ACCOUNT, is_owner=True)
        match = await open_match(db, crew, pick_ban=False)

        built = await viewbuild.build(db, match)
        assert built.sides[0].discord_id == 222

    async def test_an_account_with_no_link_still_reaches_the_board(self, db, crew):
        """A LEFT join, not an inner one: a nameless side is a row the board
        draws, never a match that cannot be rendered."""
        match = await open_match(db, crew, pick_ban=False)
        built = await viewbuild.build(db, match)
        assert len(built.sides) == 2
        assert all(side.discord_id is None for side in built.sides)

    async def test_the_board_carries_the_turn_between_rounds(self, db, crew):
        """A pick served mid-match is still a turn, so the board draws it the
        same way -- countdown and menu -- rather than a break it is not in."""
        alice, bob = crew
        match = await open_match(db, crew)
        await match_ops.start(db, match)
        await draft_bans(db, match)
        await act_next(db, match)
        await finish_round(db, match, alice.id, bob.id)
        await service.tick(db)

        built = await viewbuild.build(db, match)
        assert built.turn is not None and built.turn.action == "pick"
        assert built.phase is None, "a turn is not a break"
        assert render.board(built).rows, "the pick menu rides the board"

    async def test_an_undrafted_entry_reads_unplayed_once_it_is_over(
        self, db, crew
    ):
        """A match decided early leaves charts nobody picked. They were never
        banned and never played, and `available` would read as still on the
        table."""
        alice, bob = crew
        match = await open_match(db, crew, best_of=5)
        await match_ops.start(db, match)
        await draft_bans(db, match)
        for _ in range(match_ops.wins_needed(match.best_of)):
            await act_next(db, match)
            await finish_round(db, match, alice.id, bob.id)
            await service.tick(db)

        built = await viewbuild.build(db, match)
        assert "available" not in {entry.state for entry in built.pool}
        assert "unplayed" in {entry.state for entry in built.pool}

    async def test_the_discord_name_captured_at_creation_wins(self, db, crew):
        alice, bob = crew
        alice.display_name = "ArcaeaAlice"
        await db.flush()
        match = await match_ops.create(
            db,
            guild_id=1,
            home_channel_id=2,
            thread_id=3,
            creator_discord_id=4,
            roster=[alice.id, bob.id],
            options=options(pick_ban=False),
            names={alice.id: "marut"},
        )
        built = await viewbuild.build(db, match)
        assert built.sides[0].name == "marut"
        assert built.sides[0].arcaea_name == "ArcaeaAlice"
        # No Discord name captured for bob, so the Arcaea one stands.
        assert built.sides[1].name == built.sides[1].arcaea_name


class TestBestOfOne:
    """No picks exist at Bo1, so there is nothing to interleave: the two bans
    run and the survivor is the decider, exactly as before."""

    async def test_bans_then_the_decider(self, db, crew):
        alice, bob = crew
        match = await open_match(db, crew, best_of=1)
        await match_ops.start(db, match)
        assert len(await match_ops.entries(db, match.id)) == 3
        await draft_bans(db, match)

        assert match.state == MatchState.PLAYING
        assert await match_ops.turn_owed(db, match) is False
        assert len(await service.rounds(db, match.id)) == 1

        await finish_round(db, match, alice.id, bob.id)
        assert match.state == MatchState.CLOSED
