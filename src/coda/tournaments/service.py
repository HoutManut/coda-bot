"""Round transitions and the sweep that drives them. DB only, no Discord.

Every transition is recomputable from the DB: round state plus start/end, match
state plus the turn deadline. Nothing lives in memory, so a restart mid-match
loses nothing and every board component has to be stateless.

Nothing here waits on a human. A wait ends the moment it is satisfied, and its
timeout is only the backstop for someone who never acts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from collections.abc import Sequence

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from coda.db.enums import MatchState, PoolEntryState, RoundState
from coda.db.models import (
    TournamentMatch,
    TournamentParticipant,
    TournamentRound,
)
from coda.tournaments import announce
from coda.tournaments import match as match_ops
from coda.tournaments import pickban, results
from coda.tournaments.constants import (
    BREAK_SECONDS,
    TURN_SECONDS,
    WINDOW_SECONDS,
)
from coda.tournaments.match import now_ms
from coda.tournaments.views import Phase

logger = logging.getLogger(__name__)

LIVE_MATCH = (MatchState.PICKBAN, MatchState.PLAYING)


@dataclass
class Tick:
    """What one sweep changed: which boards to redraw, and which beats are owed.

    The two are separate because they fail separately. A redraw is an edit of a
    message that may be gone; a beat is a new message that must be posted once
    and then stamped. Nothing here posts either -- this module never touches
    Discord.
    """

    touched: set[int]
    beats: dict[int, list[announce.Beat]]

    def note(self, match_id: int) -> None:
        self.touched.add(match_id)


async def tick(db: AsyncSession) -> Tick:
    """Advance every live match by whatever its clock now allows.

    Each match advances inside its own SAVEPOINT: this sweep is what makes the
    clock run at all, so one match that cannot advance must cost only itself
    rather than abort the transaction every other tournament shares.
    """
    changed = Tick(touched=set(), beats={})
    for match in await _live_matches(db):
        try:
            async with db.begin_nested():
                await _advance(db, match, changed)
        except Exception:
            logger.exception(
                "tournaments: match %s could not advance", match.id)
            changed.touched.discard(match.id)
    return changed


async def _advance(
    db: AsyncSession, match: TournamentMatch, changed: Tick
) -> None:
    if match.state == MatchState.PICKBAN:
        await _expire_turn(db, match, changed)
    elif match.state == MatchState.PLAYING:
        await _advance_rounds(db, match, changed)
    # Owed beats are re-derived from the round stamps rather than from the
    # transitions this pass happened to make, so a beat whose post failed --
    # or whose process died between the commit and the message -- is simply
    # still owed on the next tick.
    #
    # PICKBAN is in the list because a match returns to it BETWEEN rounds, and
    # a result beat whose post failed is still owed when it does. Leaving it
    # out would ask a player to pick before the thread had been told who won.
    if match.state in (MatchState.PICKBAN, MatchState.PLAYING, MatchState.CLOSED):
        owed = announce.owed(await rounds(db, match.id))
        if owed:
            changed.beats[match.id] = owed


async def open_round(
    db: AsyncSession, match: TournamentMatch, round_: TournamentRound
) -> None:
    """Start the validity window. Accounts go hot from here.

    ``start_ms``/``end_ms`` are set together and never move again: the window is
    what makes "played inside it" a guarantee rather than an honour system.

    The window opens at the same instant the chart is revealed, and the reveal
    is a NEW message in the thread. That is what lets the window need no
    announcement of its own: you cannot play a chart before you are told which
    one it is, so there is no earlier moment for a lenient start to reach back
    to, and nothing picked for a LATER round can be banked against this one.
    """
    round_.start_ms = now_ms()
    round_.end_ms = round_.start_ms + WINDOW_SECONDS * 1000
    round_.state = RoundState.OPEN
    await match_ops.clear_ready(db, match.id)
    await db.flush()


async def rounds(db: AsyncSession, match_id: int) -> list[TournamentRound]:
    rows = await db.execute(
        select(TournamentRound)
        .where(TournamentRound.match_id == match_id)
        .order_by(TournamentRound.ordinal)
    )
    return list(rows.scalars())


async def wins(db: AsyncSession, match_id: int) -> dict[int, int]:
    """Rounds won per side. A drawn round counts for nobody."""
    tally: dict[int, int] = {}
    for round_ in await rounds(db, match_id):
        if round_.state != RoundState.CLOSED:
            continue
        side, tied = results.winner_side(await results.standings(db, round_))
        if side is not None and not tied:
            tally[side] = tally.get(side, 0) + 1
    return tally


async def cancel(db: AsyncSession, match: TournamentMatch) -> None:
    """Stop everything. The thread stays for the record."""
    for round_ in await rounds(db, match.id):
        if round_.state in (RoundState.PENDING, RoundState.OPEN, RoundState.GRACE):
            round_.state = RoundState.CANCELLED
    match.state = MatchState.CANCELLED
    match.turn_deadline_ms = None
    await db.flush()


async def _live_matches(db: AsyncSession) -> list[TournamentMatch]:
    """Matches the sweep must look at: the live ones, plus any still owing a
    beat.

    A match that closes leaves ``LIVE_MATCH`` on the same tick that decides it,
    which is the tick its final result is announced on. If that message does
    not land, nothing would ever be selected to try again -- and the beat that
    goes missing is the one saying who won. Owing is self-limiting: a match
    drops out for good the moment its last beat is stamped.
    """
    rows = await db.execute(
        select(TournamentMatch).where(
            or_(
                TournamentMatch.state.in_(LIVE_MATCH),
                TournamentMatch.id.in_(_owing()),
            )
        )
    )
    return list(rows.scalars())


def _owing():
    """Match ids with a round whose beat has not been posted."""
    return select(TournamentRound.match_id).where(
        or_(
            TournamentRound.state.in_(announce.REVEALED)
            & TournamentRound.revealed_at.is_(None),
            (TournamentRound.state == RoundState.CLOSED)
            & TournamentRound.resulted_at.is_(None),
        )
    )


async def _expire_turn(
    db: AsyncSession, match: TournamentMatch, changed: Tick
) -> None:
    if match.turn_deadline_ms is None or now_ms() < match.turn_deadline_ms:
        return
    available = await match_ops.entries(
        db, match.id, state=PoolEntryState.AVAILABLE)
    if not available:
        return
    # Drawn ONCE and then matched: called inside the comprehension it would
    # redraw on every comparison, picking a different entry each time and
    # sometimes matching none at all.
    drawn = pickban.auto_pick([entry.id for entry in available])
    chosen = next(entry for entry in available if entry.id == drawn)
    await match_ops.act(db, match, chosen, auto=True)
    changed.note(match.id)
    if match.state == MatchState.PLAYING:
        await _open_next(db, match, changed)


async def _advance_rounds(
    db: AsyncSession, match: TournamentMatch, changed: Tick
) -> None:
    live = await rounds(db, match.id)
    now = now_ms()
    for round_ in live:
        if round_.state == RoundState.OPEN:
            await _maybe_close_window(db, round_, now, changed, match.id)
        # Not `elif`: a window that shuts because everybody has scored leaves
        # nothing to observe, so its grace is already over on the same tick.
        # Kept as two steps rather than one so a round still passes through
        # every state it is defined to have.
        if round_.state == RoundState.GRACE and await _grace_over(db, round_, now):
            round_.state = RoundState.CLOSED
            round_.closed_ms = now
            changed.note(match.id)

    if any(r.state in (RoundState.OPEN, RoundState.GRACE) for r in live):
        return
    if await _finished(db, match, live):
        return
    if any(r.state == RoundState.PENDING for r in live):
        await _open_next(db, match, changed)
        return
    # Every round is settled and the match is still live, so the only thing
    # that can make another one is the pick that names it.
    await _resume_pickban(db, match, changed)


async def _maybe_close_window(
    db: AsyncSession,
    round_: TournamentRound,
    now: int,
    changed: Tick,
    match_id: int,
) -> None:
    """``open -> grace`` on the deadline, or early once every score is in.

    This early exit is why WINDOW_SECONDS can be flat: a full set of scores is
    a result nothing can change, so a window almost never runs its full length.
    See wiki/questions/h-tournament-window-and-clock.md.
    """
    if now >= round_.end_ms:
        round_.state = RoundState.GRACE
        changed.note(match_id)
        return
    if results.all_scored(await results.standings(db, round_)):
        round_.state = RoundState.GRACE
        changed.note(match_id)


async def _grace_over(
    db: AsyncSession, round_: TournamentRound, now: int
) -> bool:
    """Whether a round's scores have stopped being gathered.

    Grace waits to OBSERVE plays the window may have cut off mid-poll, and like
    every other wait here it ends the moment that is satisfied rather than
    running a fixed length. A full set of scores IS the definition of decided
    -- it is the same condition that shut the window -- so there is nothing
    left to observe and the slack is owed only to a round still missing one.

    Without this the early ``open -> grace`` exit bought nothing at all. The
    board swapped its countdown for "Looking for scores…" and then sat on the
    already-known result until ``end_ms + grace_ms`` -- the exact instant a
    window that ran its full length would have reached anyway.
    """
    if now >= closed_at(round_):
        return True
    return results.all_scored(await results.standings(db, round_))


async def _finished(
    db: AsyncSession, match: TournamentMatch, live: list[TournamentRound]
) -> bool:
    """Close the match once it is decided, or once nothing is left to play.

    Remaining rounds are never opened; the board renders them ``unplayed``.
    """
    tally = await wins(db, match.id)
    decided = any(
        won >= match_ops.wins_needed(match.best_of) for won in tally.values())
    pending = [r for r in live if r.state == RoundState.PENDING]
    # A pick still owed is a round that does not exist yet. Without it every
    # gap between rounds -- where the round just played is closed and the next
    # has not been named -- would read as "nothing left" and close the match
    # on the first result.
    if not decided and (pending or await match_ops.turn_owed(db, match)):
        return False
    for round_ in pending:
        round_.state = RoundState.CANCELLED
    match.state = MatchState.CLOSED
    await db.flush()
    return True


async def _resume_pickban(
    db: AsyncSession, match: TournamentMatch, changed: Tick
) -> None:
    """Hand the next pick back to the player who owes it, once they have rested.

    The turn is served AFTER the rest, not alongside it. Overlapping the two
    costs less wall clock -- the pick fits inside a 300 s break with room to
    spare -- but it puts the last ask of the gap before the wait rather than
    after it, and a player who has just picked their chart expects to play it.
    Asking them to hit Ready afterwards reads as a step that should not be
    there, and the one that gets missed. See wiki/domains/tournaments.md,
    "The rest comes before the pick".

    The Ready flags that ended the rest are deliberately NOT cleared here: they
    are what lets ``_open_next`` fire on the tick after the pick, which is what
    makes the pick the last thing that happens before the chart is revealed.
    ``open_round`` clears them, so nothing carries into the window.
    """
    if not await match_ops.turn_owed(db, match):
        return
    if not await _rest_over(db, match, _last_closed(await rounds(db, match.id))):
        return
    match.state = MatchState.PICKBAN
    match.turn_deadline_ms = now_ms() + TURN_SECONDS * 1000
    await db.flush()
    changed.note(match.id)


async def _open_next(
    db: AsyncSession, match: TournamentMatch, changed: Tick
) -> None:
    """Open the next pending round once everyone is Ready, or the intermission
    has run out."""
    pending = [
        r for r in await rounds(db, match.id) if r.state == RoundState.PENDING]
    if not pending:
        return
    if not await _break_over(db, match, pending[0]):
        return
    await open_round(db, match, pending[0])
    changed.note(match.id)


async def _break_over(
    db: AsyncSession, match: TournamentMatch, next_round: TournamentRound
) -> bool:
    """Whether the rest before ``next_round`` is spent.

    The first round of a match never waits: there is no previous result.
    """
    if next_round.ordinal == 1:
        return True
    previous = await db.scalar(
        select(TournamentRound)
        .where(
            TournamentRound.match_id == match.id,
            TournamentRound.ordinal == next_round.ordinal - 1,
        )
    )
    return await _rest_over(db, match, previous)


async def _rest_over(
    db: AsyncSession, match: TournamentMatch, previous: TournamentRound | None
) -> bool:
    """Everyone Ready ends the rest early; otherwise BREAK_SECONDS does.

    Taken against the round just CLOSED rather than the one about to open,
    because between rounds the next one does not exist yet -- the pick that
    names it is served on the far side of this wait. One measurement for both
    callers, so a rest cannot be spent twice or skipped once.

    The rest runs from the moment that round was DECIDED -- past its window and
    past the grace that gathers its scores -- not from the moment the window
    shut. It is a beat to read the result in, so it cannot begin before there
    is a result to read.
    """
    if previous is None or previous.end_ms is None:
        return True
    if await _everyone_ready(db, match.id):
        return True
    return now_ms() >= closed_at(previous) + BREAK_SECONDS * 1000


def _last_closed(live: Sequence[TournamentRound]) -> TournamentRound | None:
    """The most recently decided round -- what a rest between rounds is timed
    from, and the only thing that says a rest is running at all."""
    closed = [r for r in live if r.state == RoundState.CLOSED]
    return max(closed, key=lambda r: r.ordinal) if closed else None


def closed_at(round_: TournamentRound) -> int:
    """When a round's scores stop being gathered and its result is final.

    The real close once there is one. ``end_ms + grace_ms`` is the BACKSTOP a
    round is heading for while it is still gathering, not the moment it lands
    on: grace ends early whenever every score is already in, and the break
    after a round has to run from when it was actually decided.

    Its OWN ``grace_ms``, never the next round's: grace is observation slack
    for the plays inside THIS window, so a round that carried a different one
    must be measured by the value it actually ran with.
    """
    if round_.closed_ms is not None:
        return round_.closed_ms
    return round_.end_ms + round_.grace_ms


def phase_of(
    live: Sequence[TournamentRound],
    now: int,
    *,
    turn_owed: bool = False,
) -> tuple[Phase | None, int | None, int | None]:
    """``(phase, ends_ms, ordinal)`` -- where a playing match is right now.

    One definition, read by the board and by the chat-line Ready alike, so the
    button and the words that stand in for it can never disagree about whether
    there is a break to skip.

    ``turn_owed`` is what makes the rest before an UNNAMED round visible. A
    pick is served after that rest, so between rounds there is nothing pending
    to hang a countdown off -- and without this the board would show an idle
    match and no Ready would be accepted for the one wait that has one.

    A rest the clock has already run out on is NOT a break. It reads as one
    from the rounds alone -- a pending round whose predecessor closed long ago
    is exactly the state a match is in for the few seconds between a pick and
    the sweep that opens it -- and reporting it there would post a second Ready
    prompt counting down to a moment already past, which is the ask this
    ordering exists to delete.
    """
    for round_ in live:
        if round_.state == RoundState.OPEN:
            return "open", round_.end_ms, round_.ordinal
        if round_.state == RoundState.GRACE:
            return "grace", closed_at(round_), round_.ordinal
    pending = next(
        (r for r in live if r.state == RoundState.PENDING), None)
    if pending is not None:
        previous = next(
            (r for r in live if r.ordinal == pending.ordinal - 1), None)
        if previous is None or previous.end_ms is None:
            return None, None, None
        return _rest(previous, pending.ordinal, now)
    # Every round settled and a pick still owed: the rest before a round that
    # the next turn will name. Gated on the owed turn, never on "nothing
    # pending" alone -- a decided match looks identical from here, and would
    # otherwise print a countdown to a round that will never be played.
    previous = _last_closed(live)
    if not turn_owed or previous is None or previous.end_ms is None:
        return None, None, None
    return _rest(previous, previous.ordinal + 1, now)


def _rest(
    previous: TournamentRound, ordinal: int, now: int
) -> tuple[Phase | None, int | None, int | None]:
    """The rest after ``previous``, as a phase -- or nothing once it is spent."""
    ends = closed_at(previous) + BREAK_SECONDS * 1000
    if now >= ends:
        return None, None, None
    return "break", ends, ordinal


async def _everyone_ready(db: AsyncSession, match_id: int) -> bool:
    rows = await db.execute(
        select(TournamentParticipant.ready_at).where(
            TournamentParticipant.match_id == match_id)
    )
    flags = list(rows.scalars())
    return bool(flags) and all(flag is not None for flag in flags)

