"""Player registration and live-update destinations.

Sits above ``sessions/`` and ``db/``: it asks the pool for a session and never
learns which bot account it got.
"""

from __future__ import annotations

from coda.players.errors import (
    AccountClaimed,
    AlreadyLinkedElsewhere,
    AlreadyRegistered,
    AmbiguousFriend,
    PlayerUnreachable,
    RegistrationError,
    ReservedCodeError,
)
from coda.players.service import RegistrationService

__all__ = [
    "RegistrationService",
    "RegistrationError",
    "PlayerUnreachable",
    "AmbiguousFriend",
    "AlreadyRegistered",
    "AlreadyLinkedElsewhere",
    "ReservedCodeError",
    "AccountClaimed",
]
