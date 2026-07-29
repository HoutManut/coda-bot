"""Bot configuration commands: /config user|channel|server [key] [value].

Bot-wide settings live on ``/run``, not here: this surface is the public
picker, and everything it lists is a name every user can read.
"""

from __future__ import annotations

from typing import Any

import hikari
import lightbulb
from sqlalchemy import or_, select

from coda.db.session import async_session
from coda.settings import ConfigService, Scope, parse_value, user_keys
from coda.settings.model import ConfigValue
from coda.settings.service import GLOBAL_SCOPE_ID

loader = lightbulb.Loader()
config_group = lightbulb.Group("config", "Bot configuration")

# Per-scope key choice lists, computed once at import time. Every one of them
# is built from user_keys() -- an owner key must never reach this picker.
_USER_KEYS = user_keys()
_KEYS_USER = [lightbulb.Choice(name=k, value=k) for k, d in _USER_KEYS.items() if Scope.USER in d.settable_scopes]
_KEYS_CHANNEL = [lightbulb.Choice(name=k, value=k) for k, d in _USER_KEYS.items() if Scope.CHANNEL in d.settable_scopes]
_KEYS_GUILD = [lightbulb.Choice(name=k, value=k) for k, d in _USER_KEYS.items() if Scope.GUILD in d.settable_scopes]
_KEYS_VIEW = [lightbulb.Choice(name="all", value="all")] + [lightbulb.Choice(name=k, value=k) for k in _USER_KEYS]

_NEUTRAL_COLOR = 0x99AAB5

_SCOPE_COLOR: dict[Scope, int] = {
    Scope.GUILD:   0x5865F2,
    Scope.CHANNEL: 0x57F287,
    Scope.USER:    0xEB459E,
}

_SCOPE_LABEL: dict[Scope, str] = {
    Scope.GUILD:   "for this server",
    Scope.CHANNEL: "for this channel",
    Scope.USER:    "for you",
}

_SCOPE_TITLE: dict[Scope, str] = {
    Scope.GUILD:   "Server settings",
    Scope.CHANNEL: "Channel settings",
    Scope.USER:    "Your settings",
}


async def _ac_value(ctx: lightbulb.AutocompleteContext[str]) -> None:
    key_opt = ctx.get_option("key")
    defn = _USER_KEYS.get(str(key_opt.value)) if key_opt and key_opt.value else None
    if defn is None or defn.choices is None:
        await ctx.respond([])
        return
    typed = str(ctx.focused.value or "").lower()
    await ctx.respond([c for c in defn.choices if typed in c][:25])


# ---------------------------------------------------------------------------
# Shared handler
# ---------------------------------------------------------------------------

def _make_reset_menu(
    svc: ConfigService,
    key: str,
    scope: Scope,
    scope_id: int,
    caller_id: int,
) -> lightbulb.components.Menu:
    menu = lightbulb.components.Menu()

    async def on_reset(mctx: lightbulb.components.MenuContext) -> None:
        if mctx.user.id != caller_id:
            await mctx.respond("This button isn't for you.", ephemeral=True)
            return
        async with async_session() as session:
            await svc.reset_value(session, key, scope, scope_id)
        await mctx.respond(
            f"**{key}** has been reset to its default {_SCOPE_LABEL[scope]}.",
            edit=True,
            components=[],
        )
        mctx.stop_interacting()

    menu.add_interactive_button(hikari.ButtonStyle.DANGER, on_reset, label="Reset to default")
    return menu


async def _handle(
    ctx: lightbulb.Context,
    svc: ConfigService,
    scope: Scope,
    scope_id: int,
    key: hikari.UndefinedOr[str],
    value: hikari.UndefinedOr[str],
) -> None:
    color = _SCOPE_COLOR[scope]
    label = _SCOPE_LABEL[scope]

    if key is hikari.UNDEFINED:
        async with async_session() as session:
            all_vals = await svc.all_at_scope(session, scope, scope_id)
        # The query returns whatever is in the DB, so the filter goes on the
        # render -- an owner key written before it was marked one still shows up.
        visible = {k: v for k, v in all_vals.items() if k in _USER_KEYS}
        desc = "\n".join(f"**{k}**: `{v}`" for k, v in sorted(visible.items())) or f"*Nothing customized {label} yet.*"
        embed = hikari.Embed(title=_SCOPE_TITLE[scope], description=desc, color=color)
        await ctx.respond(embed=embed, ephemeral=True)
        return

    defn = _USER_KEYS.get(key)
    if defn is None:
        await ctx.respond(f"Unknown setting: `{key}`", ephemeral=True)
        return
    if scope not in defn.settable_scopes:
        await ctx.respond(f"**{key}** can't be configured {label}.", ephemeral=True)
        return

    if value is hikari.UNDEFINED:
        async with async_session() as session:
            current = await svc.get_at_scope(session, key, scope, scope_id)
        if current is None:
            display = f"*Not set — using the default:* `{defn.default}`"
        else:
            display = f"`{current}` *(default: `{defn.default}`)*"
        embed = (
            hikari.Embed(title=defn.description or key, color=color)
            .add_field("Current value", display)
            .add_field("Applies", label)
        )
        menu = _make_reset_menu(svc, key, scope, scope_id, int(ctx.user.id))
        await ctx.respond(embed=embed, components=menu, ephemeral=True)
        menu.attach_persistent(ctx.client, timeout=60)
        return

    try:
        parsed = parse_value(defn, value)
    except ValueError as err:
        await ctx.respond(str(err), ephemeral=True)
        return

    async with async_session() as session:
        await svc.set_value(session, key, scope, scope_id, parsed, int(ctx.user.id))
    embed = (
        hikari.Embed(title="Saved!", color=color)
        .add_field(defn.description or key, f"`{parsed}`")
        .add_field("Applies", label)
    )
    await ctx.respond(embed=embed, ephemeral=True)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

@loader.command
@config_group.register
class ConfigUser(
    lightbulb.SlashCommand,
    name="user",
    description="Your personal preferences",
):
    key: hikari.UndefinedOr[str] = lightbulb.string(
        "key", "Setting to view or change", default=hikari.UNDEFINED, choices=_KEYS_USER
    )
    value: hikari.UndefinedOr[str] = lightbulb.string(
        "value", "New value", default=hikari.UNDEFINED, autocomplete=_ac_value,
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context, svc: ConfigService) -> None:
        await _handle(ctx, svc, Scope.USER, int(ctx.user.id), self.key, self.value)


@loader.command
@config_group.register
class ConfigChannel(
    lightbulb.SlashCommand,
    name="channel",
    description="Config for this channel (requires Manage Channels)",
):
    key: hikari.UndefinedOr[str] = lightbulb.string(
        "key", "Setting to view or change", default=hikari.UNDEFINED, choices=_KEYS_CHANNEL
    )
    value: hikari.UndefinedOr[str] = lightbulb.string(
        "value", "New value", default=hikari.UNDEFINED, autocomplete=_ac_value
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context, svc: ConfigService) -> None:
        if ctx.guild_id is None:
            await ctx.respond("This command only works inside a server.", ephemeral=True)
            return
        if not (ctx.member and ctx.member.permissions & hikari.Permissions.MANAGE_CHANNELS):
            await ctx.respond("You need the **Manage Channels** permission to configure this channel.", ephemeral=True)
            return
        await _handle(ctx, svc, Scope.CHANNEL, int(ctx.channel_id), self.key, self.value)


@loader.command
@config_group.register
class ConfigServer(
    lightbulb.SlashCommand,
    name="server",
    description="Config for this server (requires Manage Server)",
):
    key: hikari.UndefinedOr[str] = lightbulb.string(
        "key", "Setting to view or change", default=hikari.UNDEFINED, choices=_KEYS_GUILD
    )
    value: hikari.UndefinedOr[str] = lightbulb.string(
        "value", "New value", default=hikari.UNDEFINED, autocomplete=_ac_value
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context, svc: ConfigService) -> None:
        if ctx.guild_id is None:
            await ctx.respond("This command only works inside a server.", ephemeral=True)
            return
        if not (ctx.member and ctx.member.permissions & hikari.Permissions.MANAGE_GUILD):
            await ctx.respond("You need the **Manage Server** permission to configure this server.", ephemeral=True)
            return
        await _handle(ctx, svc, Scope.GUILD, int(ctx.guild_id), self.key, self.value)


@loader.command
@config_group.register
class ConfigView(
    lightbulb.SlashCommand,
    name="view",
    description="Show resolved config for this context",
):
    key: str = lightbulb.string("key", "Setting to inspect, or 'all'", choices=_KEYS_VIEW)

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context, svc: ConfigService) -> None:
        is_dm = ctx.guild_id is None
        guild_id = int(ctx.guild_id) if ctx.guild_id is not None else None
        channel_id = int(ctx.channel_id)
        user_id = int(ctx.user.id)

        scope_id_map: dict[Scope, int] = {Scope.GLOBAL: GLOBAL_SCOPE_ID, Scope.USER: user_id}
        if not is_dm:
            if guild_id is not None:
                scope_id_map[Scope.GUILD] = guild_id
            scope_id_map[Scope.CHANNEL] = channel_id

        single_key = None if self.key == "all" else self.key
        if single_key is not None and single_key not in _USER_KEYS:
            await ctx.respond(f"Unknown setting: `{single_key}`", ephemeral=True)
            return
        keys_to_show = {single_key: _USER_KEYS[single_key]} if single_key else _USER_KEYS

        # resolved_src per key, used for color when viewing a single key
        resolved_srcs: dict[str, Scope | None] = {}
        lines: list[str] = []
        async with async_session() as session:
            for key, defn in keys_to_show.items():
                chain = defn.dm_chain if is_dm else defn.guild_chain
                conditions = [
                    (ConfigValue.scope == s.value) & (ConfigValue.scope_id == scope_id_map[s])
                    for s in chain
                    if s in scope_id_map
                ]
                by_scope: dict[str, Any] = {}
                if conditions:
                    result = await session.execute(
                        select(ConfigValue)
                        .where(ConfigValue.key == key)
                        .where(or_(*conditions))
                    )
                    by_scope = {row.scope: row.value["v"] for row in result.scalars()}

                resolved_val: Any = defn.default
                resolved_src: Scope | None = None
                for s in chain:
                    if s.value in by_scope:
                        resolved_val = by_scope[s.value]
                        resolved_src = s
                        break

                resolved_srcs[key] = resolved_src
                # A value inherited from the bot-wide row IS the default as far
                # as this surface is concerned -- the global scope has no
                # user-facing name and nothing here can write it.
                src_label = (
                    "default"
                    if resolved_src is None or resolved_src is Scope.GLOBAL
                    else resolved_src.value
                )
                lines.append(f"**{key}**: `{resolved_val}` *(from {src_label})*")

        src = resolved_srcs.get(single_key) if single_key else None
        color = _SCOPE_COLOR.get(src, _NEUTRAL_COLOR) if src else _NEUTRAL_COLOR

        context_label = "DM" if is_dm else f"server `{guild_id}`, channel `{channel_id}`"
        embed = hikari.Embed(
            title="Effective config",
            description="\n".join(lines) if lines else "No config keys defined.",
            color=color,
        ).set_footer(text=f"Context: {context_label}")
        await ctx.respond(embed=embed, ephemeral=True)


loader.command(config_group)
