"""Keep the auto-derived alias rows in sync on every admin write.

Mirrors the schema doc's "write triggers": when an entity is saved, its
automatic aliases (ids/names) must exist as rows. Renames additionally **drop**
the stale auto term (user's choice) — but only terms that were auto-derived
before and aren't anymore, so manually-added aliases are never disturbed.

The pure term sets come from :mod:`coda.catalog.aliases`; this module just
applies the (prev_auto − new_auto) delete + new_auto upsert against the session.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from coda.catalog.aliases import (
    difficulty_alias_terms,
    entity_alias_terms,
    song_alias_terms,
)
from coda.catalog.search import refresh_search_index
from coda.db.models import (
    ArtistAlias,
    CharterAlias,
    DifficultyAlias,
    SongAlias,
)


async def _apply(
    session: AsyncSession,
    model: type,
    fk_col: str,
    fk_val,
    prev_auto: set[str],
    new_auto: set[str],
) -> None:
    """Delete now-stale auto terms, then upsert the current ones (manual rows,
    never in ``prev_auto``, are untouched)."""
    stale = prev_auto - new_auto
    if not stale and not new_auto:
        return
    if stale:
        await session.execute(
            delete(model).where(
                getattr(model, fk_col) == fk_val, model.alias.in_(stale)
            )
        )
    if new_auto:
        stmt = pg_insert(model).values(
            [{fk_col: fk_val, "alias": term} for term in new_auto]
        )
        await session.execute(
            stmt.on_conflict_do_nothing(index_elements=[fk_col, "alias"])
        )
    await refresh_search_index(session)


async def sync_song(
    session: AsyncSession,
    song_id: str,
    *,
    old_name_en: str = "",
    old_name_jp: str | None = None,
    new_name_en: str,
    new_name_jp: str | None,
) -> None:
    await _apply(
        session, SongAlias, "song_id", song_id,
        prev_auto=song_alias_terms(song_id, old_name_en, old_name_jp),
        new_auto=song_alias_terms(song_id, new_name_en, new_name_jp),
    )


async def sync_difficulty(
    session: AsyncSession,
    difficulty_id: int,
    *,
    old_name_en: str | None = None,
    old_game_song_id: str | None = None,
    new_name_en: str | None,
    new_game_song_id: str | None,
) -> None:
    await _apply(
        session, DifficultyAlias, "difficulty_id", difficulty_id,
        prev_auto=difficulty_alias_terms(old_name_en, old_game_song_id),
        new_auto=difficulty_alias_terms(new_name_en, new_game_song_id),
    )


async def sync_artist(
    session: AsyncSession, artist_id: str, *, old_name: str = "", new_name: str
) -> None:
    await _apply(
        session, ArtistAlias, "artist_id", artist_id,
        prev_auto=entity_alias_terms(artist_id, old_name),
        new_auto=entity_alias_terms(artist_id, new_name),
    )


async def sync_charter(
    session: AsyncSession, charter_id: str, *, old_name: str = "", new_name: str
) -> None:
    await _apply(
        session, CharterAlias, "charter_id", charter_id,
        prev_auto=entity_alias_terms(charter_id, old_name),
        new_auto=entity_alias_terms(charter_id, new_name),
    )


async def add_manual(
    session: AsyncSession, model: type, fk_col: str, fk_val, alias: str
) -> None:
    """Insert a hand-typed alias (idempotent)."""
    alias = alias.strip()
    if not alias:
        return
    stmt = pg_insert(model).values([{fk_col: fk_val, "alias": alias}])
    await session.execute(
        stmt.on_conflict_do_nothing(index_elements=[fk_col, "alias"])
    )
    await refresh_search_index(session)


async def remove(
    session: AsyncSession, model: type, fk_col: str, fk_val, alias: str
) -> None:
    """Delete a specific alias row (manual or auto)."""
    await session.execute(
        delete(model).where(getattr(model, fk_col) == fk_val, model.alias == alias)
    )
    await refresh_search_index(session)


__all__ = [
    "sync_song",
    "sync_difficulty",
    "sync_artist",
    "sync_charter",
    "add_manual",
    "remove",
]
