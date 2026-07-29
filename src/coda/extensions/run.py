"""``/run`` -- the owner terminal.

One free-text option and nothing else. Discord's picker is public: every named
option and every choice list is readable by anyone who can type ``/``, so an
owner-only capability shaped as a normal subcommand publishes its internal
parameter names to everyone it is hidden from. A single opaque box publishes
nothing, and the suggestions behind it are gated on the invoker.

Four layers, none of which replaces another: the command is created only in
``OWNER_GUILD_IDS``, ``default_member_permissions`` removes the row for
non-admins, the autocomplete refuses to suggest anything to a non-owner (this
is the one that closes the leak), and the handler refuses to act (this is the
one that matters for correctness).
"""

from __future__ import annotations

import logging

import hikari
import lightbulb

from coda.config import config
from coda.ops import ConfirmAction, dispatch, suggestions

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()

_NOT_OWNER = "This command is for the bot owner only."


def _is_owner(user_id: hikari.Snowflakeish) -> bool:
    return int(user_id) in config.owner_ids


async def _ac_cmd(ctx: lightbulb.AutocompleteContext[str]) -> None:
    """Suggestions for the owner, nothing for anyone else.

    AutocompleteContext has no ``user`` -- the invoker is on the interaction.
    """
    if not _is_owner(ctx.interaction.user.id):
        await ctx.respond([])
        return
    await ctx.respond(suggestions(str(ctx.focused.value or "")))


def _confirm_menu(action: ConfirmAction, caller_id: int) -> lightbulb.components.Menu:
    menu = lightbulb.components.Menu()

    async def on_confirm(mctx: lightbulb.components.MenuContext) -> None:
        if mctx.user.id != caller_id:
            await mctx.respond("This button isn't for you.", ephemeral=True)
            return
        await mctx.respond(await action.run(), edit=True, components=[])
        mctx.stop_interacting()

    menu.add_interactive_button(hikari.ButtonStyle.DANGER, on_confirm, label=action.label)
    return menu


class Run(
    lightbulb.SlashCommand,
    name="run",
    description="Owner operations",
    default_member_permissions=hikari.Permissions.NONE,
):
    cmd: str = lightbulb.string("cmd", "What to run", autocomplete=_ac_cmd)

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        # Never to the discord log channel: the line carries internal key names
        # and the values being set, into a channel whose read access is a
        # server setting rather than the owner list.
        logger.info(
            "/run by %s: %s", ctx.user.id, self.cmd, extra={"discord": False}
        )
        if not _is_owner(ctx.user.id):
            await ctx.respond(_NOT_OWNER, ephemeral=True)
            return

        try:
            result = await dispatch(self.cmd, invoker_id=int(ctx.user.id))
        except ValueError as err:
            await ctx.respond(f"Couldn't read that line: {err}", ephemeral=True)
            return

        if result.confirm is None:
            await ctx.respond(result.text, ephemeral=True)
            return

        menu = _confirm_menu(result.confirm, int(ctx.user.id))
        await ctx.respond(result.text, components=menu, ephemeral=True)
        menu.attach_persistent(ctx.client, timeout=60)


# Created only in the owner guilds. Passing a tuple matters: lightbulb reads
# ``guilds=None`` as "use default_enabled_guilds", so an unset env would
# publish the terminal to every dev guild instead of nowhere.
loader.command(Run, guilds=config.owner_guild_ids)

if not config.owner_guild_ids:
    logger.warning("OWNER_GUILD_IDS is empty -- /run is created in no guild")
if not config.owner_ids:
    logger.warning("OWNER_IDS is empty -- every owner gate refuses")
