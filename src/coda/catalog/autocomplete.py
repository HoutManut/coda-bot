"""Song autocomplete rows, used by the commands that take a song query.

Every row's VALUE is the song id, so picking one resolves by exact id and never
re-enters the fuzzy path.
"""

from __future__ import annotations

import re
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from coda.catalog.search import SearchService
from coda.catalog.spoilers import flagged
from coda.db.models import Song
from coda.utils.encoding import decode_level, encode_level


async def song_choices(
    db: AsyncSession, typed: str, *, numeric_echo: bool = True
) -> list[tuple[str, str]]:
    """Discriminated song rows, a level/CC echo row, or the newest songs.

    ``numeric_echo`` is False for a caller that acts on one chart and so has
    nothing to offer for a level/CC browse.
    """
    if not typed:
        return await _newest_songs(db)
    if numeric_echo:
        echo = _numeric_echo(typed)
        if echo is not None:
            return echo
    return await _song_rows(db, typed)


def _numeric_echo(typed: str) -> list[tuple[str, str]] | None:
    """One selectable echo row confirming a level/CC interpretation, or None."""
    norm = typed.lower()
    if re.fullmatch(r"\d{1,2}\+?", norm):
        if decode_level(encode_level(norm)) == "?":
            return None
        return [(f"Level {norm} — list all charts", norm)]
    if re.fullmatch(r"\d{1,2}\.\d+", norm):
        whole, frac = norm.split(".")
        return [(f"CC {whole}.{frac[0]} — list all charts", norm)]
    return None


async def _newest_songs(db: AsyncSession) -> list[tuple[str, str]]:
    """The empty-query suggestion: the newest songs, minus the hidden ones.

    This list is ordered by ``idx`` descending, so it *is* the newest content by
    construction -- which makes it the one autocomplete path that hands out
    spoilered names to someone who typed nothing at all. Flagged versions are
    excluded in SQL rather than after the limit, so the row count survives.
    """
    query = select(Song.song_id, Song.name_en, Song.artist, Song.pack_name)
    spoilered = flagged()
    if spoilered:
        query = query.where(Song.version.notin_(spoilered))
    rows = (await db.execute(query.order_by(Song.idx.desc()).limit(25))).all()
    candidates = [
        (sid, name, artist, pack)
        for sid, name, artist, pack in rows
        if not _is_delisted_name(name)
    ]
    return _labeled_rows(candidates)


async def _song_rows(db: AsyncSession, typed: str) -> list[tuple[str, str]]:
    candidates = await SearchService().candidate_songs(db, typed, limit=25)
    return _labeled_rows(candidates)


def _labeled_rows(
    candidates: list[tuple[str, str, str, str]],
) -> list[tuple[str, str]]:
    """Row is the song name alone; only a shared name gets the discriminating
    ``— artist (pack)`` suffix (dropping the pack if it overflows 100 chars)."""
    counts = Counter(name for _sid, name, _artist, _pack in candidates)
    rows: list[tuple[str, str]] = []
    for song_id, name, artist, pack in candidates:
        if counts[name] > 1:
            label = f"{name} — {artist} ({pack})"
            if len(label) > 100:
                label = f"{name} — {artist}"
        else:
            label = name
        rows.append((label[:100], song_id))
    return rows


def _is_delisted_name(name: str) -> bool:
    return len(name) >= 2 and name.startswith("_") and name.endswith("_")
