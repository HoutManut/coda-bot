"""The ``key:value`` / ``key>value`` filter grammar, parsed to typed filters.

Pure: no I/O, no ORM. :func:`parse` splits a raw query into the leftover song-name
text and a tuple of :class:`FieldFilter`, coercing every value to the form the
column actually stores (level ``×2``, CC ``×10``, side id, epoch seconds).
Repeating a key ANDs it, so ``bpm>180 bpm<220`` needs no range operator.

Equality is spelled ``:`` or ``=``; ``>``/``>=``/``<``/``<=`` compare.

A token whose key is not a known field falls through to the song-name text rather
than erroring, but only when written with ``:``: real song titles contain colons
(``carmine:scythe``, ``Valhalla:0``). No title contains ``=``, ``>`` or ``<``, so
an unknown key with those is a genuine typo and does error.
"""

from __future__ import annotations

import enum
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from coda.db.enums import Side
from coda.utils.dates import parse_date
from coda.utils.encoding import encode_level, encode_rating


class Op(enum.StrEnum):
    EQ = ":"
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="


class Kind(enum.StrEnum):
    """What a field filters on — picks the predicate builder in ``filters.py``."""

    NUMERIC = "numeric"
    ENTITY = "entity"
    ENUM = "enum"
    TEXT = "text"
    VERSION = "version"


@dataclass(frozen=True)
class FieldFilter:
    """One constraint, its value already coerced to the column's storage form."""

    field: str
    kind: Kind
    op: Op
    value: Any


@dataclass(frozen=True)
class ParsedQuery:
    """Leftover song-name text plus the filters. ``error`` set → reject the query."""

    text: str
    filters: tuple[FieldFilter, ...] = ()
    error: str | None = None


# A token is a run of non-space characters, with double-quoted spans held together
# so ``pack:"eternal core"`` survives as one token. The closing quote is optional
# so an unbalanced one degrades instead of swallowing the rest of the query.
_TOKEN_RE = re.compile(r'(?:[^\s"]+|"[^"]*"?)+')
_FIELD_RE = re.compile(r'^([a-z]+)(>=|<=|:|=|>|<)(.+)$')

# Two spellings of equality; the symbol (not the Op) decides the unknown-key
# fallthrough above, so they are not interchangeable there.
_SYMBOL_OPS: dict[str, Op] = {
    ":": Op.EQ,
    "=": Op.EQ,
    ">": Op.GT,
    ">=": Op.GTE,
    "<": Op.LT,
    "<=": Op.LTE,
}

_LEVEL_VALUE_RE = re.compile(r"^\d{1,2}\+?$")
_CC_VALUE_RE = re.compile(r"^\d{1,2}(\.\d+)?$")

_ALL_OPS = frozenset(Op)
_EQ_ONLY = frozenset({Op.EQ})


def _level_value(raw: str) -> int:
    if not _LEVEL_VALUE_RE.match(raw):
        raise ValueError("expected a level like 10 or 10+")
    return encode_level(raw)


def _cc_value(raw: str) -> int:
    if not _CC_VALUE_RE.match(raw):
        raise ValueError("expected a chart constant like 9.7")
    return encode_rating(float(raw))


def _bpm_value(raw: str) -> float:
    try:
        return float(raw)
    except ValueError:
        raise ValueError("expected a number") from None


def _note_value(raw: str) -> int:
    if not raw.isdigit():
        raise ValueError("expected a whole number")
    return int(raw)


def _date_value(raw: str) -> int:
    try:
        seconds = parse_date(raw)
    except ValueError:
        raise ValueError("expected a date like 2023-06-01") from None
    if seconds is None:
        raise ValueError("expected a date like 2023-06-01")
    return seconds


def _side_value(raw: str) -> int:
    try:
        return Side(raw).to_id()
    except ValueError:
        names = ", ".join(side.value for side in Side)
        raise ValueError(f"expected one of {names}") from None


def _text_value(raw: str) -> str:
    return raw


_VERSION_VALUE_RE = re.compile(r"^\d{1,3}(\.\d{1,3})?$")


def _version_value(raw: str) -> str:
    """Validated, not parsed here -- ``:`` still prefix-matches on the raw string,
    while ``filters.py`` splits it part-wise for ``>``/``<`` comparisons (a plain
    float would rank ``5.10`` below ``5.9``)."""
    if not _VERSION_VALUE_RE.match(raw):
        raise ValueError("expected a version like 6.8")
    return raw


@dataclass(frozen=True)
class FieldSpec:
    kind: Kind
    coerce: Callable[[str], Any]
    ops: frozenset[Op]


FIELDS: dict[str, FieldSpec] = {
    "artist": FieldSpec(Kind.ENTITY, _text_value, _EQ_ONLY),
    "charter": FieldSpec(Kind.ENTITY, _text_value, _EQ_ONLY),
    "pack": FieldSpec(Kind.TEXT, _text_value, _EQ_ONLY),
    "version": FieldSpec(Kind.VERSION, _version_value, _ALL_OPS),
    "side": FieldSpec(Kind.ENUM, _side_value, _EQ_ONLY),
    "level": FieldSpec(Kind.NUMERIC, _level_value, _ALL_OPS),
    "cc": FieldSpec(Kind.NUMERIC, _cc_value, _ALL_OPS),
    "bpm": FieldSpec(Kind.NUMERIC, _bpm_value, _ALL_OPS),
    "note": FieldSpec(Kind.NUMERIC, _note_value, _ALL_OPS),
    "date": FieldSpec(Kind.NUMERIC, _date_value, _ALL_OPS),
}

ALIASES: dict[str, str] = {
    "rating": "cc",
    "const": "cc",
    "notes": "note",
    "lv": "level",
    "lvl": "level",
    "released": "date",
    "ver": "version",
}


def parse(query: str) -> ParsedQuery:
    """Split a raw query into song-name text and coerced field filters."""
    words: list[str] = []
    filters: list[FieldFilter] = []
    for token in _TOKEN_RE.findall(query.lower()):
        parsed = _parse_token(token)
        if isinstance(parsed, ParsedQuery):
            return parsed
        if parsed is None:
            words.append(_unquote(token))
        else:
            filters.append(parsed)
    return ParsedQuery(text=" ".join(words).strip(), filters=tuple(filters))


def _parse_token(token: str) -> FieldFilter | ParsedQuery | None:
    """A filter, ``None`` for a bare word, or a :class:`ParsedQuery` holding the
    error that rejects the whole query."""
    match = _FIELD_RE.match(token)
    if match is None:
        return None
    key, symbol, raw = match.groups()
    op = _SYMBOL_OPS[symbol]
    field = ALIASES.get(key, key)
    spec = FIELDS.get(field)
    if spec is None:
        if symbol == ":":
            return None
        return _reject(f"Unknown filter `{key}`.")
    if op not in spec.ops:
        return _reject(f"`{field}` cannot be compared — use `{field}:value`.")
    try:
        value = spec.coerce(_unquote(raw))
    except ValueError as exc:
        return _reject(f"Bad `{field}` value `{_unquote(raw)}` — {exc}.")
    return FieldFilter(field=field, kind=spec.kind, op=op, value=value)


def _reject(message: str) -> ParsedQuery:
    return ParsedQuery(text="", error=message)


def _unquote(value: str) -> str:
    return value.replace('"', "")
