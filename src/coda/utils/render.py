"""Shared plumbing for the chart-rendering commands (``/song``, ``/score``, ``/calc``).

Each builds one embed, sometimes with a jacket and a row of stateless buttons,
and each has to render that payload two ways: as a fresh slash-command reply,
and as an edit of the message a button click arrived on. The second path is the
fiddly one -- attachment replacement, and tearing down a dead end that landed on
an already-public message -- so it lives here once instead of in each command.

Everything ships as a Components V2 container. The embed survives as the
authoring format because it is a far more convenient thing to build, and
converting at the boundary means the blurred and unblurred cases stay one
renderer rather than two that can drift apart.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import hikari
import lightbulb
from hikari.impl import MessageActionRowBuilder
from hikari.impl.special_endpoints import ContainerComponentBuilder

from coda.utils.container import as_container

# A transient dead end that can't be made ephemeral (it landed on an already
# public message) is auto-removed after this many seconds instead of lingering.
DEAD_END_TTL = 15

COLOR_INFO = 0x5865F2


@dataclass
class Rendered:
    """An embed + optional jacket + component rows, ready to send or edit-into.

    The embed is the *authoring* format only: every payload here ships as a
    Components V2 container (see ``utils/container``). Building embeds and
    converting once keeps one renderer for the blurred and unblurred cases, and
    means a spoilered chart differs from an ordinary one by exactly one flag.
    """

    embed: hikari.Embed
    file: hikari.File | None = None
    rows: list[MessageActionRowBuilder] = field(default_factory=list)
    # A dead end (no result / error): never worth leaving in a channel.
    # `respond` forces it ephemeral; `apply` deletes it after a timeout when it
    # lands on a message that is already public.
    transient: bool = False
    # Blurred behind a click. Set from the chart's effective version.
    spoiler: bool = False

    def build(self) -> ContainerComponentBuilder:
        return as_container(self.embed, self.rows, spoiler=self.spoiler)


def notice(title: str, description: str, *, transient: bool = False) -> Rendered:
    """A text-only payload: a prompt, or a dead end that carries no result."""
    return Rendered(
        hikari.Embed(title=title, description=description, color=COLOR_INFO),
        transient=transient,
    )


def button_row(buttons: list[tuple[str, str]]) -> MessageActionRowBuilder:
    """A row of up to five secondary buttons, each ``(label, custom_id)``."""
    row = MessageActionRowBuilder()
    for label, custom_id in buttons[:5]:
        row.add_interactive_button(
            hikari.ButtonStyle.SECONDARY, custom_id, label=label[:80]
        )
    return row


async def respond(
    ctx: lightbulb.Context, rendered: Rendered, *, ephemeral: bool | None
) -> None:
    """Send a payload as a command's initial reply.

    ``ephemeral=None`` means the user left the option unset, so a spoilered
    payload decides for them -- an explicit ``False`` still shares it.
    """
    # A dead end never clutters a channel: force the initial response ephemeral
    # (always allowed on create), overriding the user's share choice. Because
    # this is the first response, ephemeral always succeeds -- no timeout needed.
    if rendered.transient:
        ephemeral = True
    elif ephemeral is None:
        ephemeral = rendered.spoiler
    # A Components V2 message carries no embed; the jacket rides along as the
    # container's own attachment, recovered from the embed's thumbnail/image.
    await ctx.respond(components=[rendered.build()], ephemeral=ephemeral)


async def apply(
    interaction: hikari.ComponentInteraction, rendered: Rendered
) -> None:
    """Replace the message a button click arrived on with this payload.

    Every view these commands produce is a container, so an edit never has to
    change a message's shape -- which matters because Discord never lets
    ``IS_COMPONENTS_V2`` come off a message once it is set.
    """
    # Edit via edit_initial_response, not MESSAGE_UPDATE: only the edit builder
    # rebuilds `attachments` from the container's File, replacing the prior
    # jacket instead of leaving it behind as a second image. attachments=None
    # clears it when a view has none.
    await interaction.create_initial_response(
        hikari.ResponseType.DEFERRED_MESSAGE_UPDATE
    )
    await interaction.edit_initial_response(
        components=[rendered.build()],
        attachments=hikari.UNDEFINED if rendered.file is not None else None,
    )
    # A dead end reached via a button edits a message that is already public and
    # can't be made ephemeral after the fact -- so tear it down after a timeout
    # rather than leave the error sitting in the channel. (An ephemeral source
    # message needs nothing; Discord drops it on its own.)
    if rendered.transient and not is_ephemeral(interaction.message):
        asyncio.create_task(_delete_after(interaction, DEAD_END_TTL))


def is_ephemeral(message: hikari.Message | None) -> bool:
    """Whether a message only its recipient can see -- and so dismiss."""
    return message is not None and bool(message.flags & hikari.MessageFlag.EPHEMERAL)


async def _delete_after(
    interaction: hikari.ComponentInteraction, delay: float
) -> None:
    await asyncio.sleep(delay)
    try:
        await interaction.delete_initial_response()
    except hikari.NotFoundError:
        pass  # already gone (dismissed, or another edit deleted it)
