"""Session lifecycle: the only module that knows what a sid is.

Imports ``coda.arcaea`` (for the wire) and ``coda.db`` (to persist), which is
exactly the pairing that lets ``coda.arcaea`` stay DB-free.
"""

from __future__ import annotations

from coda.sessions.adapters import (
    AccountAuth,
    BotAccountAdapter,
    PlayerCredentialAdapter,
)
from coda.sessions.pool import NoCapacity, SessionPool
from coda.sessions.session import AccountSession, BotSession

__all__ = [
    "AccountSession",
    "BotSession",
    "SessionPool",
    "NoCapacity",
    "AccountAuth",
    "BotAccountAdapter",
    "PlayerCredentialAdapter",
]
