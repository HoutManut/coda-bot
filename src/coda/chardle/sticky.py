"""The daily scoreboard message in a guild's Chardle channel.

Discord-facing, so it sits beside the services rather than inside them — the
same split that keeps ``SessionService`` DB-only and ``transport.py`` REST-only.

Not a repost-on-scroll sticky: Discord has no such primitive, and a
delete-and-repost loop would fight the free-play boards sharing the channel. One
message per puzzle number, edited in place. Yesterday's is left where it is.
"""

from __future__ import annotations

import logging

import hikari
from hikari.impl import MessageActionRowBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from coda.chardle import render, scoreboard
from coda.chardle.channels import ChardleChannelService
from coda.db.models import ChardlePuzzle
from coda.settings import ConfigService

logger = logging.getLogger(__name__)

# Stateless by contract: the scoreboard outlives restarts, so a lightbulb Menu
# (which dies with its timeout) cannot carry this button.
PLAY_BUTTON_ID = "chardle:daily"


def play_row() -> MessageActionRowBuilder:
    row = MessageActionRowBuilder()
    row.add_interactive_button(
        hikari.ButtonStyle.PRIMARY,
        PLAY_BUTTON_ID,
        label="Play today's Chardle",
        emoji="▶️",
    )
    return row


async def refresh(
    app: hikari.RESTAware,
    db: AsyncSession,
    channels: ChardleChannelService,
    settings: ConfigService,
    *,
    guild_id: int,
    puzzle: ChardlePuzzle,
) -> None:
    """Bring this guild's scoreboard up to date. No channel set, no scoreboard."""
    home = await channels.get(db, guild_id)
    if home is None:
        return

    view = await scoreboard.build(db, settings, guild_id=guild_id, puzzle=puzzle)
    embed, _ = render.scoreboard(view)

    if home.scoreboard_puzzle_number == puzzle.puzzle_number and (
        home.scoreboard_message_id is not None
    ):
        try:
            await app.rest.edit_message(
                home.channel_id,
                home.scoreboard_message_id,
                embed=embed,
                components=[play_row()],
            )
            return
        except hikari.HikariError:
            # Deleted, or the channel went away. Post a new one rather than let
            # a missing message freeze the board for the rest of the day.
            logger.info("chardle: scoreboard %s is gone", home.scoreboard_message_id)

    try:
        message = await app.rest.create_message(
            home.channel_id, embed=embed, components=[play_row()]
        )
    except hikari.HikariError:
        logger.info("chardle: cannot post a scoreboard in %s", home.channel_id)
        return
    await channels.remember_sticky(
        db, guild_id, int(message.id), puzzle.puzzle_number
    )
