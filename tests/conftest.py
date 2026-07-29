"""Test fixtures.

Every test runs inside a session that is **rolled back** at teardown and never
commits, so the tests exercise real Postgres (native enums, the partial unique
index, JSONB) without leaving a trace in the dev database.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from coda.config import config
from coda.db.models import ArcaeaAccount, PlayerLink


@pytest_asyncio.fixture
async def db() -> AsyncIterator[AsyncSession]:
    # A fresh NullPool engine per test: the app's shared pooled engine caches
    # asyncpg connections bound to their creating event loop, and pytest-asyncio
    # runs each test on its own loop -> "another operation is in progress". Nothing
    # commits, so the rollback leaves the dev DB untouched.
    engine = create_async_engine(config.database_url, poolclass=NullPool)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    session = session_maker()
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


@pytest.fixture
def make_account(db: AsyncSession):
    async def _make(arc_user_id: int, friend_code: str) -> ArcaeaAccount:
        account = ArcaeaAccount(arc_user_id=arc_user_id, friend_code=friend_code)
        db.add(account)
        await db.flush()
        return account

    return _make


@pytest.fixture
def make_link(db: AsyncSession):
    async def _make(
        discord_id: int, account: ArcaeaAccount, *, linked_via, is_owner: bool
    ) -> PlayerLink:
        link = PlayerLink(
            discord_id=discord_id,
            arcaea_account_id=account.id,
            linked_via=linked_via,
            is_owner=is_owner,
        )
        db.add(link)
        await db.flush()
        return link

    return _make
