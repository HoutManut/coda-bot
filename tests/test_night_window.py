"""Day/night jacket selection follows the configured zone, not a fixed offset."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from coda.catalog.jackets import is_night
from coda.utils.zones import DEFAULT_ZONE, parse_zone

# 19:00 in Bangkok, 21:00 in Tokyo -- the same instant, either side of the
# 20:00 boundary, which is the whole point of the key being configurable.
BOUNDARY = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)


def test_day_in_the_default_zone() -> None:
    assert is_night(parse_zone(DEFAULT_ZONE), BOUNDARY) is False


def test_night_two_hours_east() -> None:
    assert is_night(ZoneInfo("Asia/Tokyo"), BOUNDARY) is True


def test_unknown_zone_falls_back_instead_of_raising() -> None:
    assert parse_zone("Nonsense/Zone") == ZoneInfo(DEFAULT_ZONE)
