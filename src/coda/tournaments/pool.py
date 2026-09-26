"""Generating a match's chart pool from the organizer's filters.

The pool is an explicit organizer choice and is never derived from player
ratings or catalog inference. A filter the organizer supplies is still the
organizer choosing, which is why generation exists at all.

``difficulty_class = None`` is SONG MODE: an entry is a song and the round's
chart set is every one of its qualifying difficulties, so the player picks the
difficulty. The level band still bounds that set -- a lv9-10 casual match must
not be winnable by posting 10,000,000 on a PST 4.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from coda.catalog.resolution import effective
from coda.catalog.search import is_delisted
from coda.catalog.spoilers import chart_spoilered
from coda.db.enums import DifficultyClass
from coda.db.models import Song, SongDifficulty
from coda.ownership.service import playable_chart_ids
from coda.tournaments.levels import LevelRange


@dataclass(frozen=True)
class PoolSpec:
    """What a pool is drawn from."""

    levels: LevelRange
    # None = any = song mode.
    difficulty_class: DifficultyClass | None
    size: int

    @property
    def song_mode(self) -> bool:
        return self.difficulty_class is None


@dataclass(frozen=True)
class PoolCandidate:
    """One offer. ``song_difficulty_id`` is None in song mode."""

    song_id: str
    song_difficulty_id: int | None
    title: str


@dataclass(frozen=True)
class Shortfall:
    """The filters did not yield enough charts to run the format."""

    found: int
    needed: int


async def candidates(
    db: AsyncSession, spec: PoolSpec, roster: Sequence[int]
) -> list[PoolCandidate]:
    """Everything the filters offer, before the draw narrows it to ``size``.

    Split out from ``generate`` so a match can be refused at the command that
    asks for it, back when a bad level band is still one ephemeral line and not
    a thread two people have already been pinged into.
    """
    charts = await qualifying(db, spec.levels, spec.difficulty_class, roster)
    return _collapse(charts, spec)


async def generate(
    db: AsyncSession, spec: PoolSpec, roster: Sequence[int]
) -> list[PoolCandidate] | Shortfall:
    """Draw a pool, or say by how much the filters fell short.

    Never silently shrinks the format: a Bo5 needs seven entries and a
    five-entry draw is a refusal, not a smaller match.
    """
    offered = await candidates(db, spec, roster)
    if len(offered) < spec.size:
        return Shortfall(found=len(offered), needed=spec.size)
    return random.sample(offered, spec.size)


async def qualifying(
    db: AsyncSession,
    levels: LevelRange,
    difficulty_class: DifficultyClass | None,
    roster: Sequence[int],
    *,
    song_id: str | None = None,
) -> list[tuple[SongDifficulty, Song]]:
    """Every chart the filters admit, against the newest catalog state.

    Takes the filters rather than a ``PoolSpec`` because the round's chart set
    in song mode is the same question minus the size: the set is re-derived
    from the match's stored filters at round-spawn time, which is what the
    ``song_id`` narrows it to.

    The roster's ownership is applied HERE rather than by the caller so that
    re-derivation cannot forget it: in song mode a song enters the pool because
    one of its charts is playable, and the round's set is built from a second
    call that would otherwise admit the whole song.
    """
    conditions = [
        # Without this, TBA (0) and N/A (-1) sort into a low band and get drawn.
        SongDifficulty.level > 0,
    ]
    if levels.low is not None:
        conditions.append(SongDifficulty.level >= levels.low)
    if levels.high is not None:
        conditions.append(SongDifficulty.level <= levels.high)
    if difficulty_class is not None:
        conditions.append(SongDifficulty.difficulty == difficulty_class)
    if song_id is not None:
        conditions.append(SongDifficulty.song_id == song_id)

    rows = await db.execute(
        select(SongDifficulty, Song)
        .join(Song, Song.song_id == SongDifficulty.song_id)
        .where(and_(*conditions))
    )
    drawable = [pair for pair in rows.all() if _drawable(*pair)]
    return await owned_by_all(db, drawable, roster)


async def owned_by_all(
    db: AsyncSession,
    charts: list[tuple[SongDifficulty, Song]],
    roster: Sequence[int],
) -> list[tuple[SongDifficulty, Song]]:
    """Charts every participant can play.

    Always applied and never optional -- a player cannot play a chart they do
    not own, so this is a property of a valid pool rather than a preference.

    A participant who has never run ``/owned`` is UNCONSTRAINED, not
    empty-handed: absence of a declaration is not a denial (see
    wiki/domains/catalog.md §Ownership), and reading it as one would empty every
    pool containing one silent player.
    """
    playable: set[int] | None = None
    for account_id in roster:
        theirs = await playable_chart_ids(db, account_id)
        if theirs is None:
            continue
        playable = theirs if playable is None else playable & theirs
    if playable is None:
        return charts
    return [pair for pair in charts if pair[0].id in playable]



def _drawable(chart: SongDifficulty, song: Song) -> bool:
    if chart.difficulty == DifficultyClass.ERR:
        return False
    if is_delisted(song):
        return False
    # A pool names charts in a thread other people read, so a spoilered chart in
    # one is an ACTIVE spoil, not an answer to a question a player asked.
    if chart_spoilered(song, chart):
        return False
    return True


def _collapse(
    charts: list[tuple[SongDifficulty, Song]], spec: PoolSpec
) -> list[PoolCandidate]:
    if not spec.song_mode:
        return [
            PoolCandidate(
                chart.song_id, chart.id, effective(song, chart, "name_en"))
            for chart, song in charts
        ]
    # A song survives if any one of its difficulties passed the filters.
    by_song: dict[str, str] = {}
    for chart, song in charts:
        by_song.setdefault(chart.song_id, song.name_en)
    return [PoolCandidate(song_id, None, title) for song_id, title in by_song.items()]
