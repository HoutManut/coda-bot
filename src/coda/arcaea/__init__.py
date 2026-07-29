"""Pure wire layer for lowiro's private webapi.

**This package never imports ``coda.db`` and never persists anything.** It does
not know what a sid means beyond "a string you pass back"; ``sessions/`` owns
that. See ``wiki/modules/arcaea.md`` for the layer rules and
``wiki/domains/auth-and-sessions.md`` for the wire behavior itself. The API
changes without notice, so re-check this code against the live wire after any
lowiro update -- the wiki records what was true when it was captured.
"""

from __future__ import annotations

from coda.arcaea.errors import (
    AlreadyFriend,
    ApiError,
    ArcaeaError,
    InvalidCredentials,
    PlayerNotFound,
    SessionExpired,
    UnexpectedResponse,
)

__all__ = [
    "ArcaeaError",
    "ApiError",
    "SessionExpired",
    "PlayerNotFound",
    "AlreadyFriend",
    "InvalidCredentials",
    "UnexpectedResponse",
]
