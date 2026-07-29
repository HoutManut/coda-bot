"""The one persistent component listener and the expiry sweep for durable approvals.

Everything here is kind-agnostic: it resolves a button click or expires a stale
row and hands off to the registered handler. Registration's ``link_approval`` is
imported below purely so its handler registers at load.

⚠️ The listener filters **strictly** on the ``req:`` custom-id prefix. lightbulb's
own ``Menu``/``Modal`` buttons ride the same ``InteractionCreateEvent`` stream, so
a loose filter would double-handle every button in the bot -- and lightbulb
already handles its own, so we must ignore anything that isn't ours.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import hikari
import lightbulb

from coda.approvals import ApprovalService, get_handler, parse_custom_id
from coda.db.enums import RequestStatus
from coda.db.session import async_session

# Registers the link_approval handler for its kind at import time.
from coda.players import link_approval  # noqa: F401

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()


def _settled_embed(text: str) -> hikari.Embed:
    return hikari.Embed(title="Link request", description=text, color=0x5865F2)


@loader.listener(hikari.InteractionCreateEvent)
async def _on_component(
    event: hikari.InteractionCreateEvent, approvals: ApprovalService
) -> None:
    interaction = event.interaction
    if not isinstance(interaction, hikari.ComponentInteraction):
        return
    parsed = parse_custom_id(interaction.custom_id)
    if parsed is None:
        # Not one of ours -- lightbulb's own Menu/Modal handling owns it.
        return
    request_id, approved = parsed

    async with async_session() as db:
        request = await approvals.get(db, request_id)
        if request is None:
            await interaction.create_initial_response(
                hikari.ResponseType.MESSAGE_CREATE,
                "This request no longer exists.",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return
        if interaction.user.id != request.responder_id:
            await interaction.create_initial_response(
                hikari.ResponseType.MESSAGE_CREATE,
                "This isn't for you.",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return

        # Acknowledge now, keeping the message: the handler may DM (a network
        # round trip) and would otherwise blow the 3s interaction budget.
        await interaction.create_initial_response(
            hikari.ResponseType.DEFERRED_MESSAGE_UPDATE
        )

        resolved = await approvals.resolve(db, request_id, approved)
        if resolved is None:
            # Already answered, or expired between the DM and this click. resolve()
            # may have flipped a lapsed row to expired; persist that.
            await db.commit()
            await interaction.edit_initial_response(
                embed=_settled_embed(
                    "This request has already been handled or has expired."
                ),
                components=[],
            )
            return

        handler = get_handler(resolved.kind)
        text = (
            await handler.on_decision(db, resolved, approved, event.app)
            if handler is not None
            else "Done."
        )
        await db.commit()

    await interaction.edit_initial_response(
        embed=_settled_embed(text), components=[]
    )


@loader.task(lightbulb.uniformtrigger(minutes=5))
async def _sweep_expired(
    client: lightbulb.Client, approvals: ApprovalService
) -> None:
    """Expire stale pending rows and let each kind's handler notify the requester.

    A stale button also self-settles when clicked (``resolve`` guards expiry), so
    this is the belt to that suspenders: it fires even if nobody ever clicks.
    """
    async with async_session() as db:
        due = await approvals.due_expired(db, limit=50)
        if not due:
            return
        now = datetime.now(UTC)
        for request in due:
            request.status = RequestStatus.EXPIRED
            request.responded_at = now
            handler = get_handler(request.kind)
            if handler is not None:
                await handler.on_expire(db, request, client.app)
        await db.commit()

    # Best-effort: strip the now-dead buttons off each DM. Failure is harmless --
    # the button self-settles on click regardless.
    for request in due:
        if request.dm_channel_id is None or request.dm_message_id is None:
            continue
        try:
            await client.app.rest.edit_message(
                request.dm_channel_id,
                request.dm_message_id,
                embed=_settled_embed("This request expired with no response."),
                components=[],
            )
        except hikari.HikariError:
            logger.debug(
                "could not strip buttons off expired request %s", request.id
            )
