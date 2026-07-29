"""Health-check command."""

from __future__ import annotations

import hikari
import lightbulb

loader = lightbulb.Loader()


@loader.command
class Ping(
    lightbulb.SlashCommand,
    name="ping",
    description="Check if the bot is alive",
):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        app = ctx.client.app
        if isinstance(app, hikari.ShardAware):
            await ctx.respond(f"Pong! `{round(app.heartbeat_latency * 1000)}ms`", flags=hikari.MessageFlag.EPHEMERAL)
        else:
            await ctx.respond("Pong!", flags=hikari.MessageFlag.EPHEMERAL)
