"""A durable request awaiting a human decision, surviving bot restarts.

Generalized on purpose: registration's "ask the owner before linking" is the
first consumer, not the only one. A ``kind`` string routes each row to a handler
registered in :mod:`coda.approvals.registry`, and ``payload`` carries whatever
that kind needs. The in-memory ``Menu.attach`` flows elsewhere cannot do this --
the requester's interaction is long dead by the time the responder answers hours
later, and a restart drops it silently.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from coda.db.base import Base
from coda.db.enums import RequestStatus, request_status_type


class PendingRequest(Base):
    """One awaited decision. Terminal statuses are set once and never reopened."""

    __tablename__ = "pending_requests"
    __table_args__ = (
        # The expiry sweep scans pending rows past their deadline.
        Index("ix_pending_requests_sweep", "status", "expires_at"),
        # A handler looks up what a given responder still owes an answer on.
        Index("ix_pending_requests_lookup", "kind", "responder_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Handler key, e.g. "link_approval". Routes to a registered handler at decision
    # and expiry time.
    kind: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[RequestStatus] = mapped_column(
        request_status_type,
        nullable=False,
        default=RequestStatus.PENDING,
        server_default=RequestStatus.PENDING.value,
    )

    # Discord ids: who asked, and who must answer.
    requester_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    responder_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Kind-specific. For link_approval: {"arcaea_account_id": int, "friend_code": str}.
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # The DM carrying the decision buttons, so it can be stripped and rewritten
    # once answered. Nullable: set only after the DM lands.
    dm_channel_id: Mapped[int | None] = mapped_column(BigInteger)
    dm_message_id: Mapped[int | None] = mapped_column(BigInteger)
