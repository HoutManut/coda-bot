"""IANA zone names, and what to do with a bad one.

Pure: no config read, no database. The configured zone is resolved by
``coda.settings.zone``; this is only the parsing half, so modules that must not
import the settings layer (``chardle.schedule``) can still share one default.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_ZONE = "Asia/Bangkok"


def parse_zone(name: str) -> ZoneInfo:
    """An IANA zone, falling back to the default rather than failing a render.

    Writes are validated at the boundary (``coda.settings.parse``), so a name
    that reaches here and is unknown means the row predates that check.
    """
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_ZONE)
