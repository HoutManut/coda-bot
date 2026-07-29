"""Durable, restart-surviving approval requests.

A feature creates a :class:`PendingRequest` (via :class:`ApprovalService`) and
registers a handler for its ``kind`` (via :func:`register_handler`). A single
persistent listener resolves button clicks and a periodic sweep expires stale
rows; both dispatch to the registered handler. See
``coda.players.link_approval`` for the first consumer, and
``wiki/flows/registration.md`` for why the flow exists.
"""

from __future__ import annotations

from coda.approvals.components import (
    CUSTOM_ID_PREFIX,
    decision_row,
    parse_custom_id,
)
from coda.approvals.registry import (
    ApprovalHandler,
    get_handler,
    register_handler,
)
from coda.approvals.service import ApprovalService

__all__ = [
    "ApprovalService",
    "ApprovalHandler",
    "register_handler",
    "get_handler",
    "decision_row",
    "parse_custom_id",
    "CUSTOM_ID_PREFIX",
]
