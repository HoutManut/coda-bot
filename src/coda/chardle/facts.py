"""The catalog facts one chart contributes to a board, resolved and flattened.

Every clue column reads off a :class:`ChartFacts`, so inheritance
(``COALESCE(difficulty.field, song.field)``) and the artist/charter link
override rules are applied once here rather than in each comparison.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from coda.catalog.resolution import effective
from coda.catalog.search import is_delisted
from coda.db.enums import DifficultyClass
from coda.db.models import (
    DifficultyArtist,
    DifficultyCharter,
    Song,
    SongArtist,
    SongCharter,
    SongDifficulty,
)


@dataclass(frozen=True)
class ChartFacts:
    """One chart's comparable values. ``level``/``rating`` stay stored-encoded."""

    difficulty_id: int
    song_id: str
    name: str
    difficulty_class: DifficultyClass
    alt: bool
    level: int
    rating: int
    note: int
    bpm: float
    bpm_display: str
    side: int
    version: str
    pack_id: str | None
    pack_name: str
    artists: frozenset[str]
    charters: frozenset[str]
    artist_text: str
    charter_text: str
    jacket_stem: str

    @property
    def visible_class(self) -> DifficultyClass:
        """The class the board prints: ``byd_2`` is a storage slot, not a class."""
        # Both of Last's charts read as Beyond.
        if self.difficulty_class is DifficultyClass.BYD_2:
            return DifficultyClass.BYD
        return self.difficulty_class


async def load_facts(
    db: AsyncSession, difficulty_ids: Iterable[int]
) -> dict[int, ChartFacts]:
    """Facts for specific charts, keyed by ``song_difficulties.id``."""
    ids = list(difficulty_ids)
    if not ids:
        return {}
    stmt = (
        select(SongDifficulty, Song)
        .join(Song, Song.song_id == SongDifficulty.song_id)
        .where(SongDifficulty.id.in_(ids))
    )
    rows = (await db.execute(stmt)).all()
    facts = await _build(db, [(chart, song) for chart, song in rows])
    return {fact.difficulty_id: fact for fact in facts}


async def load_pool(
    db: AsyncSession,
    classes: frozenset[DifficultyClass],
    *,
    allow_sentinels: bool,
    level: int | None = None,
    side: int | None = None,
) -> list[ChartFacts]:
    """Every chart eligible to be an answer under these constraints.

    Delisted songs and sentinel level/CC charts are excluded here, at draw time.
    A puzzle outlives that: an answer delisted afterwards stays winnable through
    ``GuessService``'s answer check.
    """
    stmt = (
        select(SongDifficulty, Song)
        .join(Song, Song.song_id == SongDifficulty.song_id)
        .where(SongDifficulty.difficulty.in_(classes))
    )
    if level is not None:
        stmt = stmt.where(SongDifficulty.level == level)
    rows = (await db.execute(stmt)).all()
    kept = [
        (chart, song)
        for chart, song in rows
        if not is_delisted(song)
        and (allow_sentinels or (chart.level > 0 and chart.rating > 0))
    ]
    facts = await _build(db, kept)
    if side is not None:
        facts = [fact for fact in facts if fact.side == side]
    return facts


async def _build(
    db: AsyncSession, rows: Sequence[tuple[SongDifficulty, Song]]
) -> list[ChartFacts]:
    if not rows:
        return []
    song_ids = {song.song_id for _, song in rows}
    chart_ids = {chart.id for chart, _ in rows}

    song_artists = await _links(db, SongArtist.song_id, SongArtist.artist_id, song_ids)
    chart_artists = await _links(
        db, DifficultyArtist.difficulty_id, DifficultyArtist.artist_id, chart_ids
    )
    song_charters = await _links(
        db, SongCharter.song_id, SongCharter.charter_id, song_ids
    )
    chart_charters = await _links(
        db, DifficultyCharter.difficulty_id, DifficultyCharter.charter_id, chart_ids
    )

    return [
        _fact(chart, song, song_artists, chart_artists, song_charters, chart_charters)
        for chart, song in rows
    ]


def _fact(
    chart: SongDifficulty,
    song: Song,
    song_artists: dict,
    chart_artists: dict,
    song_charters: dict,
    chart_charters: dict,
) -> ChartFacts:
    bpm_base = effective(song, chart, "bpm_base")
    return ChartFacts(
        difficulty_id=chart.id,
        song_id=song.song_id,
        name=effective(song, chart, "name_en"),
        difficulty_class=chart.difficulty,
        alt=chart.alt,
        level=chart.level,
        rating=chart.rating,
        note=chart.note,
        bpm=bpm_base,
        bpm_display=effective(song, chart, "bpm") or f"{bpm_base:g}",
        side=effective(song, chart, "side"),
        version=effective(song, chart, "version"),
        pack_id=song.pack_id,
        pack_name=song.pack_name,
        artists=_resolve_links(
            chart.artists_overridden,
            chart_artists.get(chart.id),
            song_artists.get(song.song_id),
        ),
        charters=_resolve_links(
            chart.charters_overridden,
            chart_charters.get(chart.id),
            song_charters.get(song.song_id),
        ),
        artist_text=effective(song, chart, "artist"),
        charter_text=chart.chart_designer or "",
        jacket_stem=effective(song, chart, "jacket"),
    )


async def _links(db: AsyncSession, owner_col, value_col, owners) -> dict:
    if not owners:
        return {}
    rows = (
        await db.execute(select(owner_col, value_col).where(owner_col.in_(owners)))
    ).all()
    grouped: dict = {}
    for owner, value in rows:
        grouped.setdefault(owner, set()).add(value)
    return grouped


def _resolve_links(
    overridden: bool, own: set[str] | None, inherited: set[str] | None
) -> frozenset[str]:
    """Per-chart links replace the song's set when the override flag is set —
    including when the chart's own set is empty (explicitly unknown)."""
    if overridden:
        return frozenset(own or ())
    return frozenset(inherited or ())
