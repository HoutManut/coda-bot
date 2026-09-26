"""The beats a match says out loud in its thread. Text only, no Discord.

The board is game state: one message, edited in place, always current. These
are the *moments* -- a chart revealed, a round decided -- and each is a NEW
message, because Discord does not notify on an edit. A player whose thread is
closed learns that a round opened from this and from nothing else.

A beat is owed while its stamp on the round is NULL, so the sweep re-derives
what to say from the rows instead of trusting that it was still running when
the transition happened. That is the same reason every board component id is
stateless: a restart mid-match must lose nothing.

A roster line (``joined``/``left``) carries no stamp, because there is nothing
to re-derive: it reports a command somebody just ran, and a command that ran
once is said once. Together the lines are the thread's timeline of who turned
up, which the board -- one message, always overwritten -- cannot keep.

Ordering is load-bearing. The result lands, the break runs, and only then is
the next chart named -- so the reveal is also the only "go" the match needs.
You cannot play a chart before you are told which one it is.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from coda.db.enums import RoundState
from coda.db.models import TournamentRound
from coda.tournaments.views import MatchView, PoolEntry, RoundResult, SideScore
from coda.utils.scoring import format_score

Kind = Literal["reveal", "result"]

# Rotated so a crew playing five matches does not read the same send-off five
# times. Lowercase and short on purpose: the bot is running the match, not
# hosting it.
SEND_OFFS = ("glhf", "gl hf", "have fun", "good luck", "make it count")

# A round is revealed the moment it leaves `pending`, whatever it leaves for --
# a cancelled round was never played and is never announced.
REVEALED = (RoundState.OPEN, RoundState.GRACE, RoundState.CLOSED)


@dataclass(frozen=True)
class Beat:
    """One thing worth a message, and the round it is about."""

    kind: Kind
    ordinal: int


def joined(name: str) -> str:
    """The line a join writes into the thread's log."""
    return f"**{name}** joined."


def left(name: str) -> str:
    """The line a leave writes into the thread's log."""
    return f"**{name}** left."


def owed(live: Sequence[TournamentRound]) -> list[Beat]:
    """Beats not yet posted, oldest round first.

    Both of a round's beats can be owed at once -- a round that opened and
    closed inside one tick, or a backlog after a restart -- and the order here
    is the order they happened, so the thread still reads correctly.
    """
    beats: list[Beat] = []
    for round_ in sorted(live, key=lambda r: r.ordinal):
        if round_.state in REVEALED and round_.revealed_at is None:
            beats.append(Beat("reveal", round_.ordinal))
        if round_.state == RoundState.CLOSED and round_.resulted_at is None:
            beats.append(Beat("result", round_.ordinal))
    return beats


def stamp(round_: TournamentRound, beat: Beat) -> None:
    """Mark a beat posted. Called only once the message actually landed."""
    now = datetime.now(timezone.utc)
    if beat.kind == "reveal":
        round_.revealed_at = now
    else:
        round_.resulted_at = now


def line(view: MatchView, beat: Beat) -> str | None:
    """What to post for one beat, or None if there is nothing to say.

    Plain text rather than a container: this is the bot talking in a thread
    other people are talking in, and it should not arrive looking like a
    dashboard.
    """
    entry = next(
        (e for e in view.pool if e.round_ordinal == beat.ordinal), None)
    if entry is None:
        return None
    if beat.kind == "reveal":
        return _reveal(view, entry, beat.ordinal)
    return _result(view, entry, beat.ordinal)


def mention_ids(view: MatchView) -> list[int]:
    """Who a beat pings. Empty is fine -- the text still reads."""
    return [s.discord_id for s in view.sides if s.discord_id is not None]


def _reveal(view: MatchView, entry: PoolEntry, ordinal: int) -> str:
    """The chart, and the fact that the clock is now running.

    Round one carries the send-off; later rounds do not, because a greeting
    repeated every round stops reading as a greeting.
    """
    who = _mentions(view)
    what = entry.display
    if ordinal == 1:
        return f"{who}round 1 is {what}\nFive minutes on the clock. {random.choice(SEND_OFFS)}"
    return f"{who}round {ordinal} is {what}"


def _result(view: MatchView, entry: PoolEntry, ordinal: int) -> str:
    """Who took the round, and -- on the last one -- who took the match.

    The match outcome rides on the final round's result rather than arriving as
    a beat of its own: they are the same moment, and two messages for one
    moment is how a bot starts sounding like a scoreboard.
    """
    said = _round_outcome(view, entry.result, ordinal)
    finish = _match_outcome(view)
    return f"{said}\n{finish}" if finish else said


def _round_outcome(
    view: MatchView, result: RoundResult | None, ordinal: int
) -> str:
    if result is None or not any(s.score is not None for s in result.scores):
        return f"Nobody got a score in on round {ordinal}."
    if result.tied or result.winner_side is None:
        # No winner to lead with, so the board's side order stands.
        return f"Round {ordinal} is a draw, {_scores(view, result.scores)}."
    # Winner's score FIRST, which the board has no reason to do and this
    # sentence does: "X takes it, 99 to 97" reads as X having scored 99.
    ordered = sorted(
        enumerate(result.scores), key=lambda pair: pair[0] != result.winner_side
    )
    winner = view.sides[result.winner_side].name
    shown = _scores(view, [played for _, played in ordered])
    return f"**{winner}** takes round {ordinal}, {shown}."


def _scores(view: MatchView, scores: Sequence[SideScore]) -> str:
    return " to ".join(_played(view, played) for played in scores)


def _played(view: MatchView, played: SideScore) -> str:
    """One side's answer, and in song mode WHICH chart it was answered on.

    Without the class the number says nothing there: the two sides pick their
    own difficulty, so 9'207'427 and 9'786'458 may not be comparable at all.
    The board prints it for the same reason.
    """
    if played.score is None:
        return "no score"
    shown = format_score(played.score)
    if view.song_mode and played.chart is not None:
        shown += f" on {played.chart.class_label}"
    return shown


def _match_outcome(view: MatchView) -> str | None:
    """None while the match is still live, so this reads as a normal line."""
    if view.winner_side is None:
        return None
    tally = "-".join(str(side.rounds_won) for side in view.sides)
    return f"**{view.sides[view.winner_side].name}** wins it {tally}."


def _mentions(view: MatchView) -> str:
    ids = mention_ids(view)
    return " ".join(f"<@{discord_id}>" for discord_id in ids) + ", " if ids else ""
