"""The session layer persists in its OWN transaction, never the caller's.

Regression cover for the fix in ``coda.sessions.adapters``: a re-login (or a
terminal-403 deactivation) can fire in the middle of a service call that has its
own uncommitted rows pending -- a half-built registration, say. The old adapters
called ``db.commit()`` on that shared session, flushing the caller's partial state
early. ``_persist`` now writes the new sid / dead flag through a dedicated
``async_session`` with its own commit, and expunges the row so the caller's
eventual commit does not re-emit the same write.

These run against real Postgres and never commit anything durable, so the dev DB
is left untouched (like the rest of the suite).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from coda.config import config
from coda.db.models import ArcaeaAccount, BotAccount
from coda.sessions import adapters
from coda.sessions.adapters import BotAccountAdapter, _persist


@pytest_asyncio.fixture
async def persist_maker(monkeypatch) -> AsyncIterator[async_sessionmaker]:
    """Point ``_persist``'s dedicated session at a per-test NullPool engine.

    In production ``_persist`` uses the app's shared pooled ``async_session``, but
    that engine caches asyncpg connections bound to their creating event loop and
    pytest-asyncio gives each test its own loop -- the same reason ``conftest``'s
    ``db`` fixture builds its own NullPool engine. Patching the maker keeps the
    "independent connection" property while staying loop-safe.
    """
    engine = create_async_engine(config.database_url, poolclass=NullPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(adapters, "async_session", maker)
    try:
        yield maker
    finally:
        await engine.dispose()


async def test_persist_does_not_commit_caller_transaction(
    db: AsyncSession, persist_maker, make_account
) -> None:
    # A row that lives ONLY in the caller session's uncommitted transaction.
    account = await make_account(900000010, "900000010")
    assert account in db

    await _persist(
        db, ArcaeaAccount, account.id, account, {"display_name": "persisted"}
    )

    # Detached from the caller session: its later commit cannot re-emit our write.
    assert account not in db

    # And the caller's transaction was NOT committed by the session layer. A fresh
    # connection sees no such account -- it only ever existed in db's uncommitted,
    # about-to-be-rolled-back transaction. Had _persist done db.commit(), this row
    # would be durable and visible here. This is the #3 regression.
    async with persist_maker() as fresh:
        row = await fresh.execute(
            select(ArcaeaAccount).where(ArcaeaAccount.arc_user_id == 900000010)
        )
        assert row.scalar_one_or_none() is None


async def test_store_session_keeps_fresh_sid_readable_and_detaches(
    db: AsyncSession, persist_maker
) -> None:
    # A bot account attached to the caller session.
    account = BotAccount(email="persist-test@example.invalid", password_enc="x")
    db.add(account)
    await db.flush()
    assert account in db

    expires = datetime.now(UTC)
    await BotAccountAdapter(account).store_session(db, "new-sid-123", expires)

    # In-memory attrs are updated so the SAME session instance's next call reuses
    # the fresh sid without a DB re-read (pool._capacity makes two calls on one
    # instance). Reading a detached object's already-loaded attrs needs no I/O.
    assert account.cookie_data == {"sid": "new-sid-123"}
    assert account.expires_at == expires
    assert account.last_refreshed_at is not None

    # Detached, so the caller's commit won't double-write the row _persist already
    # made durable in its own transaction.
    assert account not in db
