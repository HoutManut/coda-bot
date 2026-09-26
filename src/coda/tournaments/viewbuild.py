"""DB -> ``MatchView``. The last place a query runs before the board is drawn.

Everything Discord-facing reads the view and nothing else, which is what lets
the text board and a future composed image share one data path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from coda.catalog.labels import format_cc
from coda.catalog.resolution import effective
from coda.catalog.spoilers import chart_spoilered
from coda.db.enums import MatchState, PoolEntryState, RoundState
from coda.db.models import (
    ArcaeaAccount,
    PlayerLink,
    Song,
    SongDifficulty,
    TournamentMatch,
    TournamentRound,
)
from coda.tournaments import match as match_ops
from coda.tournaments import results, service
from coda.tournaments.levels import LevelRange
from coda.tournaments.match import now_ms
from coda.tournaments.pickban import turn_at
from coda.tournaments.views import (
    ChartRef,
    EntryState,
    MatchView,
    PoolEntry,
    RoundResult,
    Side,
    SideScore,
    Turn,
)
from coda.utils.encoding import decode_level

UNKNOWN = "?"


@dataclass(frozen=True)
class Named:
    """One account's two identities: what the board calls it, and what pings."""

    name: str
    discord_id: int | None


async def build(db: AsyncSession, match: TournamentMatch) -> MatchView:
    """The whole board, as of now."""
    members = await match_ops.roster(db, match.id)
    names = await _names(db, [p.arcaea_account_id for p in members])
    tally = await service.wins(db, match.id)
    live = await service.rounds(db, match.id)
    rounds = {r.id: r for r in live}

    sides = [
        Side(
            arcaea_name=names[p.arcaea_account_id].name,
            discord_name=p.display_name,
            discord_id=names[p.arcaea_account_id].discord_id,
            rounds_won=tally.get(p.side_index, 0),
            ready=p.ready_at is not None,
        )
        for p in members
    ]
    by_account = {p.arcaea_account_id: p.side_index for p in members}

    pool = []
    for entry in await match_ops.entries(db, match.id):
        round_ = rounds.get(entry.round_id) if entry.round_id else None
        pool.append(
            PoolEntry(
                entry_id=entry.id,
                chart=await _chart_ref(db, entry.song_difficulty_id),
                song_title=await _song_title(db, entry.song_id),
                state=_entry_state(match.state, entry.state, round_),
                acted_by_side=by_account.get(entry.acted_by),
                auto=entry.auto,
                acted_at_ms=_ms(entry.acted_at),
                round_ordinal=round_.ordinal if round_ else None,
                result=(
                    await _result(db, round_, by_account) if round_ else None),
            )
        )

    now = now_ms()
    phase, phase_ends_ms, phase_ordinal = (
        service.phase_of(
            live, now, turn_owed=await match_ops.turn_owed(db, match))
        if match.state == MatchState.PLAYING
        else (None, None, None)
    )
    return MatchView(
        match_id=match.id,
        kind="quick" if match.tournament_id is None else "tournament",
        stage_label=match.stage_label,
        state=match.state,
        best_of=match.best_of,
        pick_ban=match.pick_ban,
        open_join=match.open_join,
        levels=LevelRange(match.level_min, match.level_max),
        difficulty_class=match.difficulty_class,
        sides=sides,
        pool=pool,
        turn=_turn(match),
        winner_side=_winner(match, tally),
        phase=phase,
        phase_ends_ms=phase_ends_ms,
        phase_ordinal=phase_ordinal,
        now_ms=now,
    )


def _turn(match: TournamentMatch) -> Turn | None:
    if match.state != MatchState.PICKBAN or match.turn_deadline_ms is None:
        return None
    turn = turn_at(match.turn_index, match.best_of)
    if turn is None:
        return None
    return Turn(
        index=turn.index,
        side_index=turn.side_index,
        action=turn.action,
        deadline_ms=match.turn_deadline_ms,
    )


def _winner(match: TournamentMatch, tally: dict[int, int]) -> int | None:
    if match.state != MatchState.CLOSED or not tally:
        return None
    best = max(tally.values())
    leaders = [side for side, won in tally.items() if won == best]
    return leaders[0] if len(leaders) == 1 else None


def _entry_state(
    match_state: MatchState, state: PoolEntryState, round_: TournamentRound | None
) -> EntryState:
    """A picked entry reads by what its round did, not by the pick."""
    if state == PoolEntryState.AVAILABLE:
        # Picks are served between rounds, so a match that ends early leaves
        # the rest of its pool undrafted. Those entries were never banned and
        # never played, and "available" would read as still on the table.
        return (
            "unplayed"
            if match_state in (MatchState.CLOSED, MatchState.CANCELLED)
            else "available"
        )
    if state != PoolEntryState.PICKED or round_ is None:
        return state.value
    return {
        RoundState.PENDING: "picked",
        RoundState.OPEN: "playing",
        RoundState.GRACE: "playing",
        RoundState.CLOSED: "played",
        RoundState.CANCELLED: "unplayed",
    }[round_.state]


async def _result(
    db: AsyncSession, round_: TournamentRound, by_account: dict[int, int]
) -> RoundResult | None:
    if round_.state == RoundState.PENDING:
        return None
    rows = await results.standings(db, round_)
    side, tied = results.winner_side(rows)
    ordered = sorted(rows, key=lambda r: by_account.get(r.arcaea_account_id, 0))
    return RoundResult(
        ordinal=round_.ordinal,
        scores=[
            SideScore(
                score=row.score,
                time_played_ms=row.time_played,
                chart=await _chart_ref(db, row.song_difficulty_id),
            )
            for row in ordered
        ],
        winner_side=side,
        tied=tied,
    )


async def _chart_ref(
    db: AsyncSession, difficulty_id: int | None
) -> ChartRef | None:
    if difficulty_id is None:
        return None
    row = await db.execute(
        select(SongDifficulty, Song)
        .join(Song, Song.song_id == SongDifficulty.song_id)
        .where(SongDifficulty.id == difficulty_id)
    )
    pair = row.first()
    if pair is None:
        return None
    chart, song = pair
    return ChartRef(
        # effective(), never songs.name_en: a Beyond chart with its own name is
        # a different chart to a player, and "Pragmatism BYD" does not name the
        # chart they are being asked to play.
        title=effective(song, chart, "name_en"),
        artist=effective(song, chart, "artist") or "",
        difficulty_class=chart.difficulty,
        alt=chart.alt,
        # A sentinel renders "?", never a decoded number.
        level_display=decode_level(chart.level),
        cc_display=format_cc(chart.rating) or UNKNOWN,
        spoilered=chart_spoilered(song, chart),
    )


def _ms(at: datetime | None) -> int | None:
    return None if at is None else int(at.timestamp() * 1000)


async def _song_title(db: AsyncSession, song_id: str) -> str:
    return await db.scalar(
        select(Song.name_en).where(Song.song_id == song_id)) or song_id


async def _names(
    db: AsyncSession, account_ids: list[int]
) -> dict[int, Named]:
    """The Arcaea name, and the Discord id a beat pings.

    ``discord_id`` lives on ``player_links``, not on the account -- many Discord
    users may share one Arcaea account. ``is_owner`` marks "the single link that
    speaks for it", so that link is preferred and the oldest link breaks a tie;
    the join is LEFT so an account with no link at all still reaches the board
    under its Arcaea name.
    """
    rows = await db.execute(
        select(
            ArcaeaAccount.id, ArcaeaAccount.display_name, PlayerLink.discord_id
        )
        .outerjoin(PlayerLink, PlayerLink.arcaea_account_id == ArcaeaAccount.id)
        .where(ArcaeaAccount.id.in_(account_ids))
        .distinct(ArcaeaAccount.id)
        .order_by(
            ArcaeaAccount.id,
            PlayerLink.is_owner.desc().nullslast(),
            PlayerLink.linked_at,
        )
    )
    found = {
        account_id: Named(name or f"player {account_id}", discord_id)
        for account_id, name, discord_id in rows.all()
    }
    return {
        account_id: found.get(account_id, Named(UNKNOWN, None))
        for account_id in account_ids
    }
