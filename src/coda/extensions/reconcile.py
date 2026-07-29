"""Owner command: force a reconcile pass, e.g. right after a catalog seed."""

from __future__ import annotations

import lightbulb

from coda.config import config
from coda.db.session import async_session
from coda.scores.reconcile import reconcile

loader = lightbulb.Loader()


@loader.command
class Reconcile(
    lightbulb.SlashCommand,
    name="reconcile",
    description="Backfill chart resolution on stored plays (bot owner only)",
):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if ctx.user.id not in config.owner_ids:
            await ctx.respond("This command is for the bot owner only.", ephemeral=True)
            return
        async with async_session() as db:
            backfilled = await reconcile(db)
        await ctx.respond(
            f"Reconcile done: backfilled **{backfilled}** play(s).", ephemeral=True
        )
