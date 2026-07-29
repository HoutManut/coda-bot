"""Turning parsed :class:`FieldFilter` values into a chart-level SQL predicate.

Every predicate here is written against the ``SongDifficulty ⋈ Song`` join, and
three catalog rules are applied in this one place rather than at each call site:

* **Inheritance** — ``bpm_base``, ``side``, ``date`` and ``version`` are NULL on a
  chart that inherits the song's value (``resolution.OVERRIDABLE_FIELDS``), so
  they are always read through ``COALESCE``. Filtering the chart column alone
  silently drops every inheriting chart.
* **Sentinels** — ``level``/``rating``/``note`` use non-positive values for
  unknown, and ``rating < -1`` for a delisted chart's historical CC. Comparisons
  therefore require a positive value, or ``cc<9.0`` would match every unknown.
* **Link overrides** — a chart's artist/charter links replace the song's set only
  when its override flag is set, matching ``chardle.facts._resolve_links``.
"""

from __future__ import annotations

import operator
from collections.abc import Callable, Sequence
from typing import Any

from sqlalchemy import (
    ColumnElement,
    Integer,
    and_,
    false,
    func,
    or_,
    select,
    text,
    true,
)
from sqlalchemy.ext.asyncio import AsyncSession

from coda.catalog.query import FieldFilter, Kind, Op
from coda.db.models import (
    DifficultyArtist,
    DifficultyCharter,
    Song,
    SongArtist,
    SongCharter,
    SongDifficulty,
)

_COMPARATORS: dict[Op, Callable[[Any, Any], ColumnElement[bool]]] = {
    Op.EQ: operator.eq,
    Op.GT: operator.gt,
    Op.GTE: operator.ge,
    Op.LT: operator.lt,
    Op.LTE: operator.le,
}

# Unknown and delisted charts store non-positive values here, so they must not
# fall into a comparison window.
_SENTINEL_GUARDED = frozenset({"level", "cc", "note"})

_ENTITY_TERM_SQL = text(
    """
    SELECT DISTINCT entity_ref_id
    FROM search_index
    WHERE entity_type = :kind
      AND (lower(term) = :q OR lower(term) LIKE :like)
    """
)


def escape_like(term: str) -> str:
    """Escape LIKE wildcards so a typed ``%`` or ``_`` is matched literally."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _numeric_column(field: str) -> ColumnElement[Any]:
    match field:
        case "level":
            return SongDifficulty.level
        case "cc":
            return SongDifficulty.rating
        case "note":
            return SongDifficulty.note
        case "bpm":
            return func.coalesce(SongDifficulty.bpm_base, Song.bpm_base)
        case "date":
            return func.coalesce(SongDifficulty.date, Song.date)
    raise KeyError(field)


def _numeric_predicate(field: str, op: Op, value: Any) -> ColumnElement[bool]:
    column = _numeric_column(field)
    compared = _COMPARATORS[op](column, value)
    if field in _SENTINEL_GUARDED:
        return and_(column > 0, compared)
    return compared


def _text_predicate(value: str) -> ColumnElement[bool]:
    return Song.pack_name.ilike(f"%{escape_like(value)}%")


def _parse_version(value: str) -> tuple[int, int]:
    parts = value.split(".")
    return int(parts[0]), int(parts[1]) if len(parts) > 1 else 0


def _version_predicate(op: Op, value: str) -> ColumnElement[bool]:
    """``5.10`` is newer than ``5.9`` -- compare major/minor as ints, not the
    string or a float, matching ``chardle.feedback._version_parts``."""
    column = func.coalesce(SongDifficulty.version, Song.version)
    if op == Op.EQ:
        return column.ilike(f"{escape_like(value)}%")
    major, minor = _parse_version(value)
    col_major = func.split_part(column, ".", 1).cast(Integer)
    col_minor = func.nullif(func.split_part(column, ".", 2), "").cast(Integer)
    col_minor = func.coalesce(col_minor, 0)
    if op in (Op.GT, Op.GTE):
        same_major = col_minor >= minor if op == Op.GTE else col_minor > minor
        return or_(col_major > major, and_(col_major == major, same_major))
    same_major = col_minor <= minor if op == Op.LTE else col_minor < minor
    return or_(col_major < major, and_(col_major == major, same_major))


def _enum_predicate(value: int) -> ColumnElement[bool]:
    return func.coalesce(SongDifficulty.side, Song.side) == value


def _link_predicate(field: str, entity_ids: Sequence[str]) -> ColumnElement[bool]:
    """A chart matches through its own links when overridden, else the song's."""
    if field == "artist":
        overridden = SongDifficulty.artists_overridden
        own = select(1).where(
            DifficultyArtist.difficulty_id == SongDifficulty.id,
            DifficultyArtist.artist_id.in_(entity_ids),
        )
        inherited = select(1).where(
            SongArtist.song_id == Song.song_id,
            SongArtist.artist_id.in_(entity_ids),
        )
    else:
        overridden = SongDifficulty.charters_overridden
        own = select(1).where(
            DifficultyCharter.difficulty_id == SongDifficulty.id,
            DifficultyCharter.charter_id.in_(entity_ids),
        )
        inherited = select(1).where(
            SongCharter.song_id == Song.song_id,
            SongCharter.charter_id.in_(entity_ids),
        )
    return or_(
        and_(overridden, own.exists()),
        and_(~overridden, inherited.exists()),
    )


async def _entity_ids(db: AsyncSession, kind: str, value: str) -> list[str]:
    rows = await db.execute(
        _ENTITY_TERM_SQL,
        {"kind": kind, "q": value, "like": f"%{escape_like(value)}%"},
    )
    return [row.entity_ref_id for row in rows]


async def chart_predicate(
    db: AsyncSession, filters: Sequence[FieldFilter]
) -> ColumnElement[bool]:
    """AND every filter into one predicate over the ``SongDifficulty ⋈ Song`` join.

    An entity filter naming nothing in the catalog yields ``false()``, so the
    query returns empty rather than silently dropping the constraint.
    """
    predicates: list[ColumnElement[bool]] = []
    for spec in filters:
        match spec.kind:
            case Kind.NUMERIC:
                predicates.append(_numeric_predicate(spec.field, spec.op, spec.value))
            case Kind.TEXT:
                predicates.append(_text_predicate(spec.value))
            case Kind.VERSION:
                predicates.append(_version_predicate(spec.op, spec.value))
            case Kind.ENUM:
                predicates.append(_enum_predicate(spec.value))
            case Kind.ENTITY:
                ids = await _entity_ids(db, spec.field, spec.value)
                if not ids:
                    return false()
                predicates.append(_link_predicate(spec.field, ids))
    return and_(*predicates) if predicates else true()
