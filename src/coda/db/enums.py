"""Domain enums shared by the ORM and stored as native Postgres enum types.

Member *values* are the strings written to the DB. ``DifficultyClass`` keeps the
in-game ordinal as a separate property so callers can map to the API's integer
difficulty without coupling the stored value to a position.
"""

from __future__ import annotations

import enum

from sqlalchemy import Enum as SAEnum

# arcaea/dto/enums is a PURE module (no db import), so depending on it here does
# not build the engine at import time and does not violate "arcaea/ never imports
# db/" -- that rule is one-directional. dto/enums.py explicitly anticipates this.
from coda.arcaea.dto.enums import ClearType, GaugeModifier


class DifficultyClass(enum.Enum):
    """A chart's difficulty slot. Stored as the lowercase string value."""

    PST = "pst"
    PRS = "prs"
    FTR = "ftr"
    BYD = "byd"
    ETR = "etr"

    BYD_2 = "byd_2"
    ERR = "err"

    @property
    def ordinal(self) -> int | None:
        """The game's integer difficulty id, or ``None`` for app-defined slots."""
        return _DIFFICULTY_ORDINALS.get(self)

    @classmethod
    def from_ordinal(cls, value: int) -> "DifficultyClass | None":
        """Map a wire difficulty int (0-4) back to a real slot, else ``None``.

        Only the five game slots have an ordinal; ``byd_2`` and ``err`` are
        app-defined and deliberately unmapped -- ``byd_2`` never arrives under
        its own int (it comes as a ``byd`` play on a consolidated song_id, see
        ``arcaea-score-mapping.md`` §3) and ``err`` never reaches the wire.
        """
        return _CLASS_BY_ORDINAL.get(value)


_DIFFICULTY_ORDINALS: dict[DifficultyClass, int] = {
    DifficultyClass.PST: 0,
    DifficultyClass.PRS: 1,
    DifficultyClass.FTR: 2,
    DifficultyClass.BYD: 3,
    DifficultyClass.ETR: 4,
}

_CLASS_BY_ORDINAL: dict[int, DifficultyClass] = {
    v: k for k, v in _DIFFICULTY_ORDINALS.items()
}


class ArtistKind(enum.Enum):
    """Whether an artist is a single person or a named unit/band (e.g.
    "Endorfin.") composed of members. Stored as the lowercase string value."""

    PERSON = "person"
    UNIT = "unit"


class LinkMethod(enum.Enum):
    """How a Discord user's link to an Arcaea account was established.

    ``account`` is *proven* -- the user logged in as the account, the only
    ownership proof the public friend-code path can never provide. ``code`` is an
    unproven claim on a public friend code. Stored as the lowercase string value.
    """

    CODE = "code"
    ACCOUNT = "account"


class RequestStatus(enum.Enum):
    """Lifecycle of a durable :class:`~coda.db.models.pending_request.PendingRequest`.
    Stored as the lowercase string value."""

    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class Side(enum.Enum):
    """A song's visual theme. Stored as the lowercase string value."""

    LIGHT = "light"
    CONFLICT = "conflict"
    COLORLESS = "colorless"
    LEPHON = "lephon"

    @classmethod
    def from_id(cls, value: int) -> Side:
        """Map the game's numeric side id (0-3) to a member."""
        return _SIDE_BY_ID[value]


_SIDE_BY_ID: dict[int, Side] = {
    0: Side.LIGHT,
    1: Side.CONFLICT,
    2: Side.COLORLESS,
    3: Side.LEPHON,
}


difficulty_class_type: SAEnum = SAEnum(
    DifficultyClass,
    name="difficulty_class",
    values_callable=lambda e: [m.value for m in e],
)

artist_kind_type: SAEnum = SAEnum(
    ArtistKind,
    name="artist_kind",
    values_callable=lambda e: [m.value for m in e],
)

link_method_type: SAEnum = SAEnum(
    LinkMethod,
    name="link_method",
    values_callable=lambda e: [m.value for m in e],
)

request_status_type: SAEnum = SAEnum(
    RequestStatus,
    name="request_status",
    values_callable=lambda e: [m.value for m in e],
)

clear_type_type: SAEnum = SAEnum(
    ClearType,
    name="clear_type",
    values_callable=lambda e: [m.value for m in e],
)

gauge_modifier_type: SAEnum = SAEnum(
    GaugeModifier,
    name="gauge_modifier",
    values_callable=lambda e: [m.value for m in e],
)

