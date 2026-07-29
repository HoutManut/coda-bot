"""Stateless store operations over :class:`PendingRequest`.

Takes the session per call and never commits -- the caller owns the transaction,
exactly as ``RegistrationService`` and ``ConfigService`` do.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from coda.db.enums import RequestStatus
from coda.db.models import PendingRequest

logger = logging.getLogger(__name__)


class ApprovalService:
    async def create(
        self,
        db: AsyncSession,
        *,
        kind: str,
        requester_id: int,
        responder_id: int,
        payload: dict[str, Any],
        ttl: timedelta,
    ) -> PendingRequest:
        """Create a pending request and flush it, so ``id`` is available."""
        request = PendingRequest(
            kind=kind,
            status=RequestStatus.PENDING,
            requester_id=requester_id,
            responder_id=responder_id,
            payload=payload,
            expires_at=datetime.now(UTC) + ttl,
        )
        db.add(request)
        await db.flush()
        return request

    async def get(self, db: AsyncSession, request_id: int) -> PendingRequest | None:
        return await db.get(PendingRequest, request_id)

    async def resolve(
        self, db: AsyncSession, request_id: int, approved: bool
    ) -> PendingRequest | None:
        """Move a pending request to approved/denied, guarding status and expiry.

        Returns the row on success, or ``None`` if it was already answered, does
        not exist, or has expired -- an expired or resolved request can never be
        approved. An expired-but-still-pending row is flipped to ``expired`` here
        so a stale button click settles it rather than silently doing nothing.
        """
        request = await self.get(db, request_id)
        if request is None or request.status is not RequestStatus.PENDING:
            return None
        now = datetime.now(UTC)
        if request.expires_at <= now:
            request.status = RequestStatus.EXPIRED
            request.responded_at = now
            return None
        request.status = RequestStatus.APPROVED if approved else RequestStatus.DENIED
        request.responded_at = now
        return request

    async def due_expired(
        self, db: AsyncSession, limit: int
    ) -> list[PendingRequest]:
        """Pending rows past their deadline, oldest first."""
        rows = await db.execute(
            select(PendingRequest)
            .where(
                PendingRequest.status == RequestStatus.PENDING,
                PendingRequest.expires_at <= datetime.now(UTC),
            )
            .order_by(PendingRequest.expires_at)
            .limit(limit)
        )
        return list(rows.scalars())
