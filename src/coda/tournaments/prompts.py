"""The one line a match says when it starts waiting on somebody. Text only.

Almost every control a match has lives on the **board** (``render.py``): one
message, edited in place, always current. What the board cannot do is get
noticed -- Discord does not notify on an edit -- so each wait that needs a
person also gets a prompt: a short new message naming who is owed and what for.

The controls that live HERE instead are the two **Ready** buttons, because a
Ready is always an answer to a question that was just asked out loud. The
question and the button that answers it ship on the same message; the board
keeps the pick/ban menu, where the thing being chosen is the board's own pool.

Deliberately one line. It is a nudge toward the board, not a second copy of it:
the countdown, the pool, the ready marks and the control itself are all up there
already, and repeating any of them here is how a thread turns into a wall of
bot messages nobody reads.

A prompt is keyed by the WAIT it belongs to, never by having witnessed the
transition -- the same reason a beat is keyed by its stamp. The key is
recomputed from the view on every pass, so a restart mid-match says nothing
twice, and a post that failed is simply still owed on the next one.

Not every wait gets one. An open window already has its reveal beat, and a
second message for a moment that just spoke is exactly the clutter this file is
trying not to be. The break does get one, but no ping: the result beat lands at
the same instant and has already pinged everybody.

Nothing is left standing as an unanswered ask. When a wait ends, its message is
either taken down or **rewritten into what happened** ("your ban" becomes
"Smol-Don banned Grievous Lady"), which is what ``resolved`` decides. A turn
line rewritten that way costs nothing and leaves the thread reading as the
pick/ban log it always wanted to be; a start or break line has no outcome worth
a sentence and simply goes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import hikari
from hikari.impl import MessageActionRowBuilder

from coda.db.enums import MatchState
from coda.tournaments.views import MatchView, PoolEntry, Side, countdown

READY_ID = "tourney:ready:{match_id}"

TURN = "turn:"


@dataclass(frozen=True)
class Prompt:
    """One wait, as a message: who it is on, and what for."""

    key: str
    text: str
    mentions: list[int] = field(default_factory=list)
    rows: list[MessageActionRowBuilder] = field(default_factory=list)


def current(view: MatchView) -> Prompt | None:
    """The line this match owes right now, or None when it owes nothing."""
    if view.state == MatchState.DRAFT:
        return _start(view)
    if view.state == MatchState.PICKBAN and view.turn is not None:
        return _turn(view)
    if view.state == MatchState.PLAYING and view.phase == "break":
        return _break(view)
    return None


def resolved(view: MatchView, wait: str | None) -> str | None:
    """What a FINISHED wait's message should say now, or None to take it down.

    Only a turn resolves. A pick or a ban is a fact the thread wants to keep,
    and rewriting the line that asked for it into the line that reports it
    costs no message and leaves no unanswered question sitting in the log.

    A start and a break resolve to nothing worth a sentence -- the pick/ban line
    and the reveal beat follow them within seconds and say it better -- so they
    are removed instead.
    """
    if wait is None or not wait.startswith(TURN):
        return None
    try:
        index = int(wait[len(TURN):])
    except ValueError:
        return None
    # Turns are strictly sequential, so the nth action IS turn n. Ordered by
    # when it happened, never by pool order, which is the board's order.
    acted = sorted(
        (e for e in view.pool if e.acted_at_ms is not None),
        key=lambda entry: entry.acted_at_ms,
    )
    if not 0 <= index < len(acted):
        return None
    return _acted_line(view, acted[index])


def _acted_line(view: MatchView, entry: PoolEntry) -> str | None:
    if entry.acted_by_side is None:
        return None
    who = view.sides[entry.acted_by_side].name
    verb = "banned" if entry.state == "banned" else "picked"
    # An auto action reads differently from a chosen one: the board marks it,
    # and the line that reports it has to as well.
    timed_out = " (timed out)" if entry.auto else ""
    return f"**{who}** {verb} {entry.display}{timed_out}"


def _start(view: MatchView) -> Prompt:
    """Nobody plays until everybody has said they are here.

    A quick match opens a thread at someone who never asked for it, so the
    roster is an invitation until each side answers it -- and a match that
    starts against an absent player is a forfeit dressed up as a game. There is
    no timeout, deliberately: the backstop for a match nobody confirms is
    ``/tournament cancel``, because starting one player short is worse than not
    starting.

    Keyed by roster SIZE, so a join re-asks: joining clears every confirmation,
    and the people who had already answered would otherwise be left with a
    stale button scrolled somewhere above and no word that they are being
    waited on again.
    """
    return Prompt(
        key=f"start:{len(view.sides)}",
        text=f"{_mentions(view)}hit **Ready** and the match starts.",
        mentions=_ids(view.sides),
        rows=[_ready_row(view.match_id)],
    )


def _turn(view: MatchView) -> Prompt:
    """Whose pick or ban it is. The menu and the clock are both on the board."""
    who = view.sides[view.turn.side_index]
    return Prompt(
        key=f"{TURN}{view.turn.index}",
        text=f"{_mention(who)}your **{view.turn.action}**.",
        mentions=_ids([who]),
    )


def _ready_row(match_id: int) -> MessageActionRowBuilder:
    row = MessageActionRowBuilder()
    row.add_interactive_button(
        hikari.ButtonStyle.PRIMARY,
        READY_ID.format(match_id=match_id),
        label="Ready",
    )
    return row


def _break(view: MatchView) -> Prompt:
    """The rest between a result and the next chart, and the way to skip it.

    No mentions: the result beat lands at the same instant and has already
    pinged both sides, and pinging twice for one moment is how a thread starts
    getting muted.
    """
    return Prompt(
        key=f"break:{view.phase_ordinal}",
        text=(
            f"Round {view.phase_ordinal} {countdown(view.phase_ends_ms)}. "
            f"Hit **Ready** to go sooner."
        ),
        rows=[_ready_row(view.match_id)],
    )


def _mentions(view: MatchView) -> str:
    ids = _ids(view.sides)
    return " ".join(f"<@{discord_id}>" for discord_id in ids) + ", " if ids else ""


def _mention(side: Side) -> str:
    """One side, addressed. A ping when we have one, the name when we do not --
    an unlinked account still has to be told it is their turn."""
    if side.discord_id is None:
        return f"**{side.name}**, "
    return f"<@{side.discord_id}>, "


def _ids(sides: list[Side]) -> list[int]:
    return [s.discord_id for s in sides if s.discord_id is not None]
