"""The ``link_approval`` request kind: ask an account's owner before a second
Discord user may code-link it.

Registration produces this when :meth:`RegistrationService.register_by_code`
returns ``NeedsApproval``. The owner gets a DM with Approve/Deny buttons; their
answer (or a 24h timeout) is resolved by the durable machinery in
``coda.approvals`` and dispatched back here.
"""

from __future__ import annotations

import logging
from datetime import timedelta

import hikari
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from coda.approvals import ApprovalService, decision_row, register_handler
from coda.db.enums import LinkMethod, RequestStatus
from coda.db.models import ArcaeaAccount, PendingRequest, PlayerLink
from coda.utils.dm import send_dm

logger = logging.getLogger(__name__)

KIND = "link_approval"
TTL = timedelta(hours=24)

_COLOR_ASK = 0x5865F2
_COLOR_OK = 0x57F287
_COLOR_ERR = 0xED4245


def _owner_prompt_embed(requester_id: int, friend_code: str) -> hikari.Embed:
    return hikari.Embed(
        title="Approve a link to your Arcaea account?",
        description=(
            f"<@{requester_id}> wants to register the account behind friend code "
            f"**{friend_code}** — an account you already own.\n\n"
            "• **Approve** if that's you (an alt or a shared account) — they'll be "
            "able to track scores from it.\n"
            "• **Deny** if you don't recognise them.\n\n"
            "This request expires in 24 hours."
        ),
        color=_COLOR_ASK,
    )


def _approved_embed(friend_code: str) -> hikari.Embed:
    return hikari.Embed(
        title="Link approved",
        description=(
            f"The owner approved your request. You're now linked to **{friend_code}** "
            "and I'll track scores from it."
        ),
        color=_COLOR_OK,
    )


def _denied_embed(friend_code: str) -> hikari.Embed:
    return hikari.Embed(
        title="Link denied",
        description=(
            f"The owner declined your request to link **{friend_code}**.\n\n"
            "If you're sure this account is yours, link it with "
            "`/register method:account` — logging in proves ownership, which a "
            "friend code can't. Otherwise, ask an admin."
        ),
        color=_COLOR_ERR,
    )


def _approved_but_elsewhere_embed(friend_code: str) -> hikari.Embed:
    return hikari.Embed(
        title="Link approved — but you've since linked another account",
        description=(
            f"The owner approved your request for **{friend_code}**, but you've "
            "already linked a different account since. You can only have one "
            "linked at a time — `/unregister` the current one first if you want "
            "to switch to this account."
        ),
        color=_COLOR_ERR,
    )


def _expired_embed(friend_code: str) -> hikari.Embed:
    return hikari.Embed(
        title="Link request expired",
        description=(
            f"No response within 24 hours on your request to link **{friend_code}**. "
            "Ask an admin if you still need it."
        ),
        color=_COLOR_ERR,
    )


async def request_link(
    db: AsyncSession,
    app: hikari.RESTAware,
    approvals: ApprovalService,
    *,
    requester_id: int,
    owner_id: int,
    account: ArcaeaAccount,
) -> str:
    """Create the request and DM the owner. Returns the requester's ephemeral text.

    DMs the owner *first* (well, creates then flushes to get the button ids, then
    DMs): if that DM cannot land, the request is rolled back rather than parked
    where nobody will ever see it, and the requester is told immediately. Silence
    must never mean yes.
    """
    dup = await db.execute(
        select(PendingRequest.id)
        .where(
            PendingRequest.kind == KIND,
            PendingRequest.requester_id == requester_id,
            PendingRequest.status == RequestStatus.PENDING,
            PendingRequest.payload["arcaea_account_id"].astext == str(account.id),
        )
        .limit(1)
    )
    if dup.scalar_one_or_none() is not None:
        return (
            "You already have a pending request for that account — please wait for "
            "the owner to respond."
        )

    request = await approvals.create(
        db,
        kind=KIND,
        requester_id=requester_id,
        responder_id=owner_id,
        payload={"arcaea_account_id": account.id, "friend_code": account.friend_code},
        ttl=TTL,
    )
    message = await send_dm(
        app,
        owner_id,
        embed=_owner_prompt_embed(requester_id, account.friend_code),
        components=[decision_row(request.id)],
    )
    if message is None:
        # No orphan row: undo the insert we just flushed.
        await db.rollback()
        return (
            "That account is registered to someone I can't reach right now (their "
            "DMs are closed). Ask an admin to help link it."
        )

    request.dm_channel_id = int(message.channel_id)
    request.dm_message_id = int(message.id)
    await db.commit()
    return (
        "That account is already registered by someone else. I've asked them to "
        "approve your link — you'll get a DM with their answer."
    )


class _LinkApprovalHandler:
    """Resolves a decided/expired ``link_approval`` request."""

    async def on_decision(
        self,
        db: AsyncSession,
        request: PendingRequest,
        approved: bool,
        app: hikari.RESTAware,
    ) -> str:
        requester_id = request.requester_id
        account_id = int(request.payload["arcaea_account_id"])
        friend_code = request.payload["friend_code"]

        if not approved:
            await send_dm(app, requester_id, embed=_denied_embed(friend_code))
            return "Denied — no link was created."

        # Re-check: the requester may have linked something else while this sat.
        # One account per Discord user (UniqueConstraint("discord_id")), so they
        # hold at most one link -- branch on which account it points at.
        current = await db.execute(
            select(PlayerLink.arcaea_account_id)
            .where(PlayerLink.discord_id == requester_id)
            .limit(1)
        )
        linked_account = current.scalar_one_or_none()
        if linked_account == account_id:
            # Already linked here (e.g. they proved it by logging in meanwhile).
            await send_dm(app, requester_id, embed=_approved_embed(friend_code))
            return "Approved — they were already linked to this account."
        if linked_account is not None:
            # They linked a *different* account while this sat; the one-account
            # rule blocks a second link. Nothing to create.
            await send_dm(
                app, requester_id, embed=_approved_but_elsewhere_embed(friend_code)
            )
            return "Approved, but they had already linked a different account."

        db.add(
            PlayerLink(
                discord_id=requester_id,
                arcaea_account_id=account_id,
                # An approved code claim is still a code link, and the owner
                # keeps ownership.
                linked_via=LinkMethod.CODE,
                is_owner=False,
            )
        )
        await send_dm(app, requester_id, embed=_approved_embed(friend_code))
        return "Approved — they can now track scores from this account."

    async def on_expire(
        self, db: AsyncSession, request: PendingRequest, app: hikari.RESTAware
    ) -> None:
        await send_dm(
            app,
            request.requester_id,
            embed=_expired_embed(request.payload["friend_code"]),
        )


register_handler(KIND, _LinkApprovalHandler())
