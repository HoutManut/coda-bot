"""What a match says in its thread, and where it is on the clock. Pure — no DB.

Two things regress silently here. A beat that is stamped without being posted
is a round nobody was told about, which is the exact hole the beats exist to
close; and a phase that reports `break` while scores are still being gathered
puts a "go now" button under a round that has not been decided yet.
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from coda.db.enums import (
    DifficultyClass,
    MatchState,
    RoundState,
)
from coda.tournaments import announce, prompts, render
from coda.tournaments.constants import BREAK_SECONDS, GRACE_SECONDS
from coda.tournaments.levels import LevelRange
from coda.tournaments.service import phase_of
from coda.tournaments.views import (
    ChartRef,
    MatchView,
    PoolEntry,
    RoundResult,
    Side,
    SideScore,
)

GRACE_MS = GRACE_SECONDS * 1000
BREAK_MS = BREAK_SECONDS * 1000


def round_(
    ordinal: int,
    state: RoundState,
    *,
    start_ms: int | None = None,
    end_ms: int | None = None,
    closed_ms: int | None = None,
    revealed: object = None,
    resulted: object = None,
):
    """A round row, as `phase_of` and `owed` read one."""
    return SimpleNamespace(
        ordinal=ordinal,
        state=state,
        start_ms=start_ms,
        end_ms=end_ms,
        closed_ms=closed_ms,
        grace_ms=GRACE_MS,
        revealed_at=revealed,
        resulted_at=resulted,
    )


def chart(title: str = "Grievous Lady") -> ChartRef:
    return ChartRef(
        title=title,
        artist="Team Grimoire vs Laur",
        difficulty_class=DifficultyClass.BYD,
        alt=False,
        level_display="11",
        cc_display="11.4",
        spoilered=False,
    )


def view(
    *,
    pool: list[PoolEntry],
    winner_side: int | None = None,
    wins: tuple[int, int] = (0, 0),
    discord_ids: tuple[int | None, int | None] = (111, 222),
    discord_names: tuple[str | None, str | None] = (None, None),
) -> MatchView:
    return MatchView(
        match_id=1,
        kind="quick",
        stage_label=None,
        state=MatchState.PLAYING,
        best_of=3,
        pick_ban=True,
        open_join=False,
        levels=LevelRange(22, 22),
        difficulty_class=DifficultyClass.BYD,
        sides=[
            Side("alice", discord_names[0], discord_ids[0], wins[0], False),
            Side("bob", discord_names[1], discord_ids[1], wins[1], False),
        ],
        pool=pool,
        turn=None,
        winner_side=winner_side,
        phase=None,
        phase_ends_ms=None,
        phase_ordinal=None,
        now_ms=0,
    )


def entry(ordinal: int, result: RoundResult | None = None) -> PoolEntry:
    return PoolEntry(
        entry_id=ordinal,
        chart=chart(),
        song_title="Grievous Lady",
        state="playing",
        acted_by_side=0,
        auto=False,
        acted_at_ms=None,
        round_ordinal=ordinal,
        result=result,
    )


def result(
    ordinal: int, scores: list[int | None], winner: int | None, tied: bool = False
) -> RoundResult:
    return RoundResult(
        ordinal=ordinal,
        scores=[SideScore(s, 10, chart()) for s in scores],
        winner_side=winner,
        tied=tied,
    )


class TestPhase:
    def test_open_counts_down_to_the_window(self):
        live = [round_(1, RoundState.OPEN, start_ms=0, end_ms=300_000)]
        assert phase_of(live, 10_000) == ("open", 300_000, 1)

    def test_grace_counts_down_past_the_window(self):
        """Grace is its own phase, not the break: the round just played is
        still being scored, and the board must not offer to move on."""
        live = [round_(1, RoundState.GRACE, start_ms=0, end_ms=300_000)]
        assert phase_of(live, 310_000) == ("grace", 300_000 + GRACE_MS, 1)

    def test_break_runs_from_the_result_not_the_window(self):
        """The break exists to read a result in, so it cannot start before the
        scores are gathered — it is measured past grace, never past end_ms."""
        live = [
            round_(1, RoundState.CLOSED, start_ms=0, end_ms=300_000),
            round_(2, RoundState.PENDING),
        ]
        phase, ends, ordinal = phase_of(live, 400_000)
        assert (phase, ordinal) == ("break", 2)
        assert ends == 300_000 + GRACE_MS + BREAK_MS

    def test_break_names_the_round_it_precedes(self):
        live = [
            round_(1, RoundState.CLOSED, start_ms=0, end_ms=1),
            round_(2, RoundState.CLOSED, start_ms=0, end_ms=300_000),
            round_(3, RoundState.PENDING),
        ]
        assert phase_of(live, 400_000)[2] == 3

    def test_a_live_round_outranks_a_pending_one(self):
        live = [
            round_(1, RoundState.OPEN, start_ms=0, end_ms=300_000),
            round_(2, RoundState.PENDING),
        ]
        assert phase_of(live, 10_000)[0] == "open"

    def test_no_phase_before_the_first_round_opens(self):
        """Round one has no previous result, so there is no break to sit in."""
        assert phase_of([round_(1, RoundState.PENDING)], 0) == (None, None, None)

    def test_no_phase_once_nothing_is_pending(self):
        live = [round_(1, RoundState.CLOSED, start_ms=0, end_ms=300_000)]
        assert phase_of(live, 400_000) == (None, None, None)

    def test_a_cancelled_next_round_is_not_a_break(self):
        live = [
            round_(1, RoundState.CLOSED, start_ms=0, end_ms=300_000),
            round_(2, RoundState.CANCELLED),
        ]
        assert phase_of(live, 400_000) == (None, None, None)


class TestOwed:
    def test_an_open_round_owes_its_reveal(self):
        assert announce.owed([round_(1, RoundState.OPEN)]) == [
            announce.Beat("reveal", 1)
        ]

    def test_a_pending_round_owes_nothing(self):
        """Its chart is not named until the break ends, so there is nothing to
        say about it yet."""
        assert announce.owed([round_(1, RoundState.PENDING)]) == []

    def test_a_cancelled_round_is_never_announced(self):
        assert announce.owed([round_(3, RoundState.CANCELLED)]) == []

    def test_a_closed_round_owes_both_when_neither_was_said(self):
        """A restart mid-round, or a round that opened and closed inside one
        tick. The backlog still reads in the order it happened."""
        assert announce.owed([round_(1, RoundState.CLOSED)]) == [
            announce.Beat("reveal", 1),
            announce.Beat("result", 1),
        ]

    def test_a_stamped_beat_is_not_owed_again(self):
        live = [round_(1, RoundState.CLOSED, revealed="t", resulted="t")]
        assert announce.owed(live) == []

    def test_a_posted_reveal_still_owes_its_result(self):
        live = [round_(1, RoundState.CLOSED, revealed="t")]
        assert announce.owed(live) == [announce.Beat("result", 1)]

    def test_beats_come_out_in_round_order(self):
        live = [round_(2, RoundState.OPEN), round_(1, RoundState.CLOSED)]
        assert [b.ordinal for b in announce.owed(live)] == [1, 1, 2]


class TestStamp:
    def test_reveal_and_result_stamp_different_fields(self):
        row = round_(1, RoundState.CLOSED)
        announce.stamp(row, announce.Beat("reveal", 1))
        assert row.revealed_at is not None and row.resulted_at is None
        announce.stamp(row, announce.Beat("result", 1))
        assert row.resulted_at is not None


class TestReveal:
    def test_round_one_names_the_chart_and_sends_them_off(self):
        said = announce.line(view(pool=[entry(1)]), announce.Beat("reveal", 1))
        assert "**Grievous Lady** BYD 11 (11.4)" in said
        assert any(tail in said for tail in announce.SEND_OFFS)

    def test_later_rounds_drop_the_send_off(self):
        """A greeting repeated every round stops reading as a greeting."""
        said = announce.line(view(pool=[entry(2)]), announce.Beat("reveal", 2))
        assert "round 2 is **Grievous Lady**" in said
        assert not any(tail in said for tail in announce.SEND_OFFS)

    def test_both_sides_are_mentioned(self):
        said = announce.line(view(pool=[entry(1)]), announce.Beat("reveal", 1))
        assert "<@111>" in said and "<@222>" in said

    def test_an_unlinked_side_does_not_break_the_line(self):
        said = announce.line(
            view(pool=[entry(1)], discord_ids=(111, None)),
            announce.Beat("reveal", 1),
        )
        assert "<@111>" in said and "None" not in said

    def test_no_mentions_at_all_still_reads(self):
        said = announce.line(
            view(pool=[entry(1)], discord_ids=(None, None)),
            announce.Beat("reveal", 1),
        )
        assert said.startswith("round 1 is **Grievous Lady**")

    def test_mention_ids_skips_the_unlinked(self):
        assert announce.mention_ids(
            view(pool=[], discord_ids=(111, None))) == [111]


class TestResult:
    def test_the_winner_and_both_scores(self):
        said = announce.line(
            view(pool=[entry(1, result(1, [9_981_234, 9_975_003], 0))]),
            announce.Beat("result", 1),
        )
        assert "**alice** takes round 1" in said
        # Arcaea's own grouping, as every other score surface prints it.
        assert "09'981'234" in said and "09'975'003" in said

    def test_a_draw_names_nobody(self):
        said = announce.line(
            view(pool=[entry(1, result(1, [9_900_000, 9_900_000], None, True))]),
            announce.Beat("result", 1),
        )
        assert "is a draw" in said and "takes" not in said

    def test_a_round_nobody_scored(self):
        said = announce.line(
            view(pool=[entry(1, result(1, [None, None], None))]),
            announce.Beat("result", 1),
        )
        assert said == "Nobody got a score in on round 1."

    def test_one_side_missing_still_names_a_winner(self):
        said = announce.line(
            view(pool=[entry(1, result(1, [9_900_000, None], 0))]),
            announce.Beat("result", 1),
        )
        assert "**alice** takes round 1" in said and "no score" in said

    def test_the_last_result_carries_the_match_outcome(self):
        """One moment, one message — the match ending is not a beat of its own."""
        said = announce.line(
            view(
                pool=[entry(3, result(3, [9_900_000, 9_800_000], 0))],
                winner_side=0,
                wins=(2, 1),
            ),
            announce.Beat("result", 3),
        )
        assert "takes round 3" in said
        assert "**alice** wins it 2-1." in said

    def test_a_live_match_says_nothing_about_winning(self):
        said = announce.line(
            view(pool=[entry(1, result(1, [9_900_000, 9_800_000], 0))]),
            announce.Beat("result", 1),
        )
        assert "wins it" not in said


class TestNaming:
    """A thread is a Discord room, so people are called what Discord calls them
    — but the Arcaea name is whose scores these are, and is the only name a
    player who joined before it could be captured has."""

    def test_the_discord_name_wins_where_there_is_one(self):
        said = announce.line(
            view(
                pool=[entry(1, result(1, [9_900_000, 9_800_000], 0))],
                discord_names=("marut", None),
            ),
            announce.Beat("result", 1),
        )
        assert "**marut** takes round 1" in said

    def test_the_arcaea_name_is_the_fallback(self):
        said = announce.line(
            view(pool=[entry(1, result(1, [9_900_000, 9_800_000], 0))]),
            announce.Beat("result", 1),
        )
        assert "**alice** takes round 1" in said

    def test_the_board_prefers_it_too(self):
        built = replace(
            view(pool=[entry(1)], discord_names=("marut", "kai")),
            phase="open",
            phase_ends_ms=1,
        )
        assert "marut" in render._score_line(built)
        assert "alice" not in render._score_line(built)


class TestMissing:
    def test_a_beat_for_a_round_with_no_pool_entry_says_nothing(self):
        assert announce.line(view(pool=[]), announce.Beat("reveal", 1)) is None


class TestBoardPhases:
    """What the board says, and what it offers, in each phase.

    The old board said "Next round shortly — press Ready to go now" throughout
    grace, which invited a player to move on while the bot was still looking
    for the score they had just set.
    """

    def phased(self, phase, ends=500_000, ordinal=2):
        built = view(pool=[entry(1)])
        return replace(
            built, phase=phase, phase_ends_ms=ends, phase_ordinal=ordinal)

    def test_open_counts_the_window_down(self):
        assert "Window closes" in render._waiting_line(self.phased("open"))

    def test_grace_says_it_is_still_looking(self):
        said = render._waiting_line(self.phased("grace"))
        assert "Looking for scores" in said
        assert "Ready" not in said

    def test_break_names_the_next_round_and_who_it_waits_on(self):
        said = render._waiting_line(self.phased("break"))
        assert "Round 2" in said
        assert "○ alice" in said and "○ bob" in said

    def test_the_board_never_carries_the_ready_button(self):
        """A Ready is an answer to a question, so it rides the message that
        asks -- the board is edited in place and would not notify anyone."""
        for phase in ("open", "grace", "break"):
            assert render._rows(self.phased(phase)) == []

    def test_ready_is_offered_only_in_the_break(self):
        assert prompts.current(self.phased("break")).rows
        assert prompts.current(self.phased("grace")) is None
        assert prompts.current(self.phased("open")) is None
