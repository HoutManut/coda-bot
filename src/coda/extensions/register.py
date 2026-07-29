"""/register -- link a Discord user to an Arcaea account.

Two methods, both collecting input through a modal:

* ``code`` (the default) -- a friend code. A bot account friends the player and
  reads their scores from its friends list.
* ``account`` -- the player's own lowiro login. Entirely optional; it buys
  per-play detail the friend endpoint cannot return for anyone.

Credentials go through a modal because a slash option is visible in the command
bar as it is typed. A friend code uses one too, for the same reason.

The ``account`` path explains itself and waits for a button *before* opening the
modal: a modal has no room for prose.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

import hikari
import lightbulb
from sqlalchemy import delete

from coda.approvals import ApprovalService
from coda.arcaea.errors import ArcaeaError, InvalidCredentials
from coda.db.models import PlayerLink
from coda.db.session import async_session
from coda.players import (
    AccountClaimed,
    AlreadyLinkedElsewhere,
    AlreadyRegistered,
    AmbiguousFriend,
    PlayerUnreachable,
    RegistrationService,
    ReservedCodeError,
)
from coda.players.link_approval import request_link
from coda.players.live import LiveUpdateService
from coda.players.service import (
    LeftShared,
    NeedsApproval,
    NotLinked,
    ProvenCoexists,
    ProvenOverCode,
    Registration,
    Strayed,
)
from coda.sessions import NoCapacity
from coda.utils.dm import send_dm
from coda.utils.friend_code import InvalidFriendCode

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()

# Must cover the user typing AND the work inside on_submit: attach() only sets
# its "done" event after on_submit returns, and that wait sits inside the
# timeout. The 30s default would expire during a login round trip.
_MODAL_TIMEOUT = 300.0
_CONSENT_TIMEOUT = 120.0

_COLOR_OK = 0x57F287
_COLOR_ERR = 0xED4245
_COLOR_INFO = 0x5865F2

# The friend path is not a lesser tier of access: /webapi/friend/me returns five
# fields for everyone, so this detail is unreachable without the player's own
# login. That is a property of the endpoint, not of the user -- which is exactly
# why linking is worth offering, and why it must stay optional.
_LINK_BENEFITS = (
    "**This is optional.** A friend code alone is enough for the bot to track "
    "your scores, you never need to link your login.\n\n"
    "Linking adds, for every play:\n"
    "• **Note breakdown**: pure / far / lost, and shiny pure\n"
    "• **Clear type** and the RR for the play\n\n"
    "**B30** works either way, but linking, especially with an active "
    "Arcaea Online subscription, makes it and your rating far "
    "more reliable to track.\n\n"
    "Your email and password are **encrypted before they're stored** and are "
    "used only to read your own scores. You can remove them any time with "
    "`/unlink` — your scores keep tracking without them."
)

_TOS_NOTICE = (
    "\n\n**Before you continue:** coda-bot is unofficial and reads an "
    "undocumented, private Arcaea API. Using it and linking your login "
    "means accepting that this breaks Arcaea's Terms of Service. See the "
    "project README for the full disclosure. By linking, you accept this risk."
)

_ACCOUNT_METHOD_BLOCKED = (
    "\n\n**Account linking is temporarily disabled.** The host is running a "
    "long testing session using only bot accounts. Use `/register` with the "
    "friend code method for now."
)


def _error_message(exc: Exception) -> str:
    """Map a failure to something the user can actually act on."""
    match exc:
        case ReservedCodeError():
            return exc.user_message
        case AccountClaimed():
            return (
                f"**{exc.friend_code}** is already registered by someone else "
                f"(<@{exc.claimed_by}>).\n\n"
                "If that account is yours, link it with `/register method:account` "
                "— logging in proves it's yours, which a friend code can't. "
                "Otherwise, ask an admin."
            )
        case InvalidFriendCode():
            return (
                "That doesn't look like a friend code."
            )
        case PlayerUnreachable():
            return (
                "Arcaea doesn't recognize that friend code. Double-check the "
                "digits and try again."
            )
        case AlreadyRegistered():
            return "You've already registered that account."
        case AlreadyLinkedElsewhere():
            name = exc.display_name or exc.friend_code
            return (
                f"You're already linked to **{name}** (`{exc.friend_code}`), and "
                "you can only have one account linked at a time.\n\n"
                "To change accounts, run `/unregister` first, then "
                "register the new one."
            )
        case AmbiguousFriend():
            return (
                "Something's out of sync on our side and I can't tell which "
                "account is yours. A bot admin needs to look. There's nothing "
                "wrong with your code."
            )
        case NoCapacity():
            return (
                "Cannot add by friend code anymore at the moment. "
                "I have notified the bot owner about this, please try again at a later time."
            )
        case InvalidCredentials():
            return (
                "Arcaea rejected that email or password. "
                "Check them and try again."
            )
        case ArcaeaError():
            return "Arcaea's API returned something unexpected. Please try again shortly."
        case _:
            return "Something went wrong. Please try again."


async def _respond_error(ctx: lightbulb.components.ModalContext, exc: Exception) -> None:
    await ctx.respond(
        embed=hikari.Embed(
            title="Couldn't register", description=_error_message(exc), color=_COLOR_ERR
        ),
        ephemeral=True,
    )


def _welcome_embed(
    name: str | None, rating: float | None, *, channel_enable: bool
) -> hikari.Embed:
    """The in-channel welcome after a successful registration (either path).
    """
    embed = hikari.Embed(
        title=f"Welcome, {name}!" if name else "Welcome!",
        description=(
            "Your Arcaea account is linked."
        ),
        color=_COLOR_OK,
    )
    if rating is not None:
        embed.add_field(name="Potential", value=f"{rating:.2f}", inline=True)
    embed.add_field(
        name="Tracking",
        value=(
            "**On** by default. Every play gets recorded. Turn it off with "
            "`/tracking off` any time."
        ),
        inline=False,
    )
    live_value = (
        "Currently **off** by default. Enable them for this channel with the "
        "button below, or `/liveupdates channel` to pick somewhere else "
        "(including your DMs)."
        if channel_enable
        else "Currently **off** by default. Turn them on with `/liveupdates on` "
        "(defaults to your DMs), or `/liveupdates channel` to pick an allowed "
        "channel."
    )
    embed.add_field(name="Live updates", value=live_value, inline=False)
    return embed


async def _send_welcome(
    ctx: lightbulb.components.ModalContext,
    live: LiveUpdateService,
    name: str | None,
    rating: float | None,
) -> None:
    """Send the welcome embed, attaching an "enable here" button when the
    invoking channel is already allowlisted for live updates.

    Most users never leave the channel they registered in to run
    `/liveupdates channel`, so the one-click path is worth the extra round
    trip; elsewhere the embed just points at the commands.
    """
    channel_id = int(ctx.channel_id)
    async with async_session() as db:
        allowed = await live.is_allowed(db, channel_id)

    embed = _welcome_embed(name, rating, channel_enable=allowed)

    if not allowed:
        await ctx.respond(embed=embed, ephemeral=True)
        return

    caller_id = ctx.user.id
    menu = lightbulb.components.Menu()

    async def on_enable(mctx: lightbulb.components.MenuContext) -> None:
        if mctx.user.id != caller_id:
            await mctx.respond("This button isn't for you.", ephemeral=True)
            return
        async with async_session() as db:
            await live.set_destination(db, caller_id, channel_id)
            await live.set_enabled(db, caller_id, True)
        await mctx.respond(
            f"Live updates are on, posting in <#{channel_id}>.",
            edit=True,
            components=[],
        )
        mctx.stop_interacting()

    menu.add_interactive_button(
        hikari.ButtonStyle.SUCCESS, on_enable, label="Enable live updates here"
    )
    await ctx.respond(embed=embed, components=menu, ephemeral=True)
    try:
        await menu.attach(ctx.client, timeout=_CONSENT_TIMEOUT)
    except asyncio.TimeoutError:
        logger.debug("welcome live-update button timed out for %s", caller_id)


def _info_embed(text: str) -> hikari.Embed:
    """A neutral ephemeral reply -- e.g. an approval request went out."""
    return hikari.Embed(title="Registration", description=text, color=_COLOR_INFO)


def _linked_name(
    result: Registration | ProvenOverCode | ProvenCoexists,
) -> str:
    account = result.account
    if isinstance(result, Registration):
        return result.display_name or account.friend_code
    return account.display_name or account.friend_code


def _linked_rating(result: Registration | ProvenOverCode | ProvenCoexists) -> float | None:
    """Potential shows only when we just learned it (a fresh Registration
    carries it -- the proven-coexist path is an already-known account)."""
    return result.rating if isinstance(result, Registration) else None


def _coexist_notice_embed(account) -> hikari.Embed:
    """DMed to the existing owner when a second login coexists on their account."""
    name = account.display_name or account.friend_code
    return hikari.Embed(
        title="Another login was added to your account",
        description=(
            f"Someone else just linked **{name}** with their own Arcaea login. You "
            "both have access and nothing about your own link changed. If that "
            "wasn't expected, contact an admin."
        ),
        color=_COLOR_INFO,
    )


def _stale_prompt_embed(result: ProvenOverCode) -> hikari.Embed:
    """Shown to the proven user: keep or remove the demoted code-linkers."""
    others = ", ".join(f"<@{link.discord_id}>" for link in result.demoted)
    return hikari.Embed(
        title="You now own this account",
        description=(
            f"Linked **{_linked_name(result)}**. And because you proved ownership "
            "by logging in, you're now its owner.\n\n"
            f"{others} had linked it by friend code without proving it. Keep their "
            "access, or remove it?"
        ),
        color=_COLOR_OK,
    )


def _link_removed_embed(account) -> hikari.Embed:
    """DMed to a code-linker whose link the new owner chose to remove."""
    name = account.display_name or account.friend_code
    return hikari.Embed(
        title="Your link was removed",
        description=(
            f"Your friend-code link to **{name}** was removed by the account's owner "
            "(they proved ownership by logging in). If this account is really yours, "
            "link it with `/register method:account`."
        ),
        color=_COLOR_ERR,
    )


def _unregister_confirm_embed(name: str, friend_code: str) -> hikari.Embed:
    """Shown before unregistering: destructive, so it names the account and confirms."""
    return hikari.Embed(
        title="Unregister this account?",
        description=(
            f"You're linked to **{name}** (`{friend_code}`).\n\n"
            "Unregistering stops score tracking and removes any stored login. "
            "**Your score history is kept**, you can relink the same friend code later "
            "and it comes back. Continue?"
        ),
        color=_COLOR_ERR,
    )


def _unregistered_embed(
    outcome: Strayed | LeftShared | NotLinked, name: str
) -> hikari.Embed:
    """The reply after confirming an unregister."""
    match outcome:
        case Strayed() | LeftShared():
            desc = (
                f"Unregistered **{name}**. Your link is removed. Your history is "
                "kept."
            )
        case NotLinked():
            desc = "You don't have an Arcaea account linked."
    return hikari.Embed(title="Unregistered", description=desc, color=_COLOR_OK)


class _CodeModal(lightbulb.components.Modal):
    """Collects a friend code and registers it."""

    def __init__(
        self, svc: RegistrationService, approvals: ApprovalService, live: LiveUpdateService
    ) -> None:
        self._svc = svc
        self._approvals = approvals
        self._live = live
        self.code = self.add_short_text_input(
            "Friend code",
            placeholder="9 digits, e.g. 123456789",
            min_length=9,
            max_length=32,
        )

    async def on_submit(self, ctx: lightbulb.components.ModalContext) -> None:

        await ctx.defer(ephemeral=True)
        uid = int(ctx.user.id)

        try:
            async with async_session() as db:
                result = await self._svc.register_by_code(
                    db, uid, ctx.value_for(self.code) or ""
                )
                # Owned by someone else: no link yet -- ask the owner. request_link
                # commits or rolls back within this same session.
                if isinstance(result, NeedsApproval):
                    reply = await request_link(
                        db,
                        ctx.client.app,
                        self._approvals,
                        requester_id=uid,
                        owner_id=result.owner_id,
                        account=result.account,
                    )
                    await ctx.respond(embed=_info_embed(reply), ephemeral=True)
                    return
        except Exception as exc:
            logger.info("register by code failed for %s: %r", ctx.user.id, exc)
            await _respond_error(ctx, exc)
            return

        await _send_welcome(ctx, self._live, result.display_name, result.rating)


class _AccountModal(lightbulb.components.Modal):
    """Collects a lowiro login and links it."""

    def __init__(self, svc: RegistrationService, live: LiveUpdateService) -> None:
        self._svc = svc
        self._live = live
        self.email = self.add_short_text_input(
            "Arcaea email", placeholder="the email you log into Arcaea with"
        )
        self.password = self.add_short_text_input(
            "Arcaea password", placeholder="WARNING: this is visible"
        )

    async def on_submit(self, ctx: lightbulb.components.ModalContext) -> None:
        await ctx.defer(ephemeral=True)
        try:
            async with async_session() as db:
                result = await self._svc.register_by_credentials(
                    db,
                    int(ctx.user.id),
                    ctx.value_for(self.email) or "",
                    ctx.value_for(self.password) or "",
                )
        except Exception as exc:
            logger.info("register by credentials failed for %s: %s",
                        ctx.user.id, type(exc).__name__)
            await _respond_error(ctx, exc)
            return

        # Proving ownership over prior code-linkers: offer to keep or remove them.
        if isinstance(result, ProvenOverCode):
            await self._resolve_stale_links(ctx, result)
            return

        # A second proven login coexisting: tell the existing owner, no gate.
        # Sent before the welcome reply -- that reply's button wait shouldn't
        # delay notifying the other owner.
        if isinstance(result, ProvenCoexists):
            await send_dm(
                ctx.client.app, result.owner_id, embed=_coexist_notice_embed(
                    result.account)
            )

        await _send_welcome(ctx, self._live, _linked_name(result), _linked_rating(result))

    async def _resolve_stale_links(
        self, ctx: lightbulb.components.ModalContext, result: ProvenOverCode
    ) -> None:
        """Let the new owner keep or remove the demoted code links. Timeout = keep."""
        # Capture ids as plain values: the ORM rows are detached once the session
        # that produced them closed.
        demoted = [(link.id, link.discord_id) for link in result.demoted]
        account = result.account
        caller_id = ctx.user.id
        menu = lightbulb.components.Menu()

        async def on_keep(mctx: lightbulb.components.MenuContext) -> None:
            if mctx.user.id != caller_id:
                await mctx.respond("This button isn't for you.", ephemeral=True)
                return
            await mctx.respond(
                "Kept their link, you both have access to this account.",
                edit=True,
                components=[],
            )
            mctx.stop_interacting()

        async def on_remove(mctx: lightbulb.components.MenuContext) -> None:
            if mctx.user.id != caller_id:
                await mctx.respond("This button isn't for you.", ephemeral=True)
                return
            async with async_session() as db:
                await db.execute(
                    delete(PlayerLink).where(
                        PlayerLink.id.in_([link_id for link_id, _ in demoted])
                    )
                )
                await db.commit()
            for _, discord_id in demoted:
                await send_dm(
                    mctx.client.app, discord_id, embed=_link_removed_embed(
                        account)
                )
            await mctx.respond(
                "Removed their link. Only you are linked to this account now.",
                edit=True,
                components=[],
            )
            mctx.stop_interacting()

        menu.add_interactive_button(
            hikari.ButtonStyle.SECONDARY, on_keep, label="Keep their link"
        )
        menu.add_interactive_button(
            hikari.ButtonStyle.DANGER, on_remove, label="Remove their link"
        )
        await ctx.respond(
            embed=_stale_prompt_embed(result), components=menu, ephemeral=True
        )
        try:
            await menu.attach(ctx.client, timeout=_CONSENT_TIMEOUT)
        except asyncio.TimeoutError:
            # Timeout keeps the link -- nothing to undo.
            logger.debug("stale-link menu timed out for %s", caller_id)


@loader.command
class Register(
    lightbulb.SlashCommand,
    name="register",
    description="Link your Arcaea account to the bot",
):
    method = lightbulb.string(
        "method",
        "How to link. A friend code is all you need for score tracking.",
        default="code",
        choices=[
            lightbulb.Choice(name="Friend code (recommended)", value="code"),
            lightbulb.Choice(name="Arcaea login (optional)", value="account"),
        ],
    )

    @lightbulb.invoke
    async def invoke(
        self,
        ctx: lightbulb.Context,
        client: lightbulb.Client,
        svc: RegistrationService,
        approvals: ApprovalService,
        live: LiveUpdateService,
    ) -> None:
        if self.method == "account":
            await self._consent_then_modal(ctx, client, svc, live)
            return

        modal = _CodeModal(svc, approvals, live)
        custom_id = str(uuid.uuid4())
        # A modal must be an interaction's FIRST response; it cannot follow a defer.
        await ctx.respond_with_modal(
            "Register with your friend code", custom_id, components=modal
        )
        await self._await_modal(modal, client, custom_id, ctx.user.id)

    async def _consent_then_modal(
        self,
        ctx: lightbulb.Context,
        client: lightbulb.Client,
        svc: RegistrationService,
        live: LiveUpdateService,
    ) -> None:
        menu = lightbulb.components.Menu()

        # Restore this on_continue when account linking reopens; swap the
        # button below back to disabled=False, on_continue.
        # async def on_continue(mctx: lightbulb.components.MenuContext) -> None:
        #     if mctx.user.id != ctx.user.id:
        #         await mctx.respond("This button isn't for you.", ephemeral=True)
        #         return
        #     modal = _AccountModal(svc, live)
        #     custom_id = str(uuid.uuid4())
        #     await mctx.respond_with_modal(
        #         "Link your Arcaea account", custom_id, components=modal
        #     )
        #     mctx.stop_interacting()
        #     await self._await_modal(modal, client, custom_id, ctx.user.id)

        async def on_continue(mctx: lightbulb.components.MenuContext) -> None:
            raise AssertionError("disabled button cannot be pressed")

        menu.add_interactive_button(
            hikari.ButtonStyle.PRIMARY,
            on_continue,
            label="Link my account",
            disabled=True,
        )
        await ctx.respond(
            embed=hikari.Embed(
                title="Linking your Arcaea account",
                description=_LINK_BENEFITS + _TOS_NOTICE + _ACCOUNT_METHOD_BLOCKED,
                color=_COLOR_INFO,
            ),
            components=menu,
            ephemeral=True,
        )
        # try:
        #     await menu.attach(client, timeout=_CONSENT_TIMEOUT)
        # except asyncio.TimeoutError:
        #     logger.debug("link consent timed out for %s", ctx.user.id)

    async def _await_modal(
        self,
        modal: lightbulb.components.Modal,
        client: lightbulb.Client,
        custom_id: str,
        user_id: int,
    ) -> None:
        try:
            await modal.attach(client, custom_id, timeout=_MODAL_TIMEOUT)
        except asyncio.TimeoutError:
            logger.debug("register modal timed out for %s", user_id)


@loader.command
class LinkInfo(
    lightbulb.SlashCommand,
    name="linkinfo",
    description="What linking your Arcaea login does (and why it's optional)",
):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        await ctx.respond(
            embed=hikari.Embed(
                title="Linking your Arcaea account",
                description=_LINK_BENEFITS + _ACCOUNT_METHOD_BLOCKED,
                color=_COLOR_INFO,
            ),
            ephemeral=True,
        )


@loader.command
class Unlink(
    lightbulb.SlashCommand,
    name="unlink",
    description="Remove your stored Arcaea login",
):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context, svc: RegistrationService) -> None:
        async with async_session() as db:
            removed = await svc.unlink_credentials(db, int(ctx.user.id))

        message = (
            "Your login has been deleted. Your scores keep tracking through your "
            "friend code.\n\nTo stop tracking entirely, use `/unregister` instead."
            if removed
            else "You don't have a login stored.\n\nTo remove your account "
            "entirely, use `/unregister` instead."
        )
        await ctx.respond(
            embed=hikari.Embed(
                title="Unlink", description=message, color=_COLOR_OK),
            ephemeral=True,
        )


@loader.command
class Unregister(
    lightbulb.SlashCommand,
    name="unregister",
    description="Unlink your Arcaea account",
):
    """Delete the caller's link. Distinct from /unlink, which only drops the
    stored login and keeps tier-1 tracking; this stops tracking entirely and, if
    it was the account's last link, strays the account (slot freed, sync paused,
    history kept)."""

    @lightbulb.invoke
    async def invoke(
        self,
        ctx: lightbulb.Context,
        client: lightbulb.Client,
        svc: RegistrationService,
    ) -> None:
        uid = int(ctx.user.id)
        async with async_session() as db:
            account = await svc.current_account(db, uid)

        if account is None:
            await ctx.respond(
                embed=hikari.Embed(
                    title="Unregister",
                    description="You don't have an Arcaea account linked.",
                    color=_COLOR_INFO,
                ),
                ephemeral=True,
            )
            return

        # Name it now, off the live row: the outcome's ORM row is detached once
        # its session closes, and the confirm handler runs in a fresh session.
        name = account.display_name or account.friend_code
        friend_code = account.friend_code
        menu = lightbulb.components.Menu()

        async def on_confirm(mctx: lightbulb.components.MenuContext) -> None:
            if mctx.user.id != uid:
                await mctx.respond("This button isn't for you.", ephemeral=True)
                return
            async with async_session() as db:
                outcome = await svc.unregister(db, uid)
            await mctx.respond(
                embed=_unregistered_embed(outcome, name), edit=True, components=[]
            )
            mctx.stop_interacting()

        async def on_cancel(mctx: lightbulb.components.MenuContext) -> None:
            if mctx.user.id != uid:
                await mctx.respond("This button isn't for you.", ephemeral=True)
                return
            await mctx.respond(
                "Cancelled.", edit=True, components=[]
            )
            mctx.stop_interacting()

        menu.add_interactive_button(
            hikari.ButtonStyle.DANGER, on_confirm, label="Unregister"
        )
        menu.add_interactive_button(
            hikari.ButtonStyle.SECONDARY, on_cancel, label="Cancel"
        )
        await ctx.respond(
            embed=_unregister_confirm_embed(name, friend_code),
            components=menu,
            ephemeral=True,
        )
        try:
            await menu.attach(client, timeout=_CONSENT_TIMEOUT)
        except asyncio.TimeoutError:
            logger.debug("unregister confirm timed out for %s", uid)
