"""The head-to-head pick/ban sequence. Pure over the entry list -- the caller
writes rows.

A match is best-of-N over picked charts: two bans, then ``best_of - 1`` picks,
and the single entry left neither banned nor picked is the DECIDER, which plays
last. That is also why the decider is derived and never stored.

This list is the order the actions HAPPEN in, not the order they are asked for.
Only the two bans are drafted up front; each pick is served between rounds, so
a player who is behind picks with the score in front of them. ``match.py``
owns that timing -- the next turn is still position ``turn_index`` here, and
nothing in this module knows a round exists.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

Action = Literal["ban", "pick"]


@dataclass(frozen=True)
class Turn:
    """Whose turn it is and what they are doing."""

    index: int
    side_index: int
    action: Action


def pool_size(best_of: int, roster: int, pick_ban: bool) -> int:
    """How many entries a pool needs.

    Head-to-head WITH bans: two bans, ``best_of - 1`` picks, one decider.
    Without them nothing is thrown away -- the pool IS the round list, one
    chart per round -- and demanding the ban slack anyway refuses matches that
    would have run. Above two players there is no pick/ban either.
    """
    if roster > 2 or not pick_ban:
        return best_of
    return 2 + (best_of - 1) + 1


def sequence(best_of: int) -> list[Action]:
    """The actions of a head-to-head match, in order."""
    return ["ban", "ban"] + ["pick"] * (best_of - 1)


def turn_at(index: int, best_of: int) -> Turn | None:
    """The turn at ``index``, or ``None`` once the sequence is exhausted.

    Sides alternate from the randomised first actor, so the side is the
    position's parity and nothing else has to be stored.
    """
    actions = sequence(best_of)
    if index >= len(actions):
        return None
    return Turn(index=index, side_index=index % 2, action=actions[index])


def auto_pick(available: Sequence[int]) -> int:
    """What an expired turn acts on -- at random from what remains.

    Random rather than first-in-pool-order: a forced action chosen by pool
    order is guessable in advance, and therefore exploitable against a pool the
    organizer ordered.
    """
    return random.choice(list(available))
