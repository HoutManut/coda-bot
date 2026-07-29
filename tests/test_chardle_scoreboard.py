"""Scoreboard ordering and what an unfinished row is allowed to show."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from coda.chardle.render import DailyScoreboard, ScoreboardEntry, scoreboard
from coda.chardle.scoreboard import _rank
from coda.db.enums import ChardleState


def _entry(discord_id: int, state: ChardleState, taken: int) -> ScoreboardEntry:
    grid = None if state is ChardleState.PLAYING else ["🟩"] * taken
    return ScoreboardEntry(discord_id, state, taken, grid)


def _view(*entries: ScoreboardEntry) -> DailyScoreboard:
    return DailyScoreboard(
        puzzle_number=412,
        tier_label="Future",
        max_attempts=6,
        entries=sorted(entries, key=_rank),
        resets_at=datetime.now(UTC) + timedelta(hours=6),
    )


def test_solvers_rank_first_and_fewest_guesses_wins() -> None:
    view = _view(
        _entry(3, ChardleState.LOST, 6),
        _entry(2, ChardleState.WON, 5),
        _entry(4, ChardleState.PLAYING, 1),
        _entry(1, ChardleState.WON, 2),
    )
    assert [e.discord_id for e in view.entries] == [1, 2, 4, 3]


def test_a_loss_with_more_guesses_ranks_above_one_with_fewer() -> None:
    # On a lost board more guesses means got further, not did worse.
    view = _view(_entry(1, ChardleState.LOST, 2), _entry(2, ChardleState.LOST, 6))
    assert [e.discord_id for e in view.entries] == [2, 1]


def test_a_live_board_shows_no_grid() -> None:
    # The grid would say how many attempts are left, not just how it is going.
    view = _view(_entry(1, ChardleState.PLAYING, 3))
    body = scoreboard(view)[0].description
    assert "🟩" not in body
    assert "3 so far" in body


def test_each_of_the_top_three_solvers_gets_its_own_medal() -> None:
    # Identical results must not collide into three gold medals.
    view = _view(*[_entry(i, ChardleState.WON, 3) for i in range(1, 5)])
    body = scoreboard(view)[0].description
    assert body.count("🥇") == 1
    assert body.count("🥈") == 1
    assert body.count("🥉") == 1


def test_a_crowded_day_is_trimmed_rather_than_dropped() -> None:
    view = _view(*[_entry(i, ChardleState.LOST, 6) for i in range(200)])
    embed = scoreboard(view)[0]
    assert len(embed.description) <= 4096
    assert "more" in embed.description


def test_an_empty_day_still_renders() -> None:
    body = scoreboard(_view())[0].description
    assert "Nobody has played" in body
