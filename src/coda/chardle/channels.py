"""A guild's dedicated Chardle channel, its sticky scoreboard, and the daily
thread each player reuses in it.

DB-only, like every other service here: posting and editing live in
``sticky.py`` and ``transport.py``.
"""

from __future__ import annotations

import logging

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from coda.db.models import ChardleChannel, ChardlePlayerThread

logger = logging.getLogger(__name__)


class ChardleChannelService:
    """Stateless; takes the session per call."""

    async def get(self, db: AsyncSession, guild_id: int) -> ChardleChannel | None:
        return await db.get(ChardleChannel, guild_id)

    async def channel_id(self, db: AsyncSession, guild_id: int | None) -> int | None:
        """The one channel every Chardle thread in this guild hangs off, or
        ``None`` when it has set none -- which blocks threads outright rather
        than scattering them across whatever channel was used."""
        if guild_id is None:
            return None
        row = await self.get(db, guild_id)
        return None if row is None else row.channel_id

    async def configured_guilds(self, db: AsyncSession) -> list[int]:
        """Guilds with a Chardle channel, for the sweep that rolls their
        scoreboards over even when nobody has played yet."""
        rows = await db.execute(select(ChardleChannel.guild_id))
        return list(rows.scalars())

    async def set_channel(
        self, db: AsyncSession, guild_id: int, channel_id: int, set_by: int
    ) -> None:
        """Point a guild's Chardle at a channel, replacing any previous one.

        Clears the sticky pointer: yesterday's scoreboard message lives in the
        old channel and must not be edited from the new one.

        Read-modify-write rather than ON CONFLICT: sessions are built with
        ``expire_on_commit=False``, so a core upsert would leave any already
        loaded row stale in the identity map and the very next ``get`` would
        report the old channel.
        """
        row = await self.get(db, guild_id)
        if row is None:
            row = ChardleChannel(guild_id=guild_id)
            db.add(row)
        row.channel_id = channel_id
        row.set_by = set_by
        row.scoreboard_message_id = None
        row.scoreboard_puzzle_number = None
        await db.commit()
        logger.info("chardle: guild %s hosts chardle in %s", guild_id, channel_id)

    async def clear(self, db: AsyncSession, guild_id: int) -> bool:
        """Forget a guild's channel. False if it had none."""
        row = await self.get(db, guild_id)
        if row is None:
            return False
        await db.delete(row)
        await db.commit()
        logger.info("chardle: guild %s cleared its chardle channel", guild_id)
        return True

    async def remember_sticky(
        self, db: AsyncSession, guild_id: int, message_id: int, puzzle_number: int
    ) -> None:
        row = await self.get(db, guild_id)
        if row is None:
            return
        row.scoreboard_message_id = message_id
        row.scoreboard_puzzle_number = puzzle_number
        await db.commit()

    async def player_thread(
        self, db: AsyncSession, guild_id: int, discord_id: int
    ) -> int | None:
        return await db.scalar(
            select(ChardlePlayerThread.thread_id).where(
                ChardlePlayerThread.guild_id == guild_id,
                ChardlePlayerThread.discord_id == discord_id,
            )
        )

    async def remember_thread(
        self, db: AsyncSession, guild_id: int, discord_id: int, thread_id: int
    ) -> None:
        await db.execute(
            insert(ChardlePlayerThread)
            .values(guild_id=guild_id, discord_id=discord_id, thread_id=thread_id)
            .on_conflict_do_update(
                index_elements=[
                    ChardlePlayerThread.guild_id,
                    ChardlePlayerThread.discord_id,
                ],
                # Set explicitly: the model's onupdate is an ORM-level hook and a
                # core INSERT ... ON CONFLICT never fires it.
                set_={"thread_id": thread_id, "updated_at": func.now()},
            )
        )
        await db.commit()

    async def forget_thread(
        self, db: AsyncSession, guild_id: int, discord_id: int
    ) -> None:
        await db.execute(
            delete(ChardlePlayerThread).where(
                ChardlePlayerThread.guild_id == guild_id,
                ChardlePlayerThread.discord_id == discord_id,
            )
        )
        await db.commit()
