"""Where a user's live score updates go.

Server admins allowlist channels; users choose from that allowlist. Updates
start OFF; turning them on defaults to the user's DM unless a channel is chosen.

**Resolution happens at post time, not set time.** A user's stored channel is
only honoured while it is still allowlisted, so an admin removing a channel drops
its followers back to DM by itself -- no cleanup job, and no stored "was valid"
flag that could go stale. Same reasoning as deriving tier rather than storing it.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from coda.db.models import LiveUpdateChannel, LiveUpdatePref
from coda.scores.filters import ChannelFloor

logger = logging.getLogger(__name__)

# Live updates are opt-in, separate from tracking (always on at registration).
# Flip to True to make updates opt-out (start in DM) instead -- nothing else
# needs to change.
DEFAULT_ENABLED = False


class LiveUpdateService:
    """Stateless; takes the session per call."""

    async def allowed_channels(self, db: AsyncSession, guild_id: int) -> list[int]:
        """Channel IDs this guild permits live updates in."""
        rows = await db.execute(
            select(LiveUpdateChannel.channel_id)
            .where(LiveUpdateChannel.guild_id == guild_id)
            .order_by(LiveUpdateChannel.added_at)
        )
        return list(rows.scalars())

    async def is_allowed(self, db: AsyncSession, channel_id: int) -> bool:
        """Whether any guild currently allowlists this channel."""
        row = await db.execute(
            select(LiveUpdateChannel.id)
            .where(LiveUpdateChannel.channel_id == channel_id)
            .limit(1)
        )
        return row.scalar_one_or_none() is not None

    async def allow(
        self, db: AsyncSession, guild_id: int, channel_id: int, added_by: int
    ) -> bool:
        """Allowlist a channel. False if it already was."""
        existing = await db.execute(
            select(LiveUpdateChannel.id).where(
                LiveUpdateChannel.guild_id == guild_id,
                LiveUpdateChannel.channel_id == channel_id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            return False
        db.add(
            LiveUpdateChannel(
                guild_id=guild_id, channel_id=channel_id, added_by=added_by
            )
        )
        await db.commit()
        logger.info("live: guild %s allowed channel %s", guild_id, channel_id)
        return True

    async def disallow(self, db: AsyncSession, guild_id: int, channel_id: int) -> bool:
        """Remove a channel from the allowlist. False if it was not on it.

        Users pointed at it are NOT rewritten: resolve_destination stops
        honouring it on its own, which is the whole point of checking at post
        time. If it is re-allowed later, their choice simply works again.
        """
        row = await db.execute(
            select(LiveUpdateChannel).where(
                LiveUpdateChannel.guild_id == guild_id,
                LiveUpdateChannel.channel_id == channel_id,
            )
        )
        entry = row.scalar_one_or_none()
        if entry is None:
            return False
        await db.delete(entry)
        await db.commit()
        logger.info("live: guild %s disallowed channel %s", guild_id, channel_id)
        return True

    async def floor_for(
        self, db: AsyncSession, channel_id: int
    ) -> ChannelFloor | None:
        """The guild's bar for this channel, if it set one.

        A separate read rather than widening ``resolve_destination``'s return:
        one extra indexed lookup per channel post is nothing at this scale, and
        the resolver's signature stays what the poller calls. DMs never reach
        here -- a user's own inbox is not a guild's business.
        """
        row = (
            await db.execute(
                select(LiveUpdateChannel)
                .where(LiveUpdateChannel.channel_id == channel_id)
                .limit(1)
            )
        ).scalar_one_or_none()
        return None if row is None else ChannelFloor.of(row)

    async def set_floor(
        self,
        db: AsyncSession,
        guild_id: int,
        channel_id: int,
        *,
        min_level: int | None,
        min_grade: int | None,
    ) -> bool:
        """Set a channel's floor. False if the channel is not on the allowlist."""
        row = (
            await db.execute(
                select(LiveUpdateChannel).where(
                    LiveUpdateChannel.guild_id == guild_id,
                    LiveUpdateChannel.channel_id == channel_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return False
        row.min_level = min_level
        row.min_grade = min_grade
        await db.commit()
        logger.info(
            "live: guild %s floor on channel %s -> level %s, grade %s",
            guild_id,
            channel_id,
            min_level,
            min_grade,
        )
        return True

    async def get_pref(self, db: AsyncSession, discord_id: int) -> LiveUpdatePref | None:
        row = await db.execute(
            select(LiveUpdatePref).where(LiveUpdatePref.discord_id == discord_id)
        )
        return row.scalar_one_or_none()

    async def set_destination(
        self, db: AsyncSession, discord_id: int, channel_id: int | None
    ) -> None:
        """Point a user's updates at a channel, or at their DM (None)."""
        pref = await self._upsert(db, discord_id)
        pref.channel_id = channel_id
        await db.commit()
        logger.info("live: user %s destination -> %s", discord_id, channel_id or "DM")

    async def set_enabled(self, db: AsyncSession, discord_id: int, enabled: bool) -> None:
        """Turn a user's updates on or off, keeping their chosen destination."""
        pref = await self._upsert(db, discord_id)
        pref.enabled = enabled
        await db.commit()
        logger.info("live: user %s enabled -> %s", discord_id, enabled)

    async def set_filters(
        self,
        db: AsyncSession,
        discord_id: int,
        updates: dict[str, bool | int | None],
    ) -> LiveUpdatePref:
        """Apply filter changes and return the resulting row.

        ``updates`` holds only the filters the user actually named -- omitting
        one leaves it alone, and there is no value that means "unchanged", since
        ``None`` genuinely means "off" for the three numeric filters.
        """
        pref = await self._upsert(db, discord_id)
        for column, value in updates.items():
            setattr(pref, column, value)
        await db.commit()
        logger.info("live: user %s filters -> %s", discord_id, updates)
        return pref

    async def resolve_destination(
        self, db: AsyncSession, discord_id: int
    ) -> tuple[bool, int | None]:
        """``(enabled, channel_id)`` for a user. channel_id None = DM.

        The poller's entry point. Falls back to DM whenever the stored channel
        is no longer allowlisted, so a removed channel needs no cleanup pass.
        """
        pref = await self.get_pref(db, discord_id)
        if pref is None:
            return DEFAULT_ENABLED, None
        if not pref.enabled:
            return False, None
        if pref.channel_id is None:
            return True, None
        if not await self.is_allowed(db, pref.channel_id):
            logger.info(
                "live: user %s pointed at channel %s which is no longer allowed; "
                "falling back to DM",
                discord_id,
                pref.channel_id,
            )
            return True, None
        return True, pref.channel_id

    async def _upsert(self, db: AsyncSession, discord_id: int) -> LiveUpdatePref:
        pref = await self.get_pref(db, discord_id)
        if pref is None:
            pref = LiveUpdatePref(discord_id=discord_id, enabled=DEFAULT_ENABLED)
            db.add(pref)
            await db.flush()
        return pref
