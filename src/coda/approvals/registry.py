"""The reusable seam: each request ``kind`` registers a handler at import.

A handler decides what a yes/no *means* for its kind and what to tell each side.
The approvals machinery (the persistent listener and the expiry sweep) stays
kind-agnostic; it looks a handler up here and dispatches. Registration's
``link_approval`` is the first handler; others register the same way.
"""

from __future__ import annotations

from typing import Protocol

import hikari
from sqlalchemy.ext.asyncio import AsyncSession

from coda.db.models import PendingRequest


class ApprovalHandler(Protocol):
    """What a request kind must implement to be resolvable."""

    async def on_decision(
        self,
        db: AsyncSession,
        request: PendingRequest,
        approved: bool,
        app: hikari.RESTAware,
    ) -> str:
        """Apply the decision. Returns the text shown to the responder.

        Runs inside the caller's transaction; must not commit. May DM the
        requester via ``app`` (the responder's own message is edited by the caller).
        """
        ...

    async def on_expire(
        self, db: AsyncSession, request: PendingRequest, app: hikari.RESTAware
    ) -> None:
        """Called when a request times out unanswered. Must not commit."""
        ...


_HANDLERS: dict[str, ApprovalHandler] = {}


def register_handler(kind: str, handler: ApprovalHandler) -> None:
    _HANDLERS[kind] = handler


def get_handler(kind: str) -> ApprovalHandler | None:
    return _HANDLERS.get(kind)
