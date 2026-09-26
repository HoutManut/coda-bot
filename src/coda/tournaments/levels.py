"""The level band a chart pool draws from. Pure -- no DB, no I/O.

Levels are stored encoded (``value * 2``, ``+1`` for a "+" level), so a range
is compared in that form and never decoded mid-query. An unset range means
ANY level, which is a real choice an organizer may make and not an error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from coda.utils.encoding import decode_level, encode_level

# The displayed shape of one bound. Deliberately stricter than encode_level,
# which accepts "?" and answers with the -1 sentinel -- a band must never be
# built out of a sentinel. A leading zero is out for the same reason: level 0
# encodes to 0, which is the TBA sentinel `qualifying` excludes, so `level:0`
# would draw an empty pool and read as an empty catalog.
_BOUND = re.compile(r"^[1-9]\d?\+?$")

ANY = "any"


@dataclass(frozen=True)
class LevelRange:
    """An inclusive band of encoded levels. ``None`` on a side means open."""

    low: int | None = None
    high: int | None = None

    @property
    def unbounded(self) -> bool:
        return self.low is None and self.high is None


def parse_level_range(text: str) -> LevelRange:
    """Parse ``""``/``"any"``/``"9"``/``"10+"``/``"9-10+"``/``"9-"``/``"-10"``.

    Raises ``ValueError`` carrying a message meant for the user.
    """
    raw = text.strip().lower()
    if not raw or raw == ANY:
        return LevelRange()

    # Levels never contain "-", so splitting on it is unambiguous.
    parts = raw.split("-")
    if len(parts) == 1:
        bound = _encode(parts[0])
        return LevelRange(bound, bound)
    if len(parts) != 2:
        raise ValueError(f"`{text}` is not a level range. Try `9`, `9-10+` or `any`.")

    low = _encode(parts[0]) if parts[0] else None
    high = _encode(parts[1]) if parts[1] else None
    if low is None and high is None:
        raise ValueError(f"`{text}` is not a level range. Try `9`, `9-10+` or `any`.")
    if low is not None and high is not None and low > high:
        raise ValueError(f"`{text}` runs backwards -- put the lower level first.")
    return LevelRange(low, high)


def display(levels: LevelRange) -> str:
    """How a band reads on the board."""
    if levels.unbounded:
        return "any level"
    if levels.low == levels.high:
        return f"level {decode_level(levels.low)}"
    low = decode_level(levels.low) if levels.low is not None else ""
    high = decode_level(levels.high) if levels.high is not None else ""
    if not low:
        return f"level {high} and below"
    if not high:
        return f"level {low} and above"
    return f"level {low}-{high}"


def _encode(bound: str) -> int:
    if not _BOUND.match(bound):
        raise ValueError(f"`{bound}` is not a level. Try `9`, `10+` or `any`.")
    return encode_level(bound)
