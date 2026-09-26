"""Which game versions are flagged as spoilers, and which charts that covers.

The flagged set is cached in this module rather than read per render: every
``/song``, every ``/score`` and every live post asks the question, and
``Op.complete`` (``ops/types.py``) is synchronous so the ``/run`` completer
cannot query at all. The set holds a handful of strings and only the owner
writes it, so a process-wide cache refreshed on write is the whole mechanism.
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from coda.catalog.resolution import effective
from coda.db.models import Song, SongDifficulty, SpoilerVersion

_flagged: frozenset[str] = frozenset()


async def refresh(db: AsyncSession) -> None:
    """Reload the cached set. Called at startup and after every write."""
    global _flagged
    rows = await db.scalars(select(SpoilerVersion.version))
    _flagged = frozenset(rows)


def flagged() -> frozenset[str]:
    """Every flagged version, from cache."""
    return _flagged


def is_spoilered(version: str | None) -> bool:
    return version is not None and version in _flagged


def chart_spoilered(song: Song, chart: SongDifficulty) -> bool:
    """Whether this chart's effective version is flagged.

    A chart added to an old song in a new version carries its own ``version``,
    so the effective value -- not the song's -- is the one that decides.
    """
    return is_spoilered(effective(song, chart, "version"))


def song_spoilered(song: Song, charts: list[SongDifficulty]) -> bool:
    """Whether any of the song's charts is spoilered."""
    return is_spoilered(song.version) or any(
        chart_spoilered(song, chart) for chart in charts
    )


async def add(db: AsyncSession, version: str, set_by: int) -> bool:
    """Flag a version. False when it was already flagged."""
    if version in _flagged:
        return False
    db.add(SpoilerVersion(version=version, set_by=set_by))
    await db.commit()
    await refresh(db)
    return True


async def remove(db: AsyncSession, version: str) -> bool:
    """Unflag a version. False when it was not flagged."""
    if version not in _flagged:
        return False
    await db.execute(delete(SpoilerVersion).where(SpoilerVersion.version == version))
    await db.commit()
    await refresh(db)
    return True
