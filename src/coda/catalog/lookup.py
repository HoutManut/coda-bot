"""Catalog row loaders shared by the commands that render songs and charts.

Ids passed in come from the resolver or a bot-minted component, never from user
text -- so a miss is a bug, not a user error, and asserts rather than branches.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from coda.db.models import Song, SongDifficulty


async def load_song(
    db: AsyncSession, song_id: str
) -> tuple[Song, list[SongDifficulty]]:
    """A song and all of its charts."""
    song = await db.get(Song, song_id)
    assert song is not None
    charts = (
        await db.execute(
            select(SongDifficulty).where(SongDifficulty.song_id == song_id)
        )
    ).scalars().all()
    return song, list(charts)


async def load_chart(
    db: AsyncSession, difficulty_id: int
) -> tuple[Song, SongDifficulty]:
    """One chart and the song it belongs to."""
    chart = await db.get(SongDifficulty, difficulty_id)
    assert chart is not None
    song = await db.get(Song, chart.song_id)
    assert song is not None
    return song, chart


async def load_charts_ordered(
    db: AsyncSession, ids: list[int]
) -> list[tuple[SongDifficulty, Song]]:
    """Charts with their songs, in the order the ids were given."""
    rows = (
        await db.execute(
            select(SongDifficulty, Song)
            .join(Song, Song.song_id == SongDifficulty.song_id)
            .where(SongDifficulty.id.in_(ids))
        )
    ).all()
    by_id = {chart.id: (chart, song) for chart, song in rows}
    return [by_id[i] for i in ids if i in by_id]
