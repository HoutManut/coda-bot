"""``MatchView`` -> ``Rendered``. The text board.

The board is the match: one message, edited in place, always current, and it
carries the pick/ban menu -- the one control whose subject IS the board, since
what it chooses from is the pool printed right above it -- plus every clock the
match is running against. One place to look, and one message to keep scrolled
to. Both **Ready** buttons live instead on the line that asks for them
(``prompts.py``), because a Ready is an answer to a question, and a question
and its answer belong on one message.

What an edit cannot do is get noticed, so the moments still go out as messages
of their own: the beats a round says (``announce.py``), and a one-line nudge
when a wait lands on somebody (``prompts.py``). Those name who is owed; this
says everything else.

The image board is a later pass and lands entirely behind this seam: it will
read the same view and return the same ``Rendered``, so nothing above changes
when it arrives. Text then stops being the only board and becomes the fallback
for a guild that denies Attach Files.
"""

from __future__ import annotations

import hikari
from hikari.impl import MessageActionRowBuilder

from coda.catalog.labels import class_short
from coda.db.enums import MatchState
from coda.tournaments.levels import display as level_display
from coda.tournaments.views import MatchView, PoolEntry, countdown
from coda.utils.render import Rendered
from coda.utils.scoring import format_score

ACT_ID = "tourney:act:{match_id}"

COLOR_LIVE = 0x5865F2
COLOR_DONE = 0x57F287
COLOR_DEAD = 0x99AAB5

MARKS = {
    "available": "·",
    "banned": "✕",
    "picked": "•",
    "playing": "▶",
    "played": "✓",
    "unplayed": "–",
}

READY_MARKS = {True: "✓", False: "○"}

STATE_NOTE = {
    MatchState.DRAFT: "Waiting to start",
    MatchState.PICKBAN: "Picking and banning",
    MatchState.PLAYING: "In play",
    MatchState.CLOSED: "Finished",
    MatchState.CANCELLED: "Cancelled",
}


def board(view: MatchView) -> Rendered:
    """The one message a match keeps, ready to post or edit."""
    embed = hikari.Embed(
        title=_title(view), description=_body(view), color=_color(view))
    return Rendered(
        embed=embed,
        rows=_rows(view),
        # Decision 30 keeps a spoilered chart out of a pool, so this is the
        # rare round that reached one some other way.
        spoiler=any(
            entry.chart is not None and entry.chart.spoilered
            for entry in view.pool
        ),
    )


def _title(view: MatchView) -> str:
    names = " vs ".join(side.name for side in view.sides[:2])
    if len(view.sides) > 2:
        names = f"{view.sides[0].name} +{len(view.sides) - 1}"
    return f"{view.stage_label} - {names}" if view.stage_label else names


def _color(view: MatchView) -> int:
    if view.state == MatchState.CANCELLED:
        return COLOR_DEAD
    return COLOR_DONE if view.state == MatchState.CLOSED else COLOR_LIVE


def _body(view: MatchView) -> str:
    blocks = [_format_line(view), _score_line(view)]
    if view.pool:
        blocks.append("\n".join(_entry_line(view, e) for e in view.pool))
    waiting = _waiting_line(view)
    if waiting:
        blocks.append(waiting)
    return "\n\n".join(block for block in blocks if block)


def _format_line(view: MatchView) -> str:
    """Everything that changes how you play is printed, and the converse holds:
    anything not printed here must not change how you play."""
    parts = [
        f"**Bo{view.best_of}**",
        level_display(view.levels),
        "any difficulty"
        if view.song_mode
        else class_short(view.difficulty_class).upper(),
    ]
    # if view.head_to_head and not view.pick_ban:
    #     parts.append("no bans")
    return "-# " + " · ".join(parts)


def _score_line(view: MatchView) -> str:
    if view.state == MatchState.DRAFT:
        # Ticked, not just listed: the match is waiting on these people, and
        # the board should say which of them it is still waiting on.
        head = f"**{STATE_NOTE[view.state]}**"
        if view.open_join:
            # The board is the only thing a passer-by reads, so it is the only
            # place that can tell them the room will have them.
            head += " · anyone can `/tournament join`"
        return f"{head}\n{_ready_marks(view)}"
    if view.head_to_head:
        left, right = view.sides
        line = (
            f"**{left.name}** {left.rounds_won} - "
            f"{right.rounds_won} **{right.name}**"
        )
    else:
        line = "\n".join(
            f"**{side.name}** {side.rounds_won}" for side in view.sides
        )
    if view.winner_side is not None:
        return f"{line}\n🏆 **{view.sides[view.winner_side].name}** wins"
    return line


def _entry_line(view: MatchView, entry: PoolEntry) -> str:
    mark = MARKS[entry.state]
    name = entry.display
    line = f"{mark} {name}"
    if entry.state == "banned" and entry.acted_by_side is not None:
        who = view.sides[entry.acted_by_side].name
        # An auto-ban reads differently from a chosen one.
        line += f", banned by {who}{' (timed out)' if entry.auto else ''}"
    if entry.result is not None:
        line += _result_line(view, entry)
    return line


def _result_line(view: MatchView, entry: PoolEntry) -> str:
    """The scores, and who took the round -- a pool entry carries its own
    winner, which is what makes this a match board rather than a leaderboard."""
    result = entry.result
    scores = []
    for index, (side, played) in enumerate(zip(view.sides, result.scores)):
        if played.score is None:
            scores.append(f"{side.name} no score")
            continue
        shown = format_score(played.score)
        # Say WHICH chart it measured: in song mode the two sides choose
        # different difficulties and the number alone is unreadable.
        if view.song_mode and played.chart is not None:
            shown += f" on {played.chart.class_label}"
        won = index == result.winner_side and not result.tied
        scores.append(
            f"**{side.name} {shown}**" if won else
            f"{side.name} {shown}"
        )
    body = " · ".join(scores)
    return f"\n   {body} (tied)" if result.tied else f"\n   {body}"


def _waiting_line(view: MatchView) -> str:
    """What the match is waiting for. Each phase says its own thing.

    Grace in particular is NOT the break: the scores for the round just played
    are still being gathered, and a player who has finished needs to see that
    the bot is looking for their play rather than an invitation to move on.
    """
    if view.turn is not None:
        who = view.sides[view.turn.side_index].name
        return (
            f"**{who}** to {view.turn.action}, {countdown(view.turn.deadline_ms)}"
        )
    if view.phase == "open":
        return f"Window closes {countdown(view.phase_ends_ms)}"
    if view.phase == "grace":
        return "-# Looking for scores…"
    if view.phase == "break":
        return (
            f"-# Round {view.phase_ordinal} {countdown(view.phase_ends_ms)}"
            f" · {_ready_marks(view)}"
        )
    return ""


def _ready_marks(view: MatchView) -> str:
    """Who has answered the wait and who has not, so nobody has to guess
    whether the hold-up is them."""
    return " · ".join(
        f"{READY_MARKS[side.ready]} {side.name}" for side in view.sides)


def _rows(view: MatchView) -> list[MessageActionRowBuilder]:
    """The pick/ban menu, when there is a turn to serve. Otherwise nothing.

    Nothing is the common case: an open window waits on a play rather than on a
    click, and a break's Ready rides its own message. A row that is always
    present trains people to ignore it.
    """
    return _act_rows(view) if view.turn is not None else []


def _act_rows(view: MatchView) -> list[MessageActionRowBuilder]:
    """A string select, not a button row: a pool runs to nine and a select
    holds twenty-five."""
    available = [entry for entry in view.pool if entry.state == "available"]
    if not available:
        return []
    row = MessageActionRowBuilder()
    menu = row.add_text_menu(
        ACT_ID.format(match_id=view.match_id),
        placeholder=f"Choose a chart to {view.turn.action}",
        min_values=1,
        max_values=1,
    )
    for entry in available:
        menu.add_option(_plain(entry)[:100], str(entry.entry_id))
    return [row]


def _plain(entry: PoolEntry) -> str:
    """A select option is plain text: no markdown, and short enough to fit."""
    if entry.chart is None:
        return entry.song_title
    chart = entry.chart
    return f"{chart.title} {chart.class_label} {chart.level_display}"
