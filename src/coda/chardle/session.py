"""Session lifecycle: opening a board, finding it again, and closing stale ones.

Ownership is a parameter, not a branch on a mode: a daily is owned by a user, a
free-play board by its channel. Where the board's message *lives* is a separate
question — see :mod:`coda.chardle.transport`.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from coda.db.enums import ChardleState
from coda.db.models import ChardlePuzzle, ChardleSession


class SessionService:
    """Holds one FIFO lock per live board; everything else takes a session."""

    def __init__(self) -> None:
        # asyncio.Lock releases waiters FIFO, so two people guessing into one
        # bounded pool serialise and the budget cannot double-count. Same shape
        # as the per-destination lock in scores/poster.py.
        self._locks: dict[int, asyncio.Lock] = {}

    def lock(self, session_id: int) -> asyncio.Lock:
        return self._locks.setdefault(session_id, asyncio.Lock())

    def release(self, session_id: int) -> None:
        self._locks.pop(session_id, None)

    async def daily_of(
        self, db: AsyncSession, puzzle_id: int, discord_id: int
    ) -> ChardleSession | None:
        return await db.scalar(
            select(ChardleSession).where(
                ChardleSession.puzzle_id == puzzle_id,
                ChardleSession.discord_id == discord_id,
            )
        )

    async def live_in_channel(
        self, db: AsyncSession, channel_id: int
    ) -> ChardleSession | None:
        return await db.scalar(
            select(ChardleSession).where(
                ChardleSession.channel_id == channel_id,
                ChardleSession.state == ChardleState.PLAYING,
            )
        )

    async def by_message(
        self, db: AsyncSession, channel_id: int, message_id: int
    ) -> ChardleSession | None:
        """The reply-path lookup: a message id identifies a board."""
        return await db.scalar(
            select(ChardleSession).where(
                ChardleSession.board_channel_id == channel_id,
                ChardleSession.message_id == message_id,
            )
        )

    async def open_daily(
        self,
        db: AsyncSession,
        puzzle: ChardlePuzzle,
        *,
        discord_id: int,
        guild_id: int | None,
        board_channel_id: int,
        message_id: int,
        expires_at: datetime,
    ) -> ChardleSession:
        return await self._open(
            db,
            puzzle,
            discord_id=discord_id,
            guild_id=guild_id,
            board_channel_id=board_channel_id,
            message_id=message_id,
            expires_at=expires_at,
        )

    async def open_free(
        self,
        db: AsyncSession,
        puzzle: ChardlePuzzle,
        *,
        channel_id: int,
        guild_id: int | None,
        message_id: int,
    ) -> ChardleSession:
        return await self._open(
            db,
            puzzle,
            channel_id=channel_id,
            guild_id=guild_id,
            board_channel_id=channel_id,
            message_id=message_id,
        )

    async def _open(
        self,
        db: AsyncSession,
        puzzle: ChardlePuzzle,
        *,
        board_channel_id: int,
        message_id: int,
        guild_id: int | None,
        discord_id: int | None = None,
        channel_id: int | None = None,
        expires_at: datetime | None = None,
    ) -> ChardleSession:
        session = ChardleSession(
            puzzle_id=puzzle.id,
            discord_id=discord_id,
            channel_id=channel_id,
            board_channel_id=board_channel_id,
            is_daily=puzzle.puzzle_number is not None,
            guild_id=guild_id,
            state=ChardleState.PLAYING,
            message_id=message_id,
            expires_at=expires_at,
        )
        db.add(session)
        await db.commit()
        return session

    async def expire_dailies_of(
        self, db: AsyncSession, discord_id: int
    ) -> None:
        """Close the caller's rolled-over dailies before serving a new one —
        otherwise a missed sweep leaves yesterday's board answering today."""
        now = datetime.now(UTC)
        rows = await db.execute(
            select(ChardleSession).where(
                ChardleSession.discord_id == discord_id,
                ChardleSession.state == ChardleState.PLAYING,
                ChardleSession.expires_at <= now,
            )
        )
        self._close(rows.scalars().all(), now)
        await db.commit()

    async def sweep(self, db: AsyncSession, abandon_hours: int) -> list[ChardleSession]:
        """Expired dailies and abandoned free-play boards, scored as losses.

        A lost board frees its channel's slot for free — the partial unique index
        only covers ``playing``.
        """
        now = datetime.now(UTC)
        cutoff = now - timedelta(hours=abandon_hours)
        rows = await db.execute(
            select(ChardleSession).where(
                ChardleSession.state == ChardleState.PLAYING,
                (ChardleSession.expires_at <= now)
                | (
                    ChardleSession.channel_id.is_not(None)
                    & (ChardleSession.started_at <= cutoff)
                ),
            )
        )
        stale = list(rows.scalars().all())
        self._close(stale, now)
        await db.commit()
        for session in stale:
            self.release(session.id)
        return stale

    async def end(self, db: AsyncSession, session: ChardleSession) -> None:
        """``/chardle end`` — give the channel its slot back.

        Does not ``release()``: the caller ends a board while holding its lock,
        and dropping the entry mid-hold would hand the next guess a fresh,
        uncontended lock. Releasing is the caller's to do, after the hold.
        """
        self._close([session], datetime.now(UTC))
        await db.commit()

    def _close(self, sessions, now: datetime) -> None:
        for session in sessions:
            session.state = ChardleState.LOST
            session.finished_at = now
