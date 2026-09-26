"""Where a match lives: resolving, reusing and opening its thread.

Discord-facing only -- nothing here touches the database. The caller owns the
crew row and is told, via ``Resolved.created``, when to bind it.

Every match runs in a thread off the guild's tournament channel. A guild with
no channel set is refused, never fallen back to the invoking channel: a home
channel that later moves must not strand the threads already under it.
"""

from __future__ import annotations

import logging
from datetime import timedelta

import hikari

logger = logging.getLogger(__name__)

# A crew thread is unarchived on demand anyway; a tournament match gets a week
# so a bracket in progress stays visible. timedelta rather than a bare number:
# hikari types this argument as "Intervalish", which reads like seconds, but an
# int reaches Discord as MINUTES.
QUICK_ARCHIVE = timedelta(days=1)
TOURNAMENT_ARCHIVE = timedelta(days=7)

NO_CHANNEL = (
    "This server has no tournament channel. An admin can set one with "
    "`/tournament channel set`, then try again."
)

NO_THREAD = (
    "I can't open a thread in the tournament channel. Give me **Create "
    "Public/Private Threads** and **Send Messages in Threads** there, then "
    "try again."
)

# The anchor a public thread hangs off. Discord only emits THREAD_CREATED for a
# public thread opened from an older message, so without this the channel shows
# nothing and the thread is undiscoverable.
ANCHOR = "**{name}**"


async def resolve(
    app: hikari.RESTAware,
    *,
    parent_channel_id: int,
    name: str,
    private: bool,
    member_ids: list[int],
    reuse_thread_id: int | None,
    archive: timedelta = QUICK_ARCHIVE,
) -> tuple[int, bool] | None:
    """``(thread_id, created)``, or ``None`` when no thread could be had.

    A remembered thread is revalidated before it is trusted; any failure falls
    through to opening a fresh one rather than writing into a thread that has
    moved, been deleted, or was never ours.
    """
    if reuse_thread_id is not None and await _reusable(
        app, reuse_thread_id, parent_channel_id
    ):
        return reuse_thread_id, False

    thread_id = await open_thread(
        app,
        parent_channel_id=parent_channel_id,
        name=name,
        private=private,
        member_ids=member_ids,
        archive=archive,
    )
    return None if thread_id is None else (thread_id, True)


async def open_thread(
    app: hikari.RESTAware,
    *,
    parent_channel_id: int,
    name: str,
    private: bool,
    member_ids: list[int],
    archive: timedelta = QUICK_ARCHIVE,
) -> int | None:
    """Open a match thread, or ``None`` if Discord refuses.

    Public threads are opened FROM an anchor message so the channel announces
    them -- that system message is the only discovery mechanism there is.
    Private threads are opened bare and announce nothing, which is the point.
    """
    try:
        if private:
            thread = await app.rest.create_thread(
                parent_channel_id,
                hikari.ChannelType.GUILD_PRIVATE_THREAD,
                name[:100],
                invitable=False,
                auto_archive_duration=archive,
            )
            for member_id in member_ids:
                await app.rest.add_thread_member(thread.id, member_id)
        else:
            anchor = await app.rest.create_message(
                parent_channel_id, ANCHOR.format(name=name)
            )
            thread = await app.rest.create_message_thread(
                parent_channel_id,
                anchor.id,
                name[:100],
                auto_archive_duration=archive,
            )
    except hikari.HikariError:
        logger.info(
            "tournaments: cannot open a thread in %s", parent_channel_id)
        return None
    return int(thread.id)


def thread_name(names: list[str], stage_label: str | None = None) -> str:
    """``alice vs bob``, ``alice +3``, ``QF1 - alice vs bob``.

    A reused crew thread is never renamed: the name IS the crew, and the crew
    is the key.
    """
    if len(names) == 2:
        body = f"{names[0]} vs {names[1]}"
    elif len(names) < 2:
        body = names[0] if names else "match"
    else:
        body = f"{names[0]} +{len(names) - 1}"
    full = f"{stage_label} - {body}" if stage_label else body
    return full[:100]


async def _reusable(
    app: hikari.RESTAware, thread_id: int, parent_channel_id: int
) -> bool:
    """Three checks, each one a way a remembered thread goes wrong."""
    try:
        channel = await app.rest.fetch_channel(thread_id)
    except hikari.HikariError:
        return False
    if not isinstance(channel, hikari.GuildThreadChannel):
        return False
    # The guild moved its tournament channel: the old thread is still a thread,
    # and still readable, but it is no longer where this guild's matches live.
    if int(channel.parent_id) != parent_channel_id:
        return False
    if not channel.is_archived:
        return True
    try:
        await app.rest.edit_channel(thread_id, archived=False)
    except hikari.HikariError:
        logger.info("tournaments: cannot unarchive thread %s", thread_id)
        return False
    return True
