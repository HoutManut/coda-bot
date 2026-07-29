"""Context-menu (user + message) command scaffolds."""

from __future__ import annotations

import lightbulb

loader = lightbulb.Loader()


@loader.command
class ArcaeaProfileUser(
    lightbulb.UserCommand,
    name="Arcaea Profile",
):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        # self.target is the right-clicked hikari.User.
        # TODO: inject RegistrationService and look up their linked friend code.
        target = self.target
        await ctx.respond(
            f"Arcaea Profile for {target.mention} — coming soon.", ephemeral=True
        )


@loader.command
class ReadScoreMessage(
    lightbulb.MessageCommand,
    name="Read Arcaea Score",
):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        # self.target is the right-clicked hikari.Message.
        # TODO: parse a friend code / song name out of target.content.
        target = self.target
        await ctx.respond(
            f"Got message ({len(target.content)} chars) — coming soon.", ephemeral=True
        )
