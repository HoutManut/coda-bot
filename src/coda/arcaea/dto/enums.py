"""Domain vocabulary the DTO boundary translates wire ints into.

These live here, not in ``coda/db/enums.py``, for a mechanical reason: importing
``coda.db.enums`` executes ``coda/db/__init__.py``, which builds the async engine
at import time. Depending on that would make this package unimportable without a
live DATABASE_URL and break the "arcaea/ never imports db/" rule.

When a score table eventually stores these, ``db/enums.py`` should import them
from here and wrap them in ``SAEnum(..., values_callable=...)`` like the other
domain enums -- the string values below are already chosen for that.
"""

from __future__ import annotations

import enum
import logging

logger = logging.getLogger(__name__)


class ClearType(enum.Enum):
    """How a play ended. Own-credentials path only -- never on friend scores."""

    TRACK_LOST = "track_lost"
    CLEAR = "clear"
    FULL_RECALL = "full_recall"
    PURE_MEMORY = "pure_memory"
    EASY_CLEAR = "easy_clear"
    HARD_CLEAR = "hard_clear"

    @classmethod
    def from_wire(cls, value: object) -> "ClearType | None":
        """Map the wire int, or None if absent/unrecognized.

        An unknown value means lowiro added a clear type; that is a log line and
        a None, never a crash on an otherwise good score.
        """
        member = _CLEAR_BY_ID.get(value) if isinstance(value, int) else None
        if member is None and value is not None:
            logger.warning("unrecognized clear_type %r -- lowiro may have added one", value)
        return member


_CLEAR_BY_ID: dict[int, ClearType] = {
    0: ClearType.TRACK_LOST,
    1: ClearType.CLEAR,
    2: ClearType.FULL_RECALL,
    3: ClearType.PURE_MEMORY,
    4: ClearType.EASY_CLEAR,
    5: ClearType.HARD_CLEAR,
}


class GaugeModifier(enum.Enum):
    """Which gauge a play used. Own-credentials path only.

    Load-bearing beyond display: excluding a hard-gauge loss from the PTT
    recent-30 pool needs ``clear_type == TRACK_LOST`` AND ``modifier == HARD``
    together -- never clear_type alone.
    """

    NORMAL = "normal"
    EASY = "easy"
    HARD = "hard"

    @classmethod
    def from_wire(cls, value: object) -> "GaugeModifier | None":
        """Map the wire int, or None if absent/unrecognized."""
        member = _GAUGE_BY_ID.get(value) if isinstance(value, int) else None
        if member is None and value is not None:
            logger.warning("unrecognized modifier %r -- lowiro may have added one", value)
        return member


_GAUGE_BY_ID: dict[int, GaugeModifier] = {
    0: GaugeModifier.NORMAL,
    1: GaugeModifier.EASY,
    2: GaugeModifier.HARD,
}
