"""Async engine and session factory, built once from config.

App code depends on :data:`async_session` (an ``async_sessionmaker``); it never
constructs engines itself, so connection settings live in exactly one place.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from coda.config import config

engine: AsyncEngine = create_async_engine(config.database_url)

async_session: async_sessionmaker = async_sessionmaker(
    engine, expire_on_commit=False
)
