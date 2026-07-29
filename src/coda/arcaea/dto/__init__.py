"""Raw dict -> typed objects. No I/O, no DB, no exceptions leaking upward.

**The private webapi changes without notice** -- no versioning, no deprecation.
A key that exists today can vanish, and the failure mode is a hard KeyError on
every call. Absorbing that is this package's entire job: use ``.get()`` with
explicit defaults, validate at the boundary, and fail with "lowiro changed the
API" (:class:`~coda.arcaea.errors.UnexpectedResponse`) rather than a bare
KeyError from deep inside a comprehension.
"""

from __future__ import annotations

from coda.arcaea.dto.enums import ClearType, GaugeModifier
from coda.arcaea.dto.friend import Friend, parse_friend, parse_friends
from coda.arcaea.dto.me import Me, parse_me
from coda.arcaea.dto.score import ScoreResult, from_friend_wire, from_own_wire

__all__ = [
    "ClearType",
    "GaugeModifier",
    "ScoreResult",
    "from_friend_wire",
    "from_own_wire",
    "Friend",
    "parse_friend",
    "parse_friends",
    "Me",
    "parse_me",
]
