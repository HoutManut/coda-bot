"""Daily numbering and rollover.

Puzzles are **numbered, not dated**. A guild's timezone moves *when* puzzle #N
unlocks there; it never changes *which* chart #N is, which is what lets streaks
be global while rollover stays local.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from coda.utils.zones import DEFAULT_ZONE, parse_zone

# Local 00:00 + 4h, so someone still up at 02:00 is playing the day they think
# they are. It also lands clear of DST, which moves 02:00-03:00.
ROLLOVER_HOUR = 4

APRIL_WINDOW_DAYS = 7


def puzzle_number(epoch: date, tz: ZoneInfo, now: datetime) -> int:
    local = now.astimezone(tz)
    day = (local - timedelta(hours=ROLLOVER_HOUR)).date()
    return (day - epoch).days + 1


def reference_date(epoch: date, number: int) -> date:
    """The date on the reference calendar that puzzle ``number`` belongs to."""
    return epoch + timedelta(days=number - 1)


def unlock_at(epoch: date, tz: ZoneInfo, number: int) -> datetime:
    """When puzzle ``number`` unlocks in ``tz``, as UTC."""
    local = datetime.combine(
        reference_date(epoch, number), time(hour=ROLLOVER_HOUR), tzinfo=tz
    )
    return local.astimezone(UTC)


def expires_at(epoch: date, tz: ZoneInfo, number: int) -> datetime:
    """A daily dies at the next rollover in the zone that served it."""
    return unlock_at(epoch, tz, number + 1)


def is_april_first(epoch: date, number: int) -> bool:
    """Read off the reference calendar, never a guild clock — #N must be the
    same joke everywhere."""
    day = reference_date(epoch, number)
    return (day.month, day.day) == (4, 1)


def in_april_window(now: datetime) -> bool:
    """April 1-7 inclusive on the reference calendar."""
    # The reference calendar, not a guild clock: the same zone the `timezone`
    # key defaults to, so a guild that never overrode it sees no discontinuity.
    day = now.astimezone(parse_zone(DEFAULT_ZONE)).date()
    return day.month == 4 and 1 <= day.day <= APRIL_WINDOW_DAYS
