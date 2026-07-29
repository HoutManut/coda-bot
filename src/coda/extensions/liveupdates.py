"""/liveupdates -- where a user's live score updates go, and which channels allow them.

Server admins allowlist channels; users pick from that allowlist. DM is the
default and always available.

Two different pickers, deliberately:

* ``allow``/``disallow`` (admin) use Discord's **native** channel picker -- any
  text channel is a legitimate choice there, so the built-in is exactly right.
* ``channel`` (user) uses **autocomplete over the allowlist** instead. Discord's
  picker validates a channel's *type*, not its membership of our allowlist, so
  using it would let a user pick a disallowed channel and force us to reject it
  after the fact. Building the list ourselves makes the invalid choice
  unrepresentable rather than merely refused.
"""

from __future__ import annotations

import logging

import hikari
import lightbulb

from coda.db.session import async_session
from coda.players.live import LiveUpdateService
from coda.utils.permissions import can_send_in

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()
live_group = lightbulb.Group("liveupdates", "Where your live score updates go")

_COLOR_OK = 0x57F287
_COLOR_ERR = 0xED4245

_DM_CHOICE = "dm"
_MAX_CHOICES = 25  # Discord's hard cap on autocomplete results.


def _embed(title: str, description: str, *, ok: bool = True) -> hikari.Embed:
    return hikari.Embed(
        title=title, description=description, color=_COLOR_OK if ok else _COLOR_ERR
    )


async def _ac_channel(ctx: lightbulb.AutocompleteContext[str]) -> None:
    """Offer DM plus whichever channels this guild allows.

    Filtered to channels the member can actually post in, so the list only ever
    contains real choices -- the point of not using Discord's native picker.
    """
    choices: list[tuple[str, str]] = [("Direct Messages", _DM_CHOICE)]
    guild_id = ctx.interaction.guild_id
    app = ctx.client.app
    if guild_id is not None and isinstance(app, hikari.CacheAware):
        async with async_session() as db:
            allowed = await LiveUpdateService().allowed_channels(db, int(guild_id))
        member = ctx.interaction.member
        for channel_id in allowed:
            if member is not None and can_send_in(app, channel_id, member) is False:
                continue
            channel = app.cache.get_guild_channel(channel_id)
            name = f"#{channel.name}" if channel is not None else f"#{channel_id}"
            choices.append((name, str(channel_id)))

    typed = str(ctx.focused.value or "").lower()
    matches = [c for c in choices if typed in c[0].lower()]
    await ctx.respond(matches[:_MAX_CHOICES])


def _is_admin(ctx: lightbulb.Context) -> bool:
    """Manage Channels, checked inline -- the house pattern for gating."""
    return (
        ctx.member is not None
        and bool(ctx.member.permissions & hikari.Permissions.MANAGE_CHANNELS)
    )


@loader.command
@live_group.register
class Allow(
    lightbulb.SlashCommand,
    name="allow",
    description="Allow live score updates in a channel (admin)",
):
    # The native picker is right here: any text channel is a valid choice.
    channel = lightbulb.channel(
        "channel",
        "Channel to allow score updates in",
        channel_types=[hikari.ChannelType.GUILD_TEXT],
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context, svc: LiveUpdateService) -> None:
        if ctx.guild_id is None:
            await ctx.respond(_embed("Not here", "Use this in a server.", ok=False), ephemeral=True)
            return
        if not _is_admin(ctx):
            await ctx.respond(
                _embed("Nope", "You need **Manage Channels** to do that.", ok=False),
                ephemeral=True,
            )
            return

        async with async_session() as db:
            added = await svc.allow(
                db, int(ctx.guild_id), int(self.channel.id), int(ctx.user.id)
            )

        await ctx.respond(
            _embed(
                "Channel allowed" if added else "Already allowed",
                f"<#{self.channel.id}> "
                + (
                    "now accepts live score updates. Members can point their "
                    "updates at it with `/liveupdates channel`."
                    if added
                    else "was already on the list."
                ),
            ),
            ephemeral=True,
        )


@loader.command
@live_group.register
class Disallow(
    lightbulb.SlashCommand,
    name="disallow",
    description="Stop allowing live score updates in a channel (admin)",
):
    channel = lightbulb.channel(
        "channel",
        "Channel to stop allowing",
        channel_types=[hikari.ChannelType.GUILD_TEXT],
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context, svc: LiveUpdateService) -> None:
        if ctx.guild_id is None:
            await ctx.respond(_embed("Not here", "Use this in a server.", ok=False), ephemeral=True)
            return
        if not _is_admin(ctx):
            await ctx.respond(
                _embed("Nope", "You need **Manage Channels** to do that.", ok=False),
                ephemeral=True,
            )
            return

        async with async_session() as db:
            removed = await svc.disallow(db, int(ctx.guild_id), int(self.channel.id))

        await ctx.respond(
            _embed(
                "Channel removed" if removed else "Not on the list",
                f"<#{self.channel.id}> "
                + (
                    "no longer accepts live updates. Anyone pointed at it falls "
                    "back to DMs automatically."
                    if removed
                    else "wasn't allowing live updates anyway."
                ),
            ),
            ephemeral=True,
        )


@loader.command
@live_group.register
class Channel(
    lightbulb.SlashCommand,
    name="channel",
    description="Choose where your live score updates go",
):
    where = lightbulb.string(
        "where",
        "Direct Messages, or a channel this server allows",
        autocomplete=_ac_channel,
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context, svc: LiveUpdateService) -> None:
        if self.where == _DM_CHOICE:
            async with async_session() as db:
                await svc.set_destination(db, int(ctx.user.id), None)
            await ctx.respond(
                _embed("Updates moved", "Your live updates will arrive in your **DMs**."),
                ephemeral=True,
            )
            return

        try:
            channel_id = int(self.where)
        except ValueError:
            await ctx.respond(
                _embed("Unknown channel", "Pick one from the list.", ok=False),
                ephemeral=True,
            )
            return

        async with async_session() as db:
            # Re-check rather than trust the value: autocomplete is a
            # suggestion, and Discord will submit anything the user typed.
            if not await svc.is_allowed(db, channel_id):
                await ctx.respond(
                    _embed(
                        "Not allowed there",
                        f"<#{channel_id}> isn't set up for live score updates. "
                        "An admin can allow it with `/liveupdates allow`.",
                        ok=False,
                    ),
                    ephemeral=True,
                )
                return
            if not await self._can_post(ctx, channel_id):
                await ctx.respond(
                    _embed(
                        "You can't post there",
                        f"You need to be able to send messages in <#{channel_id}> "
                        "to send your updates to it.",
                        ok=False,
                    ),
                    ephemeral=True,
                )
                return
            await svc.set_destination(db, int(ctx.user.id), channel_id)

        await ctx.respond(
            _embed("Updates moved", f"Your live updates will now post in <#{channel_id}>."),
            ephemeral=True,
        )

    async def _can_post(self, ctx: lightbulb.Context, channel_id: int) -> bool:
        """Whether the caller may send messages in the target channel.

        The allowlist is guild-wide, but a channel on it can still be one this
        particular member cannot post in. Only False rejects: a cache miss
        returns None and is allowed through, since refusing on a cold cache
        would block legitimate choices, and posting re-checks anyway.
        """
        if ctx.member is None:
            return False
        app = ctx.client.app
        if not isinstance(app, hikari.CacheAware):
            return True  # Can't check without a cache; posting re-checks anyway.
        return can_send_in(app, channel_id, ctx.member) is not False


@loader.command
@live_group.register
class Off(
    lightbulb.SlashCommand, name="off", description="Stop live score updates"
):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context, svc: LiveUpdateService) -> None:
        async with async_session() as db:
            await svc.set_enabled(db, int(ctx.user.id), False)
        await ctx.respond(
            _embed(
                "Live updates off",
                "I'll stop posting your plays. `/liveupdates on` turns them back "
                "on — your chosen channel is remembered.",
            ),
            ephemeral=True,
        )


@loader.command
@live_group.register
class On(
    lightbulb.SlashCommand, name="on", description="Start live score updates"
):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context, svc: LiveUpdateService) -> None:
        async with async_session() as db:
            await svc.set_enabled(db, int(ctx.user.id), True)
            _, channel_id = await svc.resolve_destination(db, int(ctx.user.id))
        where = f"<#{channel_id}>" if channel_id else "your **DMs**"
        await ctx.respond(
            _embed("Live updates on", f"Your plays will post in {where}."),
            ephemeral=True,
        )


@loader.command
@live_group.register
class Status(
    lightbulb.SlashCommand,
    name="status",
    description="Show where your live updates currently go",
):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context, svc: LiveUpdateService) -> None:
        async with async_session() as db:
            enabled, channel_id = await svc.resolve_destination(db, int(ctx.user.id))
            pref = await svc.get_pref(db, int(ctx.user.id))
            allowed = (
                await svc.allowed_channels(db, int(ctx.guild_id))
                if ctx.guild_id is not None
                else []
            )

        if not enabled:
            body = "**Off.** `/liveupdates on` starts them again."
        else:
            body = f"**On**, posting to {f'<#{channel_id}>' if channel_id else 'your **DMs**'}."
            # Explain the fallback rather than silently showing DM: the user
            # chose a channel and deserves to know why it is not being used.
            if pref is not None and pref.channel_id and channel_id is None:
                body += (
                    f"\n\nYou'd picked <#{pref.channel_id}>, but it no longer "
                    "allows live updates, so they're going to your DMs instead."
                )

        embed = _embed("Live updates", body)
        if allowed:
            embed.add_field(
                name="Allowed in this server",
                value="\n".join(f"<#{c}>" for c in allowed[:10]),
                inline=False,
            )
        await ctx.respond(embed, ephemeral=True)


loader.command(live_group)
