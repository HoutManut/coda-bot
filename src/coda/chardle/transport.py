"""Where a board's message lives.

A daily is owned by a user but must still be posted somewhere, and never in the
open channel: private thread, else DM. There is no ephemeral leg — an
interaction token dies after 15 minutes, so an ephemeral board cannot be edited
across the hours a daily lives and has no reply path at all.

Discord-facing only: nothing here touches the database. The caller owns the
remembered-thread row and is told, via :attr:`Resolved.created`, when to write it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import hikari

logger = logging.getLogger(__name__)

THREAD_NAME = "{name}'s daily board"
FREE_THREAD_NAME = "{name}'s board"
FREE_THREAD_NAME_PRIVATE = "{name}'s private board"

NO_TRANSPORT = (
    "I can't put a private board anywhere for you. Either let me create "
    "private threads in this server, or open your DMs, then try again."
)

NO_THREAD = (
    "I can't create a thread in the Chardle channel. Give me **Create "
    "Public/Private Threads** and **Send Messages in Threads** there, or start "
    "the board with `thread: No thread`."
)


@dataclass(frozen=True)
class Destination:
    channel_id: int
    is_thread: bool


@dataclass(frozen=True)
class Resolved:
    destination: Destination
    # True when a thread was just opened, so the caller knows to remember it.
    created: bool


async def resolve_daily(
    app: hikari.RESTAware,
    *,
    user: hikari.User,
    guild_id: int | None,
    parent_channel_id: int | None,
    reuse_channel_id: int | None,
) -> Resolved | None:
    """A private thread under the guild's Chardle channel, the DM channel
    otherwise, or ``None``.

    ``parent_channel_id`` is ``None`` when the guild has set no Chardle channel.
    That is a DM, not a thread off whatever channel the command was typed in:
    threads only ever hang off the dedicated channel. Both no-parent cases have
    to return before the reuse branch, which would otherwise compare a thread's
    parent against ``None``, fail, and call ``create_thread(None, ...)``.
    """
    if guild_id is None or parent_channel_id is None:
        dm = await _dm(app, user)
        return None if dm is None else Resolved(dm, created=False)

    if reuse_channel_id is not None and await _reusable_thread(
        app, reuse_channel_id, parent_channel_id
    ):
        logger.info("chardle: reusing thread %s for %s", reuse_channel_id, user.id)
        return Resolved(Destination(reuse_channel_id, is_thread=True), created=False)
    logger.info(
        "chardle: no reusable thread for %s (remembered %s)", user.id, reuse_channel_id
    )

    thread = await _private_thread(app, parent_channel_id, user)
    if thread is not None:
        return Resolved(thread, created=True)
    dm = await _dm(app, user)
    return None if dm is None else Resolved(dm, created=False)


async def open_free_thread(
    app: hikari.RESTAware,
    parent_channel_id: int,
    user: hikari.User,
    *,
    private: bool,
) -> Destination | None:
    """A thread for a free-play board. It owns itself: a thread has its own
    channel id, so several boards can run under one channel."""
    kind = (
        hikari.ChannelType.GUILD_PRIVATE_THREAD
        if private
        else hikari.ChannelType.GUILD_PUBLIC_THREAD
    )
    name_fmt = FREE_THREAD_NAME_PRIVATE if private else FREE_THREAD_NAME
    try:
        thread = await app.rest.create_thread(
            parent_channel_id,
            kind,
            name_fmt.format(name=user.username)[:100],
            invitable=True
        )
    except hikari.HikariError:
        logger.info("chardle: no free-play thread in channel %s", parent_channel_id)
        return None
    return Destination(int(thread.id), is_thread=True)


async def _reusable_thread(
    app: hikari.RESTAware, channel_id: int, parent_channel_id: int
) -> bool:
    """Whether the remembered board channel can host today's daily.

    Three things can be wrong with it. It may not be a thread at all (an earlier
    DM fallback left a DM channel id behind, and reusing it would build a guild
    message link that resolves to nothing). It may hang off a *different* parent,
    which happens the moment a guild sets or moves its Chardle channel — reusing
    it would strand the player's boards outside it forever. And it may have
    auto-archived overnight, which is the ordinary case for a daily.
    """
    try:
        channel = await app.rest.fetch_channel(channel_id)
    except hikari.HikariError:
        return False
    if not isinstance(channel, hikari.GuildThreadChannel):
        return False
    if int(channel.parent_id) != parent_channel_id:
        return False
    if not channel.is_archived:
        return True
    try:
        await app.rest.edit_channel(channel_id, archived=False)
    except hikari.HikariError:
        logger.info("chardle: cannot unarchive thread %s", channel_id)
        return False
    return True


async def _private_thread(
    app: hikari.RESTAware, parent_channel_id: int, user: hikari.User
) -> Destination | None:
    """A private thread announces nothing in its parent channel — Discord only
    sends THREAD_CREATED for a public thread off an older message."""
    try:
        thread = await app.rest.create_thread(
            parent_channel_id,
            hikari.ChannelType.GUILD_PRIVATE_THREAD,
            THREAD_NAME.format(name=user.username)[:100],
            invitable=False,
        )
        await app.rest.add_thread_member(thread.id, user.id)
    except hikari.HikariError:
        logger.info("chardle: no private thread in channel %s", parent_channel_id)
        return None
    return Destination(int(thread.id), is_thread=True)


async def _dm(app: hikari.RESTAware, user: hikari.User) -> Destination | None:
    try:
        channel = await app.rest.create_dm_channel(user.id)
    except hikari.HikariError:
        logger.info("chardle: cannot DM %s", user.id)
        return None
    return Destination(int(channel.id), is_thread=False)
