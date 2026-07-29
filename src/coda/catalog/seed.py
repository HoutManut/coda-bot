"""Idempotent import of ``arcsongs.json`` into the ORM.

Run as ``uv run python -m coda.catalog.seed [path]`` (defaults to
``assets/arcsongs.json``). Every table is upserted by natural key, so re-running
is safe and converges to the file's contents. Aliases are populated here, in
Python — there are no DB triggers.

Caveat: the old JSON has no separate display names for artists/charters, so their
``name`` is seeded as the id string; real names land when a richer source exists.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from coda.catalog.aliases import (
    difficulty_alias_terms,
    entity_alias_terms,
    song_alias_terms,
)
from coda.catalog.dto import OVERRIDABLE, ParsedSong, parse_catalog
from coda.catalog.search import refresh_search_index
from coda.db.models import (
    Artist,
    ArtistAlias,
    Charter,
    CharterAlias,
    DifficultyAlias,
    Pack,
    Song,
    SongArtist,
    SongCharter,
    SongDifficulty,
)
from coda.db.models.alias import SongAlias
from coda.db.session import async_session

DEFAULT_SOURCE = Path("assets/arcsongs.json")

# asyncpg caps a statement at 32767 bind params; chunk rows so widest table
# (song_difficulties, ~22 cols) stays well under that.
_MAX_ROWS_PER_INSERT = 800


def _chunks(rows: Sequence[dict[str, Any]]) -> Iterable[list[dict[str, Any]]]:
    for start in range(0, len(rows), _MAX_ROWS_PER_INSERT):
        yield list(rows[start : start + _MAX_ROWS_PER_INSERT])


async def _upsert(
    session: AsyncSession,
    model: type,
    rows: Sequence[dict[str, Any]],
    *,
    index_elements: Sequence[str],
    update: Sequence[str] | None = None,
) -> None:
    """Insert ``rows`` for ``model``; on conflict update ``update`` cols (or skip)."""
    for chunk in _chunks(rows):
        stmt = pg_insert(model).values(chunk)
        if update:
            stmt = stmt.on_conflict_do_update(
                index_elements=list(index_elements),
                set_={col: getattr(stmt.excluded, col) for col in update},
            )
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=list(index_elements))
        await session.execute(stmt)


def _distinct_packs(songs: Iterable[ParsedSong]) -> list[dict[str, Any]]:
    packs: dict[str, str] = {}
    for song in songs:
        if song.pack_id and song.pack_id not in packs:
            packs[song.pack_id] = song.fields["pack_name"]
    return [{"pack_id": pid, "name": name} for pid, name in packs.items()]


def _named_rows(ids: Iterable[str], id_col: str) -> list[dict[str, Any]]:
    """Rows for an entity whose display name is, for now, its id."""
    return [{id_col: i, "name": i} for i in dict.fromkeys(ids)]


def _song_row(song: ParsedSong) -> dict[str, Any]:
    return {
        "song_id": song.song_id,
        "idx": song.idx,
        "pack_id": song.pack_id,
        **song.fields,
    }


def _difficulty_row(song: ParsedSong, diff: Any) -> dict[str, Any]:
    # Every overridable column is set explicitly (None = inherit) so all rows share
    # one key set — a bulk insert takes its column list from the first row, and a
    # sparse row would silently drop overrides present only on later rows.
    row: dict[str, Any] = {
        "song_id": song.song_id,
        "difficulty": diff.difficulty,
        "level": diff.level,
        "rating": diff.rating,
        "note": diff.note,
        "chart_designer": diff.chart_designer,
        "game_song_id": diff.game_song_id,
    }
    for name in OVERRIDABLE:
        row[name] = diff.overrides.get(name)
    return row


def _song_alias_terms(song: ParsedSong) -> set[str]:
    return song_alias_terms(
        song.song_id,
        song.fields["name_en"],
        song.fields["name_jp"],
        extra=song.aliases,
    )


async def seed(session: AsyncSession, songs: list[ParsedSong]) -> None:
    artist_ids = {a for s in songs for a in s.artist_ids}
    charter_ids = {c for s in songs for c in s.charter_ids}

    # Parents first (FK targets), entities updatable, links/aliases insert-only.
    await _upsert(
        session, Pack, _distinct_packs(songs),
        index_elements=["pack_id"], update=["name"],
    )
    await _upsert(
        session, Artist, _named_rows(artist_ids, "artist_id"),
        index_elements=["artist_id"], update=["name"],
    )
    await _upsert(
        session, Charter, _named_rows(charter_ids, "charter_id"),
        index_elements=["charter_id"], update=["name"],
    )

    song_cols = list(_song_row(songs[0]).keys()) if songs else []
    await _upsert(
        session, Song, [_song_row(s) for s in songs],
        index_elements=["song_id"],
        update=[c for c in song_cols if c != "song_id"],
    )

    # Difficulties: upsert and capture ids keyed by (song_id, difficulty) so we
    # can attach difficulty aliases without a follow-up query.
    diff_rows = [_difficulty_row(s, d) for s in songs for d in s.difficulties]
    diff_id: dict[tuple[str, Any], int] = {}
    if diff_rows:
        update_cols = [c for c in diff_rows[0] if c not in ("song_id", "difficulty")]
        for chunk in _chunks(diff_rows):
            stmt = pg_insert(SongDifficulty).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=["song_id", "difficulty"],
                set_={col: getattr(stmt.excluded, col) for col in update_cols},
            ).returning(
                SongDifficulty.id, SongDifficulty.song_id, SongDifficulty.difficulty
            )
            for did, sid, dclass in (await session.execute(stmt)).all():
                diff_id[(sid, dclass)] = did

    # Junctions.
    await _upsert(
        session, SongArtist,
        [{"song_id": s.song_id, "artist_id": a} for s in songs for a in s.artist_ids],
        index_elements=["song_id", "artist_id"],
    )
    await _upsert(
        session, SongCharter,
        [{"song_id": s.song_id, "charter_id": c} for s in songs for c in s.charter_ids],
        index_elements=["song_id", "charter_id"],
    )

    # Aliases (search source of truth).
    await _upsert(
        session, SongAlias,
        [{"song_id": s.song_id, "alias": t} for s in songs for t in _song_alias_terms(s)],
        index_elements=["song_id", "alias"],
    )
    await _upsert(
        session, ArtistAlias,
        [
            {"artist_id": a, "alias": t}
            for a in artist_ids
            for t in entity_alias_terms(a)  # name == id at seed time
        ],
        index_elements=["artist_id", "alias"],
    )
    await _upsert(
        session, CharterAlias,
        [
            {"charter_id": c, "alias": t}
            for c in charter_ids
            for t in entity_alias_terms(c)
        ],
        index_elements=["charter_id", "alias"],
    )

    diff_alias_rows: list[dict[str, Any]] = []
    for s in songs:
        for d in s.difficulties:
            did = diff_id[(s.song_id, d.difficulty)]
            for term in difficulty_alias_terms(
                d.overrides.get("name_en"), d.game_song_id
            ):
                diff_alias_rows.append({"difficulty_id": did, "alias": term})
    await _upsert(
        session, DifficultyAlias, diff_alias_rows,
        index_elements=["difficulty_id", "alias"],
    )

    await refresh_search_index(session)


class SeedNotEmptyError(RuntimeError):
    """Seed is bootstrap-only; refuse to run against a populated catalog.

    Once the catalog exists, the admin editor owns it. Re-seeding upserts
    ``name = id`` over curated names and re-inserts JSON-only ids, resurrecting
    entities that were merged or renamed in the editor. ``--force`` overrides.
    """

    def __init__(self, existing: int) -> None:
        super().__init__(
            f"Catalog already has {existing} songs; seed is bootstrap-only. "
            "The admin editor owns the catalog now -- re-seeding overwrites "
            "curated names and resurrects merged/renamed entities. Pass --force "
            "only for an intentional re-bootstrap of an empty-by-intent catalog."
        )


async def run(source: Path = DEFAULT_SOURCE, *, force: bool = False) -> int:
    data = json.loads(source.read_text(encoding="utf-8"))
    songs = parse_catalog(data)
    async with async_session() as session:
        existing = await session.scalar(select(func.count()).select_from(Song))
        if existing and not force:
            raise SeedNotEmptyError(existing)
        await seed(session, songs)
        await session.commit()
    return len(songs)


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--force"]
    force = "--force" in sys.argv[1:]
    source = Path(args[0]) if args else DEFAULT_SOURCE
    try:
        count = asyncio.run(run(source, force=force))
    except SeedNotEmptyError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(2)
    print(f"Seeded {count} songs from {source}")


if __name__ == "__main__":
    main()
