"""Reading and writing a player's declared chart set.

One write primitive, :func:`replace`, serves every surface: a pack tick, a song
toggle and a Beyond answer differ only in which chart ids they resolve to.

Two predicates decide what a declaration covers, and the gap between them is
deliberate: :func:`_pack_granted` is what ticking a pack WRITES, :func:`_ownable`
is what unticking one CLEARS. Grant and clear over the same set either orphans a
pack's Beyond rows or wipes them on every re-tick.

The pack checkmark counts :func:`_pack_granted` as well, so a chart the writer
skips must be one the counter skips too -- otherwise a whole-pack tick can never
read as fully owned and the picker looks broken with no error anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import ColumnElement, delete, distinct, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from coda.db.enums import DifficultyClass
from coda.db.models import OwnedChart, PlayScore, Song, SongDifficulty

# Answered on their own page, never granted by the pack: 66 of 67 Beyonds need
# a world map or story progression that owning the pack says nothing about.
BEYOND = (DifficultyClass.BYD, DifficultyClass.BYD_2)

# Free to everyone, so never worth a tick. Granted with the first real
# declaration rather than dropped, because "not asked" must not become "cannot
# play" -- and because its 20 Beyonds are gated like any other.
FREE_PACK_IDS = frozenset({"base"})

# A score proves the whole PACK only where the song cannot be had on its own.
# These three release song-by-song -- `base` free, `single` individually sold,
# `extend_*` handed out incrementally through world mode -- so a score inside
# one proves the song and nothing more.
SONG_BY_SONG_PACK_IDS = FREE_PACK_IDS | {"single"}
SONG_BY_SONG_PACK_PREFIX = "extend"


@dataclass(frozen=True)
class BeyondEntry:
    """One Beyond offered on the answer page.

    ``declared`` is a claim and can be retracted; ``proven`` is a stored play on
    that very chart and cannot, because ``playable_chart_ids`` unions plays in
    regardless of what the page says.
    """

    chart: SongDifficulty
    song: Song
    declared: bool
    proven: bool

    @property
    def owned(self) -> bool:
        return self.declared or self.proven


@dataclass(frozen=True)
class PackCount:
    """How much of one pack a player has declared."""

    pack_id: str
    pack_name: str
    total: int
    owned: int

    @property
    def checked(self) -> bool:
        return self.total > 0 and self.owned == self.total


def _not_delisted() -> ColumnElement[bool]:
    """A delisted song is unreachable for everyone, buyers included, so it is
    never part of a playable set. Mirrors ``catalog.search.is_delisted``."""
    return ~Song.name_en.like(r"\_%\_", escape="\\")


def _ownable() -> list[ColumnElement[bool]]:
    """Every chart a declaration may ever cover. err is out of scope entirely."""
    return [SongDifficulty.difficulty != DifficultyClass.ERR, _not_delisted()]


def _pack_granted() -> list[ColumnElement[bool]]:
    """Charts a pack tick GRANTS -- the ownable set minus Beyond.

    Narrower than :func:`_ownable` on purpose, and the difference is what makes
    unticking work: a pack is cleared over its ownable charts so its Beyond
    answers go with it, but ticking one may never grant a Beyond back.
    """
    return [SongDifficulty.difficulty.notin_(BEYOND), *_ownable()]


async def replace(
    db: AsyncSession, account_id: int, *, owned: set[int], within: set[int]
) -> None:
    """Make ``owned`` the declared set within ``within``, leaving the rest alone.

    Scoped rather than absolute because a select menu reports only its own
    chunk's selection: anything outside that chunk was never on screen and must
    survive the write untouched. A write that adds anything also brings the free
    packs along, which is the only way they are ever granted.

    Flushes without committing -- one interaction may write more than once, so
    the command owns the transaction.
    """
    dropped = within - owned
    if dropped:
        await db.execute(
            delete(OwnedChart).where(
                OwnedChart.arcaea_account_id == account_id,
                OwnedChart.song_difficulty_id.in_(dropped),
            )
        )
    added = owned & within
    if added:
        # The base game rides along with whatever the player actually answered:
        # it is off the picker, so this is the only thing that puts it in reach.
        added |= await charts_in_packs(db, set(FREE_PACK_IDS))
    if added:
        await db.execute(
            insert(OwnedChart)
            .values(
                [
                    {"arcaea_account_id": account_id, "song_difficulty_id": chart_id}
                    for chart_id in sorted(added)
                ]
            )
            .on_conflict_do_nothing()
        )
    await db.flush()


async def clear_all(db: AsyncSession, account_id: int) -> None:
    """Undeclare everything, returning the account to unconstrained."""
    await db.execute(
        delete(OwnedChart).where(OwnedChart.arcaea_account_id == account_id)
    )
    await db.flush()


async def charts_in_packs(
    db: AsyncSession, pack_ids: set[str], *, include_beyond: bool = False
) -> set[int]:
    """Charts in those packs -- what a tick grants, or what unticking clears."""
    if not pack_ids:
        return set()
    rows = await db.scalars(
        select(SongDifficulty.id)
        .join(Song, Song.song_id == SongDifficulty.song_id)
        .where(
            Song.pack_id.in_(pack_ids),
            *(_ownable() if include_beyond else _pack_granted()),
        )
    )
    return set(rows)


async def charts_in_song(
    db: AsyncSession, song_id: str, *, include_beyond: bool = False
) -> set[int]:
    """Charts of one song -- what a tick grants, or what unticking clears."""
    rows = await db.scalars(
        select(SongDifficulty.id)
        .join(Song, Song.song_id == SongDifficulty.song_id)
        .where(
            Song.song_id == song_id,
            *(_ownable() if include_beyond else _pack_granted()),
        )
    )
    return set(rows)


async def pack_counts(db: AsyncSession, account_id: int) -> list[PackCount]:
    """Declared-vs-total per pack, counted over exactly what a tick writes.

    Grouped by ``songs.pack_name`` as well as id because the display name is
    per-song and may disagree with ``packs.name``; the caller picks the winner.
    """
    rows = await db.execute(
        select(
            Song.pack_id,
            Song.pack_name,
            func.count(SongDifficulty.id),
            func.count(OwnedChart.song_difficulty_id),
        )
        .select_from(SongDifficulty)
        .join(Song, Song.song_id == SongDifficulty.song_id)
        .outerjoin(
            OwnedChart,
            (OwnedChart.song_difficulty_id == SongDifficulty.id)
            & (OwnedChart.arcaea_account_id == account_id),
        )
        .where(Song.pack_id.isnot(None), *_pack_granted())
        .group_by(Song.pack_id, Song.pack_name)
    )
    return [
        PackCount(pack_id=pack_id, pack_name=pack_name, total=total, owned=owned)
        for pack_id, pack_name, total, owned in rows.all()
    ]


async def beyond_charts(db: AsyncSession, account_id: int) -> list[BeyondEntry]:
    """Every Beyond of a song the player holds, and whether it is already theirs.

    A song counts as held when it was declared OR sits in a pack the player's
    plays prove -- otherwise someone whose packs are all inferred opens an empty
    page and can never answer a Beyond at all.

    A score on the chart is reported separately from a stored answer, because it
    is not a tick the player may take back -- see ``BeyondEntry``.

    ORM rows rather than a flat projection: a Beyond's name and version are
    routinely chart-level overrides (53 of them override ``version``), so the
    caller has to resolve effective values and the ``alt`` appearance itself.
    """
    held_songs = (
        select(SongDifficulty.song_id)
        .join(OwnedChart, OwnedChart.song_difficulty_id == SongDifficulty.id)
        .where(
            OwnedChart.arcaea_account_id == account_id,
            SongDifficulty.difficulty.notin_(BEYOND),
        )
        .scalar_subquery()
    )
    played = (
        select(PlayScore.id)
        .where(
            PlayScore.arcaea_account_id == account_id,
            PlayScore.song_difficulty_id == SongDifficulty.id,
        )
        .exists()
    )
    rows = await db.execute(
        select(SongDifficulty, Song, OwnedChart.song_difficulty_id.isnot(None), played)
        .join(Song, Song.song_id == SongDifficulty.song_id)
        .outerjoin(
            OwnedChart,
            (OwnedChart.song_difficulty_id == SongDifficulty.id)
            & (OwnedChart.arcaea_account_id == account_id),
        )
        .where(
            SongDifficulty.difficulty.in_(BEYOND),
            or_(
                SongDifficulty.song_id.in_(held_songs),
                Song.pack_id.in_(await inferred_pack_ids(db, account_id)),
            ),
            _not_delisted(),
        )
    )
    return [
        BeyondEntry(chart=chart, song=song, declared=declared, proven=proven)
        for chart, song, declared, proven in rows.all()
    ]


async def inferred_pack_ids(db: AsyncSession, account_id: int) -> set[str]:
    """Packs a stored play proves outright: you cannot score on a song you could
    not reach, and outside the song-by-song packs a song comes only with its pack.

    The exemption is per PACK and nothing else. ``world_unlock`` is deliberately
    not consulted: a world-mode unlock inside a paid pack still needs that pack
    bought, because the map ships inside it (owner, 2026-09-06). Every song whose
    map has a cross-pack prerequisite -- ``guardina``, ``diein``, ``desive``,
    ``acheron``, ``chronologia`` -- lives in ``single`` and is exempt already.

    Not reading the flag also puts the [[h-world-unlock-corrections|18 stale
    rows]] out of reach of ownership entirely.
    """
    rows = await db.scalars(
        select(distinct(Song.pack_id))
        .select_from(PlayScore)
        .join(SongDifficulty, SongDifficulty.id == PlayScore.song_difficulty_id)
        .join(Song, Song.song_id == SongDifficulty.song_id)
        .where(
            PlayScore.arcaea_account_id == account_id,
            Song.pack_id.isnot(None),
            Song.pack_id.notin_(SONG_BY_SONG_PACK_IDS),
            ~Song.pack_id.like(f"{SONG_BY_SONG_PACK_PREFIX}%"),
        )
    )
    return set(rows)


async def declared_chart_ids(db: AsyncSession, account_id: int) -> set[int]:
    """The rows as stored, with no ``has_score`` union."""
    rows = await db.scalars(
        select(OwnedChart.song_difficulty_id).where(
            OwnedChart.arcaea_account_id == account_id
        )
    )
    return set(rows)


async def playable_chart_ids(db: AsyncSession, account_id: int) -> set[int] | None:
    """What this account can play, or ``None`` when it has never declared.

    ``None`` is not "owns nothing" -- an account that never answered is
    unconstrained, and every reader must treat it that way or one silent
    participant empties a pool. A played chart is owned by proof, whatever was
    declared.

    Inference from plays only ever ADDS to an existing declaration; it can never
    make an undeclared account declared. Someone with scores in three packs has
    not told us they own only three.
    """
    declared = await declared_chart_ids(db, account_id)
    if not declared:
        return None
    played = await db.scalars(
        select(distinct(PlayScore.song_difficulty_id)).where(
            PlayScore.arcaea_account_id == account_id,
            PlayScore.song_difficulty_id.isnot(None),
        )
    )
    inferred = await charts_in_packs(db, await inferred_pack_ids(db, account_id))
    return declared | set(played) | inferred
