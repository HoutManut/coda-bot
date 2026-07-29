"""AccountSession -- a sid, and the one place the re-login retry lives.

This module and :mod:`coda.sessions.pool` are the only code that knows what a
sid is. Everything above asks for a session and calls through it.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from coda.arcaea import auth, identity
from coda.arcaea.errors import InvalidCredentials, SessionExpired
from coda.db.models import BotAccount
from coda.sessions.adapters import AccountAuth, BotAccountAdapter

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Re-login this long before expires_at rather than waiting for a 203. Purely an
# optimization: expiry does not slide, but the server can also invalidate
# out-of-band, so 203 remains the authoritative signal and this is never trusted.
REFRESH_MARGIN = timedelta(hours=24)


# Re-login locks, keyed by account and SHARED across sessions.
_login_locks: dict[tuple[str, int], asyncio.Lock] = {}


def _login_lock(account: AccountAuth) -> asyncio.Lock:
    """The shared re-login lock for this account. Same account -> same lock.

    ``get``-then-``set`` with no ``await`` between is atomic under asyncio's
    single-threaded scheduling, so no guard lock is needed to create one.
    """
    key = (type(account).__name__, account.id)
    lock = _login_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _login_locks[key] = lock
    return lock


class AccountSession:
    """One stored login's live session."""

    def __init__(self, account: AccountAuth, db: AsyncSession) -> None:
        self._account = account
        self._db = db
        self._lock = _login_lock(account)

    @property
    def account_id(self) -> int:
        return self._account.id

    @property
    def _identity(self) -> identity.BrowserIdentity | None:
        """This account's stored browser identity, or None to use the default."""
        return identity.coerce(self._account.browser_identity)

    async def call(
        self, fn: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any
    ) -> T:
        """Call an endpoint with this account's sid, refreshing once on 203.

        ``fn`` takes the sid as its first argument (the signature every function
        in :mod:`coda.arcaea.endpoints` has).
        """
        # bind is a sync context manager (contextvar set/reset), so it nests
        # inside the async lock rather than joining the ``async with``.
        async with self._lock:
            with identity.bind(self._identity):
                sid = await self._ensure_sid()
                try:
                    return await fn(sid, *args, **kwargs)
                except SessionExpired:

                    logger.info(
                        "session for account %s rejected; re-logging in",
                        self._account.id,
                    )
                    sid = await self._refresh()
                    return await fn(sid, *args, **kwargs)

    async def _ensure_sid(self) -> str:
        """Return a usable sid, logging in if we have none or it is near expiry."""
        cookie = self._account.cookie_data or {}
        sid = cookie.get("sid")
        if not sid:
            logger.info("account %s has no stored sid", self._account.id)
            return await self._refresh()

        expires_at = self._account.expires_at
        if expires_at is not None and expires_at - REFRESH_MARGIN <= datetime.now(UTC):
            logger.info(
                "account %s session expires %s, refreshing proactively",
                self._account.id,
                expires_at,
            )
            return await self._refresh()

        return sid

    async def _refresh(self) -> str:
        """Log in, persist the new sid, and return it.

        A 403 is terminal: credentials are wrong and will not fix themselves
        (a rotated password reaches here after its stale sid 401s), so the
        account is marked dead and the error re-raised. Never retried.
        """
        try:
            sid, expires_at = await auth.login(
                self._account.email, self._account.password
            )
        except InvalidCredentials:
            logger.error(
                "account %s: credentials rejected (403). Deactivating -- "
                "this needs a human, retrying would be a login storm",
                self._account.id,
            )
            await self._account.mark_dead(self._db)
            raise

        await self._account.store_session(self._db, sid, expires_at)
        logger.info("account %s: new session stored", self._account.id)
        return sid


class BotSession(AccountSession):
    """An :class:`AccountSession` bound to a bot account."""

    def __init__(self, account: BotAccount, db: AsyncSession) -> None:
        super().__init__(BotAccountAdapter(account), db)
