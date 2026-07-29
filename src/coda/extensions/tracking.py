"""/tracking -- whether the bot records this account's plays.

Owner-only, because the switch is per ACCOUNT: several Discord users can link
one Arcaea account through the consent flow, and the one with ``is_owner`` is
who speaks for it. A co-linked user sees the state but cannot change it.

Called with no option it reports; with ``state`` it sets. Off stops new plays
being recorded -- it does not delete stored plays, does not unregister, and does
not stop the account being fetched, so ``/recent`` keeps working.
"""

from __future__ import annotations

import logging

import hikari
import lightbulb

from coda.db.session import async_session
from coda.scores import TrackingService

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()

_COLOR_OK = 0x57F287
_COLOR_ERR = 0xED4245

_ON = "on"
_OFF = "off"

_NOT_REGISTERED = "You're not registered yet -- run `/register` first."
_NOT_OWNER = (
    "Only the owner of this Arcaea account can change tracking. You're linked "
    "to it, but someone else registered it first."
)
_ON_BLURB = "New plays are being recorded."
_OFF_BLURB = (
    "New plays will **not** be recorded. Your stored plays are kept, and "
    "`/recent` still works -- it just shows what the game reports without "
    "saving it."
)


def _embed(title: str, description: str, *, ok: bool = True) -> hikari.Embed:
    return hikari.Embed(
        title=title, description=description, color=_COLOR_OK if ok else _COLOR_ERR
    )


@loader.command
class Tracking(
    lightbulb.SlashCommand,
    name="tracking",
    description="Whether the bot records your plays",
):
    state: hikari.UndefinedOr[str] = lightbulb.string(
        "state",
        "Turn recording on or off",
        default=hikari.UNDEFINED,
        choices=[
            lightbulb.Choice(name="on", value=_ON),
            lightbulb.Choice(name="off", value=_OFF),
        ],
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context, svc: TrackingService) -> None:
        async with async_session() as db:
            link = await svc.link_of(db, int(ctx.user.id))
            if link is None:
                await ctx.respond(_NOT_REGISTERED, ephemeral=True)
                return
            account = await svc.account_of(db, link)

            if self.state is hikari.UNDEFINED:
                await ctx.respond(_status(account.tracking_enabled), ephemeral=True)
                return

            if not link.is_owner:
                await ctx.respond(_embed("Nope", _NOT_OWNER, ok=False), ephemeral=True)
                return

            enabled = self.state == _ON
            if enabled == account.tracking_enabled:
                await ctx.respond(_status(enabled), ephemeral=True)
                return
            await svc.set_enabled(db, account, enabled)

        await ctx.respond(
            _embed(
                "Tracking on" if enabled else "Tracking off",
                _ON_BLURB if enabled else _OFF_BLURB,
            ),
            ephemeral=True,
        )


def _status(enabled: bool) -> hikari.Embed:
    return _embed(
        f"Tracking is **{_ON if enabled else _OFF}**",
        _ON_BLURB if enabled else _OFF_BLURB,
    )
