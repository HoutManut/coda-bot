"""A guild's tournament channel, and the crew thread a quick match reuses.

DB-only: opening and revalidating threads lives in ``transport.py``.

The reuse key is the roster itself, sorted and deduped, so array equality is
set equality and order never matters. One extra player, one fewer, or
public-vs-private is a DIFFERENT crew and therefore a different thread.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from coda.db.enums import ThreadVisibility
from coda.db.models import TournamentChannel, TournamentThread


def roster_key(account_ids: Iterable[int]) -> list[int]:
    """The canonical form of a crew. Sorted and deduped at every boundary, so
    the unique index can do the comparing."""
    return sorted(set(account_ids))


class TournamentChannelService:
    """Stateless; takes the session per call."""

    async def get(
        self, db: AsyncSession, guild_id: int
    ) -> TournamentChannel | None:
        return await db.get(TournamentChannel, guild_id)

    async def channel_id(
        self, db: AsyncSession, guild_id: int | None
    ) -> int | None:
        """The channel every match thread in this guild hangs off, or ``None``.

        ``None`` refuses the match outright rather than opening a thread off
        whatever channel the command was typed in -- a home channel that moves
        must never strand the threads already under it.
        """
        if guild_id is None:
            return None
        row = await self.get(db, guild_id)
        return None if row is None else row.channel_id

    async def set_channel(
        self, db: AsyncSession, guild_id: int, channel_id: int, set_by: int
    ) -> None:
        """Point a guild's tournaments at a channel, replacing any previous one.

        Read-modify-write rather than ON CONFLICT: sessions are built with
        ``expire_on_commit=False``, so a core upsert would leave an already
        loaded row stale in the identity map.
        """
        row = await self.get(db, guild_id)
        if row is None:
            db.add(
                TournamentChannel(
                    guild_id=guild_id, channel_id=channel_id, set_by=set_by)
            )
        else:
            row.channel_id = channel_id
            row.set_by = set_by
        await db.commit()

    async def clear(self, db: AsyncSession, guild_id: int) -> bool:
        row = await self.get(db, guild_id)
        if row is None:
            return False
        await db.delete(row)
        await db.commit()
        return True

    async def crew_thread(
        self,
        db: AsyncSession,
        guild_id: int,
        account_ids: Iterable[int],
        visibility: ThreadVisibility,
    ) -> int | None:
        """The thread this exact crew last used, if any."""
        return await db.scalar(
            select(TournamentThread.thread_id).where(
                TournamentThread.guild_id == guild_id,
                TournamentThread.roster_key == roster_key(account_ids),
                TournamentThread.visibility == visibility,
            )
        )

    async def remember_crew(
        self,
        db: AsyncSession,
        guild_id: int,
        account_ids: Iterable[int],
        visibility: ThreadVisibility,
        thread_id: int,
    ) -> None:
        """Bind a crew to its thread.

        Written at roster FREEZE, not at creation: the roster can still grow
        while a match is drafting, and the key has to name the crew that
        actually played rather than the one that opened the room.
        """
        await db.execute(
            insert(TournamentThread)
            .values(
                guild_id=guild_id,
                roster_key=roster_key(account_ids),
                visibility=visibility,
                thread_id=thread_id,
            )
            .on_conflict_do_update(
                constraint="uq_tournament_threads_key",
                # Set explicitly: the model's onupdate is an ORM-level hook and
                # a core INSERT ... ON CONFLICT never fires it.
                set_={"thread_id": thread_id, "updated_at": func.now()},
            )
        )
        await db.commit()

    async def forget_thread(self, db: AsyncSession, thread_id: int) -> None:
        """Drop every crew bound to a thread that no longer works."""
        await db.execute(
            delete(TournamentThread).where(
                TournamentThread.thread_id == thread_id)
        )
        await db.commit()
