"""Conversion between stored unix-second dates and ``YYYY-MM-DD``.

``songs.date`` and ``packs.release_date`` are unix timestamps in **seconds**. A
day-precision date is snapped to that day's midnight UTC.
"""

from __future__ import annotations

from datetime import date, datetime, timezone


# Largest unix second `datetime` can represent (23:59:59 on 9999-12-31 UTC). A
# value stored in milliseconds by mistake lands far past this, and formatting it
# raises -- which would take out a whole list page for one bad row.
_MAX_SECONDS = 253402300799


def in_range(seconds: int | None) -> bool:
    """Whether ``seconds`` is a formattable unix second."""
    return seconds is not None and 0 <= seconds <= _MAX_SECONDS


def display_date(seconds: int | None) -> str:
    """Unix-seconds -> ``YYYY-MM-DD`` (empty for None or an unformattable value)."""
    if not in_range(seconds):
        return ""
    return datetime.fromtimestamp(seconds, tz=timezone.utc).date().isoformat()


def split_date(seconds: int | None) -> tuple[str, int]:
    """Unix-seconds -> (``YYYY-MM-DD``, offset seconds within that day).

    The game offsets songs by whole seconds inside a release day purely to fix
    their sort order -- the headline song of a pack is typically last, a few
    seconds in. Players never see it, so the stored value diverges from the
    displayed day by design; splitting it is what makes that legible in the
    editor instead of a raw epoch integer.
    """
    if not in_range(seconds):
        return "", 0
    day = display_date(seconds)
    return day, seconds - (parse_date(day) or 0)


def combine_date(day: str, offset: int) -> int | None:
    """(``YYYY-MM-DD``, offset seconds) -> unix-seconds (None for a blank day)."""
    midnight = parse_date(day)
    return None if midnight is None else midnight + offset


def parse_date(text: str) -> int | None:
    """Unix-seconds or ``YYYY-MM-DD`` -> unix-seconds (None for blank).

    The song forms post a raw seconds value directly; a bare ISO date is still
    accepted (pasted, or from the pack date picker) and snapped to midnight UTC."""
    text = text.strip()
    if not text:
        return None
    if text.lstrip("-").isdigit():
        return int(text)
    d = date.fromisoformat(text[:10])
    dt = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    return int(dt.timestamp())
