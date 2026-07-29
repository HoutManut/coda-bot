"""Request-scoped dependencies."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from coda.db.session import async_session


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield one ``AsyncSession`` per request. Handlers commit explicitly; the
    context manager rolls back and closes on exit."""
    async with async_session() as session:
        yield session
