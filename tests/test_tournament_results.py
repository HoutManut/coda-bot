"""Round ranking. Pure — no DB.

Ranking is raw score with an earlier ``time_played`` breaking the tie, and
nothing else. A no-score participant is a row the board draws, never an
omission, so it has to survive the sort rather than fall out of it.
"""

from __future__ import annotations

from coda.tournaments.results import Standing, all_scored, rank, winner_side


def standing(side: int, score: int | None, played: int | None = None) -> Standing:
    return Standing(
        arcaea_account_id=side + 1,
        side_index=side,
        score=score,
        time_played=played,
        song_difficulty_id=1 if score is not None else None,
    )


class TestRank:
    def test_higher_score_first(self):
        rows = rank([standing(0, 9_800_000, 5), standing(1, 9_900_000, 9)])
        assert [r.side_index for r in rows] == [1, 0]

    def test_tie_breaks_on_earlier_play(self):
        rows = rank([standing(0, 9_900_000, 900), standing(1, 9_900_000, 100)])
        assert [r.side_index for r in rows] == [1, 0]

    def test_no_score_sorts_last(self):
        rows = rank([standing(0, None), standing(1, 5_000_000, 10)])
        assert [r.side_index for r in rows] == [1, 0]

    def test_a_zero_score_still_beats_no_score(self):
        """0 is a real score — a hard-gauge death submits one seconds in."""
        rows = rank([standing(0, None), standing(1, 0, 10)])
        assert [r.side_index for r in rows] == [1, 0]

    def test_no_score_participants_are_kept(self):
        rows = rank([standing(0, None), standing(1, None)])
        assert len(rows) == 2


class TestWinner:
    def test_higher_score_wins(self):
        side, tied = winner_side(rank([standing(0, 9_500_000, 1), standing(1, 9_600_000, 2)]))
        assert (side, tied) == (1, False)

    def test_earlier_play_wins_a_score_tie(self):
        side, tied = winner_side(rank([standing(0, 9_900_000, 50), standing(1, 9_900_000, 20)]))
        assert (side, tied) == (1, False)

    def test_identical_score_and_time_is_a_draw(self):
        side, tied = winner_side(rank([standing(0, 9_900_000, 20), standing(1, 9_900_000, 20)]))
        assert (side, tied) == (None, True)

    def test_nobody_played(self):
        assert winner_side(rank([standing(0, None), standing(1, None)])) == (None, False)

    def test_one_player_scoring_wins_unopposed(self):
        side, tied = winner_side(rank([standing(0, None), standing(1, 1_000, 4)]))
        assert (side, tied) == (1, False)


class TestAllScored:
    def test_true_only_when_everyone_has_a_score(self):
        assert all_scored([standing(0, 1, 1), standing(1, 2, 2)])
        assert not all_scored([standing(0, 1, 1), standing(1, None)])

    def test_empty_roster_is_not_all_scored(self):
        assert not all_scored([])
