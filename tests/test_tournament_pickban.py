"""The head-to-head pick/ban sequence and the pool size it forces. Pure — no DB.

Pool size is derived from ``best_of`` and is deliberately not configurable:
offering both would let someone configure a Bo5 with a three-chart pool, which
cannot be played.
"""

from __future__ import annotations

import pytest

from coda.tournaments.pickban import auto_pick, pool_size, sequence, turn_at


class TestPoolSize:
    @pytest.mark.parametrize("best_of,size", [(1, 3), (3, 5), (5, 7), (7, 9)])
    def test_head_to_head(self, best_of, size):
        assert pool_size(best_of, roster=2, pick_ban=True) == size

    @pytest.mark.parametrize("best_of", [1, 3, 5, 7])
    def test_size_leaves_exactly_one_decider(self, best_of):
        """Every action consumes one entry; the survivor is the decider."""
        assert pool_size(best_of, roster=2, pick_ban=True) - len(sequence(best_of)) == 1

    @pytest.mark.parametrize("best_of", [1, 3, 5, 7])
    def test_rounds_played_equals_best_of(self, best_of):
        picks = sequence(best_of).count("pick")
        assert picks + 1 == best_of

    def test_above_two_players_there_is_no_pickban(self):
        """The pool IS the round's chart set, so best_of is how many charts are
        on the table."""
        assert pool_size(3, roster=5, pick_ban=True) == 3

    @pytest.mark.parametrize("best_of", [1, 3, 5, 7])
    def test_bans_off_asks_for_no_slack(self, best_of):
        """Nothing is thrown away, so demanding the ban slack anyway would
        refuse pools that could have been played."""
        assert pool_size(best_of, roster=2, pick_ban=False) == best_of


class TestSequence:
    def test_bans_come_first(self):
        assert sequence(5)[:2] == ["ban", "ban"]

    def test_bo1_is_two_bans_and_a_decider(self):
        assert sequence(1) == ["ban", "ban"]

    def test_sides_alternate(self):
        sides = [turn_at(i, 5).side_index for i in range(len(sequence(5)))]
        assert sides == [0, 1, 0, 1, 0, 1]

    def test_exhausted_sequence_has_no_turn(self):
        assert turn_at(len(sequence(3)), 3) is None

    def test_turn_carries_its_action(self):
        assert turn_at(2, 3).action == "pick"


class TestAutoAct:
    def test_only_ever_acts_on_what_remains(self):
        remaining = [4, 9, 11]
        assert all(auto_pick(remaining) in remaining for _ in range(50))

    def test_is_not_pool_order(self):
        """Deterministic auto-act is guessable, and therefore exploitable
        against a pool the organizer ordered."""
        remaining = list(range(20))
        assert len({auto_pick(remaining) for _ in range(60)}) > 1
