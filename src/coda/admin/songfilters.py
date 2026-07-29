"""Chart-level filter state for the song list, parsed from the query string.

Every filter lives in the URL so it survives a sort click, a page step and an
htmx re-request identically. :class:`ChartFilters` carries the parsed values,
the SQL predicates they imply, and the ``extra`` mapping
:class:`~coda.admin.listing.Page` round-trips back into every generated link.

Two catalog rules are applied here rather than at each call site:

* **Sentinels** -- ``level``/``rating`` hold ``0`` (TBA) and ``-1`` (unknown),
  and ``rating < -1`` is a delisted chart's negated historical CC. A range
  comparison therefore requires a *positive* value, or ``cc <= 9.0`` would match
  every unknown chart in the catalog.
* **Inheritance** -- ``jacket`` is NULL on a chart that inherits the song's, so
  the gap filter reads it through ``COALESCE``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlencode

from sqlalchemy import ColumnElement, and_, exists, func, or_, select
from sqlalchemy.orm import aliased

from coda.admin.presenters import parse_level, parse_rating
from coda.db.enums import DifficultyClass
from coda.db.models import (
    DifficultyArtist,
    DifficultyCharter,
    Song,
    SongArtist,
    SongCharter,
    SongDifficulty,
)

# Gap toggles, in render order: (param value, button label).
GAP_CHOICES: tuple[tuple[str, str], ...] = (
    ("no_cc", "no CC"),
    ("no_level", "no level"),
    ("no_notes", "no notes"),
    ("no_jacket", "no jacket"),
    ("no_charter", "no charter link"),
    ("no_artist", "no artist link"),
    ("dup_date", "duplicate date"),
)

_GAP_LABELS = dict(GAP_CHOICES)

# A range bound only makes sense against a real value, never a sentinel.
_POSITIVE_LEVEL = SongDifficulty.level > 0
_POSITIVE_RATING = SongDifficulty.rating > 0


def _int_or_none(raw: str) -> int | None:
    try:
        return int(raw.strip())
    except ValueError:
        return None


def _encoded_or_none(raw: str, encode) -> int | None:
    """Parse a bound through a display encoder, ignoring anything unparseable.

    A half-typed bound must not blank the list, so a bad value is dropped rather
    than raised -- the chip for it simply does not appear.
    """
    raw = raw.strip()
    if not raw:
        return None
    try:
        value = encode(raw)
    except (ValueError, KeyError):
        return None
    return value if value > 0 else None


def _no_links(link_model, song_link_model, override_col) -> ColumnElement[bool]:
    """Charts resolving to an empty artist/charter set.

    Mirrors the override model: a chart with its flag set is authoritative (so
    its own link table decides, and empty means "explicitly unknown"); otherwise
    the song's links are what it inherits.
    """
    own = exists().where(link_model.difficulty_id == SongDifficulty.id)
    inherited = exists().where(song_link_model.song_id == Song.song_id)
    return or_(
        and_(override_col.is_(True), ~own),
        and_(override_col.is_(False), ~inherited),
    )


def _duplicate_date() -> ColumnElement[bool]:
    """Songs sharing a release second with another song.

    The catalog holds collisions predating the uniqueness rule, so this surfaces
    them rather than rewriting them.
    """
    twin = aliased(Song)
    return exists(
        select(1).where(twin.date == Song.date, twin.song_id != Song.song_id)
    )


@dataclass(frozen=True)
class ChartFilters:
    """Parsed chart-level filter state."""

    difficulties: tuple[DifficultyClass, ...] = ()
    level_min: int | None = None
    level_max: int | None = None
    cc_min: int | None = None
    cc_max: int | None = None
    note_min: int | None = None
    note_max: int | None = None
    gaps: tuple[str, ...] = ()
    raw: dict[str, str] = field(default_factory=dict)

    @property
    def active(self) -> bool:
        """Whether any chart-level filter is set (this is what forces charts mode)."""
        return bool(
            self.difficulties
            or self.gaps
            or any(
                v is not None
                for v in (
                    self.level_min, self.level_max, self.cc_min,
                    self.cc_max, self.note_min, self.note_max,
                )
            )
        )

    def extra(self, mode: str) -> dict[str, str | list[str]]:
        """Query params to round-trip through every sort/pager link."""
        out: dict[str, str | list[str]] = {"mode": mode, **self.raw}
        if self.difficulties:
            out["diff"] = [d.value for d in self.difficulties]
        if self.gaps:
            out["gap"] = list(self.gaps)
        return out

    def query(self, mode: str, q: str) -> str:
        """Full query string for a mode-toggle link, keeping the active filters."""
        params: dict[str, str | list[str]] = dict(self.extra(mode))
        if q:
            params["q"] = q
        return urlencode(params, doseq=True)

    def chips(self) -> list[dict[str, str]]:
        """Active filters as removable chips: label plus the param to drop."""
        out: list[dict[str, str]] = []
        for diff in self.difficulties:
            out.append({"label": diff.value.upper(), "param": "diff", "value": diff.value})
        for key, label in (
            ("lvl_min", "level ≥"), ("lvl_max", "level ≤"),
            ("cc_min", "CC ≥"), ("cc_max", "CC ≤"),
            ("note_min", "notes ≥"), ("note_max", "notes ≤"),
        ):
            if self.raw.get(key):
                out.append({"label": f"{label} {self.raw[key]}", "param": key, "value": ""})
        for gap in self.gaps:
            out.append({"label": _GAP_LABELS[gap], "param": "gap", "value": gap})
        return out

    def predicates(self) -> list[ColumnElement[bool]]:
        """SQL conditions for the ``Song ⋈ SongDifficulty`` join."""
        where: list[ColumnElement[bool]] = []
        if self.difficulties:
            where.append(SongDifficulty.difficulty.in_(self.difficulties))
        if self.level_min is not None:
            where.append(and_(_POSITIVE_LEVEL, SongDifficulty.level >= self.level_min))
        if self.level_max is not None:
            where.append(and_(_POSITIVE_LEVEL, SongDifficulty.level <= self.level_max))
        if self.cc_min is not None:
            where.append(and_(_POSITIVE_RATING, SongDifficulty.rating >= self.cc_min))
        if self.cc_max is not None:
            where.append(and_(_POSITIVE_RATING, SongDifficulty.rating <= self.cc_max))
        if self.note_min is not None:
            where.append(SongDifficulty.note >= self.note_min)
        if self.note_max is not None:
            where.append(SongDifficulty.note <= self.note_max)
        where.extend(_gap_predicate(gap) for gap in self.gaps)
        return where


def _gap_predicate(gap: str) -> ColumnElement[bool]:
    if gap == "no_cc":
        # Only the two unknown sentinels. A delisted chart stores a negated real
        # CC, so `rating <= 0` would sweep it in as missing data.
        return SongDifficulty.rating.in_((0, -1))
    if gap == "no_level":
        return SongDifficulty.level.in_((0, -1))
    if gap == "no_notes":
        return SongDifficulty.note == 0
    if gap == "no_jacket":
        return func.coalesce(SongDifficulty.jacket, Song.jacket, "") == ""
    if gap == "no_charter":
        return _no_links(
            DifficultyCharter, SongCharter, SongDifficulty.charters_overridden
        )
    if gap == "no_artist":
        return _no_links(
            DifficultyArtist, SongArtist, SongDifficulty.artists_overridden
        )
    if gap == "dup_date":
        return _duplicate_date()
    raise ValueError(f"unknown gap filter: {gap}")


def parse(params) -> ChartFilters:
    """Read filter state off a request's query params."""
    valid_gaps = {g for g, _ in GAP_CHOICES}
    gaps = tuple(g for g in params.getlist("gap") if g in valid_gaps)

    difficulties: list[DifficultyClass] = []
    for value in params.getlist("diff"):
        try:
            difficulties.append(DifficultyClass(value))
        except ValueError:
            continue

    raw = {}
    for key in ("lvl_min", "lvl_max", "cc_min", "cc_max", "note_min", "note_max"):
        value = (params.get(key) or "").strip()
        if value:
            raw[key] = value
    return ChartFilters(
        difficulties=tuple(difficulties),
        level_min=_encoded_or_none(raw.get("lvl_min", ""), parse_level),
        level_max=_encoded_or_none(raw.get("lvl_max", ""), parse_level),
        cc_min=_encoded_or_none(raw.get("cc_min", ""), parse_rating),
        cc_max=_encoded_or_none(raw.get("cc_max", ""), parse_rating),
        note_min=_int_or_none(raw.get("note_min", "")),
        note_max=_int_or_none(raw.get("note_max", "")),
        gaps=gaps,
        raw=raw,
    )
