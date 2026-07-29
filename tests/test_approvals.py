"""ApprovalService.resolve guards (handoff 02): a request can be approved once,
and never after it has expired or already been answered."""

from __future__ import annotations

from datetime import timedelta

from coda.approvals import ApprovalService
from coda.db.enums import RequestStatus

SVC = ApprovalService()


async def _create(db, ttl: timedelta):
    return await SVC.create(
        db,
        kind="test",
        requester_id=1,
        responder_id=2,
        payload={"x": 1},
        ttl=ttl,
    )


async def test_resolve_approves_a_pending_request(db):
    request = await _create(db, timedelta(hours=1))
    resolved = await SVC.resolve(db, request.id, approved=True)
    assert resolved is not None
    assert resolved.status is RequestStatus.APPROVED
    assert resolved.responded_at is not None


async def test_resolve_denies_a_pending_request(db):
    request = await _create(db, timedelta(hours=1))
    resolved = await SVC.resolve(db, request.id, approved=False)
    assert resolved is not None
    assert resolved.status is RequestStatus.DENIED


async def test_resolve_refuses_an_already_answered_request(db):
    request = await _create(db, timedelta(hours=1))
    await SVC.resolve(db, request.id, approved=True)
    # Second answer must not flip an already-approved row.
    again = await SVC.resolve(db, request.id, approved=False)
    assert again is None
    row = await SVC.get(db, request.id)
    assert row is not None
    assert row.status is RequestStatus.APPROVED


async def test_resolve_refuses_and_expires_a_lapsed_request(db):
    request = await _create(db, timedelta(seconds=-1))  # already past its deadline
    resolved = await SVC.resolve(db, request.id, approved=True)
    assert resolved is None
    # The lapsed row is flipped to expired so a stale click settles it.
    row = await SVC.get(db, request.id)
    assert row is not None
    assert row.status is RequestStatus.EXPIRED


async def test_due_expired_finds_lapsed_pending_rows(db):
    lapsed = await _create(db, timedelta(seconds=-5))
    fresh = await _create(db, timedelta(hours=1))
    due_ids = {r.id for r in await SVC.due_expired(db, limit=50)}
    assert lapsed.id in due_ids
    assert fresh.id not in due_ids
