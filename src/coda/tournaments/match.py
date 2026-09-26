"""Match CRUD, roster, pool and the transitions between them. DB only.

A match owns everything Discord-facing -- roster, pool, pick/ban, best-of -- and
spawns rounds. It never reads a score; that is the round's job, and the only
one it has.

A quick match is a match with ``tournament_id IS NULL``. That is the whole
difference: not a second code path, and not a flag that changes any rule.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from coda.db.enums import (
    DifficultyClass,
    MatchState,
    PoolEntryState,
    RoundState,
    ThreadVisibility,
)
from coda.db.models import (
    TournamentChart,
    TournamentMatch,
    TournamentParticipant,
    TournamentPoolEntry,
    TournamentRound,
)
from coda.tournaments import pickban, pool
from coda.tournaments.constants import GRACE_SECONDS, TURN_SECONDS
from coda.tournaments.levels import LevelRange


@dataclass(frozen=True)
class MatchOptions:
    """Everything ``/tournament quick`` resolved to."""

    levels: LevelRange
    difficulty_class: DifficultyClass | None
    best_of: int
    pick_ban: bool
    # Who may PLAY, where visibility is who may read. A closed match is the
    # roster it was opened with; an open one takes anyone who can see it.
    open_join: bool
    visibility: ThreadVisibility


def now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


async def create(
    db: AsyncSession,
    *,
    guild_id: int,
    home_channel_id: int,
    thread_id: int,
    creator_discord_id: int,
    roster: Sequence[int],
    options: MatchOptions,
    names: Mapping[int, str | None] | None = None,
) -> TournamentMatch:
    """Open a match in ``draft``. The roster may still grow until it starts.

    ``names`` are the players' DISCORD names, by account id, captured by the
    caller while it still held the real user objects. Absent ones fall back to
    the Arcaea name on the board.
    """
    match = TournamentMatch(
        guild_id=guild_id,
        home_channel_id=home_channel_id,
        thread_id=thread_id,
        visibility=options.visibility,
        open_join=options.open_join,
        pick_ban=options.pick_ban,
        best_of=options.best_of,
        difficulty_class=options.difficulty_class,
        level_min=options.levels.low,
        level_max=options.levels.high,
        state=MatchState.DRAFT,
        creator_discord_id=creator_discord_id,
    )
    db.add(match)
    await db.flush()
    for side, account_id in enumerate(roster):
        db.add(
            TournamentParticipant(
                match_id=match.id,
                arcaea_account_id=account_id,
                side_index=side,
                display_name=(names or {}).get(account_id),
            )
        )
    await db.flush()
    return match


async def roster(db: AsyncSession, match_id: int) -> list[TournamentParticipant]:
    """The roster in side order."""
    rows = await db.execute(
        select(TournamentParticipant)
        .where(TournamentParticipant.match_id == match_id)
        .order_by(TournamentParticipant.side_index)
    )
    return list(rows.scalars())


async def join(
    db: AsyncSession,
    match: TournamentMatch,
    account_id: int,
    display_name: str | None = None,
) -> bool:
    """Add one account while the match is still forming. False if already in."""
    existing = await roster(db, match.id)
    if any(p.arcaea_account_id == account_id for p in existing):
        return False
    db.add(
        TournamentParticipant(
            match_id=match.id,
            arcaea_account_id=account_id,
            side_index=len(existing),
            display_name=display_name,
        )
    )
    # A new wait: what the others confirmed was a two-player match, and this is
    # not that match. Everyone answers the roster they are actually playing.
    await clear_ready(db, match.id)
    await db.flush()
    return True


async def leave(db: AsyncSession, match: TournamentMatch, account_id: int) -> bool:
    """Remove one account and close the gap in ``side_index``.

    Reindexing rather than leaving a hole: side_index IS the turn order and the
    board side, so a gap would put a pick/ban turn on nobody.
    """
    members = await roster(db, match.id)
    leaving = next(
        (p for p in members if p.arcaea_account_id == account_id), None)
    if leaving is None:
        return False
    await db.delete(leaving)
    await db.flush()
    for side, participant in enumerate(
        p for p in members if p.arcaea_account_id != account_id
    ):
        participant.side_index = side
    await db.flush()
    return True


def spec_of(match: TournamentMatch, roster_size: int) -> pool.PoolSpec:
    """The pool the match's stored filters describe."""
    return pool.PoolSpec(
        levels=LevelRange(match.level_min, match.level_max),
        difficulty_class=match.difficulty_class,
        size=pickban.pool_size(match.best_of, roster_size, match.pick_ban),
    )


def spec_for(options: MatchOptions, roster_size: int) -> pool.PoolSpec:
    """The same pool, from options a match has not been opened with yet."""
    return pool.PoolSpec(
        levels=options.levels,
        difficulty_class=options.difficulty_class,
        size=pickban.pool_size(options.best_of, roster_size, options.pick_ban),
    )


async def start(
    db: AsyncSession, match: TournamentMatch
) -> pool.Shortfall | None:
    """Freeze the roster, generate the pool, and enter pick/ban or playing.

    Returns a ``Shortfall`` and changes nothing when the filters cannot fill the
    pool -- the format is never silently shrunk.
    """
    members = await roster(db, match.id)
    spec = spec_of(match, len(members))
    drawn = await pool.generate(
        db, spec, [p.arcaea_account_id for p in members])
    if isinstance(drawn, pool.Shortfall):
        return drawn

    for ordinal, candidate in enumerate(drawn):
        db.add(
            TournamentPoolEntry(
                match_id=match.id,
                song_id=candidate.song_id,
                song_difficulty_id=candidate.song_difficulty_id,
                ordinal=ordinal,
            )
        )
    await db.flush()

    # The draft confirmations answered "are you here"; every wait from here
    # asks something else, and a flag that outlives its wait answers the next
    # one on the player's behalf.
    await clear_ready(db, match.id)
    if len(members) == 2 and match.pick_ban:
        match.state = MatchState.PICKBAN
        # Alternation needs a start, and a fixed one is an advantage.
        match.turn_index = 0
        match.turn_deadline_ms = now_ms() + TURN_SECONDS * 1000
        await _shuffle_sides(db, members)
    else:
        match.state = MatchState.PLAYING
        await _rounds_without_pickban(db, match, len(members))
    await db.flush()
    return None


async def entries(
    db: AsyncSession, match_id: int, *, state: PoolEntryState | None = None
) -> list[TournamentPoolEntry]:
    """Pool entries in board order."""
    query = select(TournamentPoolEntry).where(
        TournamentPoolEntry.match_id == match_id)
    if state is not None:
        query = query.where(TournamentPoolEntry.state == state)
    rows = await db.execute(query.order_by(TournamentPoolEntry.ordinal))
    return list(rows.scalars())


async def act(
    db: AsyncSession,
    match: TournamentMatch,
    entry: TournamentPoolEntry,
    *,
    auto: bool,
) -> None:
    """Apply one pick or ban and advance the turn.

    A pick spawns its round as ``pending`` immediately, so the round order is
    the pick order with no second pass to get wrong.
    """
    turn = pickban.turn_at(match.turn_index, match.best_of)
    if turn is None:
        return
    actor = await _side_account(db, match.id, turn.side_index)
    entry.state = (
        PoolEntryState.BANNED if turn.action == "ban" else PoolEntryState.PICKED
    )
    entry.acted_by = actor
    entry.acted_at = datetime.now(timezone.utc)
    entry.auto = auto
    if turn.action == "pick":
        round_ = await spawn_round(db, match, entry)
        entry.round_id = round_.id

    match.turn_index += 1
    if pickban.turn_at(match.turn_index, match.best_of) is None:
        await _close_pickban(db, match)
    elif turn.action == "pick":
        # One pick, one round: the chart just named is played before the next
        # is asked for, which is the only way a pick can answer the score.
        # `service` hands the turn back once that round is over.
        match.state = MatchState.PLAYING
        match.turn_deadline_ms = None
    else:
        match.turn_deadline_ms = now_ms() + TURN_SECONDS * 1000
    await db.flush()


async def spawn_round(
    db: AsyncSession, match: TournamentMatch, entry: TournamentPoolEntry
) -> TournamentRound:
    """Create the ``pending`` round one pool entry becomes."""
    ordinal = await db.scalar(
        select(func.count())
        .select_from(TournamentRound)
        .where(TournamentRound.match_id == match.id)
    )
    round_ = TournamentRound(
        match_id=match.id,
        ordinal=ordinal + 1,
        state=RoundState.PENDING,
        grace_ms=GRACE_SECONDS * 1000,
    )
    db.add(round_)
    await db.flush()
    await _write_chart_set(db, match, round_, [entry])
    return round_


def wins_needed(best_of: int) -> int:
    return math.ceil(best_of / 2)


async def turn_owed(db: AsyncSession, match: TournamentMatch) -> bool:
    """Whether the pick/ban sequence still has a turn to serve this match.

    The roster is re-read rather than the match state trusted: above two
    players, or with banning off, ``start`` spawned every round up front and
    ``turn_index`` never leaves 0 -- which the sequence alone would read as a
    ban still owed, and no such match would ever close.
    """
    if not match.pick_ban or len(await roster(db, match.id)) != 2:
        return False
    return pickban.turn_at(match.turn_index, match.best_of) is not None


async def clear_ready(db: AsyncSession, match_id: int) -> None:
    """A new wait begins, so nobody is Ready for it yet."""
    await db.execute(
        update(TournamentParticipant)
        .where(TournamentParticipant.match_id == match_id)
        .values(ready_at=None)
    )


async def _close_pickban(db: AsyncSession, match: TournamentMatch) -> None:
    """The survivor becomes the decider and plays last.

    Reached only on the LAST pick, so the decider's round is spawned behind the
    one that pick just made -- which is what keeps it last in ordinal order
    however few of the rounds before it are reached.
    """
    left = await entries(db, match.id, state=PoolEntryState.AVAILABLE)
    if left:
        decider = left[0]
        decider.state = PoolEntryState.PICKED
        round_ = await spawn_round(db, match, decider)
        decider.round_id = round_.id
    match.state = MatchState.PLAYING
    match.turn_deadline_ms = None


async def _rounds_without_pickban(
    db: AsyncSession, match: TournamentMatch, roster_size: int
) -> None:
    """Rounds for a match that never picks or bans.

    Above two players the whole pool is ONE round's chart set -- the casual
    lobby shape. At two with banning off, the pool is consumed in order.
    """
    drawn = await entries(db, match.id)
    if roster_size > 2:
        round_ = TournamentRound(
            match_id=match.id,
            ordinal=1,
            state=RoundState.PENDING,
            grace_ms=GRACE_SECONDS * 1000,
        )
        db.add(round_)
        await db.flush()
        await _write_chart_set(db, match, round_, drawn)
        for entry in drawn:
            entry.state = PoolEntryState.PICKED
            entry.round_id = round_.id
        return

    for entry in drawn[: match.best_of]:
        entry.state = PoolEntryState.PICKED
        round_ = await spawn_round(db, match, entry)
        entry.round_id = round_.id


async def _write_chart_set(
    db: AsyncSession,
    match: TournamentMatch,
    round_: TournamentRound,
    for_entries: Sequence[TournamentPoolEntry],
) -> None:
    """Resolve entries into the round's eligible charts.

    In song mode an entry is a song, so its set is re-derived from the match's
    stored filters -- the band still bounds it, or a lv9-10 casual round could
    be won on a PST 4.
    """
    levels = LevelRange(match.level_min, match.level_max)
    playing = [member.arcaea_account_id for member in await roster(db, match.id)]
    seen: set[int] = set()
    for entry in for_entries:
        if entry.song_difficulty_id is not None:
            ids = [entry.song_difficulty_id]
        else:
            charts = await pool.qualifying(
                db, levels, match.difficulty_class, playing, song_id=entry.song_id
            )
            ids = [chart.id for chart, _ in charts]
        for difficulty_id in ids:
            if difficulty_id in seen:
                continue
            seen.add(difficulty_id)
            db.add(
                TournamentChart(
                    round_id=round_.id, song_difficulty_id=difficulty_id)
            )
    await db.flush()


async def _shuffle_sides(
    db: AsyncSession, members: Sequence[TournamentParticipant]
) -> None:
    """Randomise who acts first. Shown on the board."""
    order = list(members)
    random.shuffle(order)
    for side, participant in enumerate(order):
        participant.side_index = side
    await db.flush()


async def _side_account(db: AsyncSession, match_id: int, side: int) -> int | None:
    return await db.scalar(
        select(TournamentParticipant.arcaea_account_id).where(
            TournamentParticipant.match_id == match_id,
            TournamentParticipant.side_index == side,
        )
    )
