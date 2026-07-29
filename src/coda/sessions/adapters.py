"""Account adapters -- what :class:`~coda.sessions.session.AccountSession` needs
from a stored login, minus the storage shape.

Two account rows drive the same login lifecycle (203-once retry, proactive
refresh, terminal-403 deactivation) but differ in three places: a bot account
holds its email in plaintext while a player credential encrypts it, the "unusable"
flag is ``BotAccount.is_active`` versus ``PlayerCredential.is_valid``, and only a
bot account carries ``last_refreshed_at``. Each adapter absorbs exactly those
differences so the session core stays single-sourced.

Decryption lives here, not in the session: the session only ever sees a ready
``email``/``password``, so it never imports :mod:`coda.crypto` and never learns
which fields were encrypted.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from coda.crypto import decrypt
from coda.db import async_session
from coda.db.models import BotAccount, PlayerCredential


async def _persist(
    caller_db: AsyncSession, model: type, pk: int, obj: object, values: dict[str, Any]
) -> None:
    """Durably write session state in a transaction OF OUR OWN, then detach ``obj``.

    The session layer must never commit the caller's transaction. A re-login (or a
    terminal-403 deactivation) can fire in the MIDDLE of a service call --
    registration, a poll -- that has its own uncommitted rows pending on
    ``caller_db``; committing that session here would flush the caller's half-built
    state early. So the new sid / dead flag goes to a dedicated ``async_session``
    with its own commit, entirely independent of what the caller is doing.

    The caller updates ``obj``'s in-memory attributes BEFORE calling this, so the
    same session instance reuses the fresh sid without a re-read (pool._capacity
    makes two calls on one instance). We then expunge ``obj`` from ``caller_db`` so
    the caller's eventual commit does not re-emit the write we just made durable --
    the dedicated transaction above is the single source of this row's write.
    """
    async with async_session() as session:
        await session.execute(update(model).where(model.id == pk).values(**values))
        await session.commit()
    if obj in caller_db:
        caller_db.expunge(obj)


@runtime_checkable
class AccountAuth(Protocol):
    """The stored-login surface a session drives. Both adapters satisfy it."""

    @property
    def id(self) -> int: ...
    @property
    def email(self) -> str: ...
    @property
    def password(self) -> str: ...
    @property
    def cookie_data(self) -> dict | None: ...
    @property
    def expires_at(self) -> datetime | None: ...
    @property
    def browser_identity(self) -> dict | None: ...

    async def store_session(
        self, db: AsyncSession, sid: str, expires_at: datetime
    ) -> None:
        """Persist a freshly-issued sid and its expiry."""
        ...

    async def mark_dead(self, db: AsyncSession) -> None:
        """Flag this account unusable after a terminal 403. Never retried."""
        ...


class BotAccountAdapter:
    """A bot account: plaintext email, ``is_active`` flag, ``last_refreshed_at``."""

    def __init__(self, account: BotAccount) -> None:
        self._a = account

    @property
    def id(self) -> int:
        return self._a.id

    @property
    def email(self) -> str:
        return self._a.email

    @property
    def password(self) -> str:
        return decrypt(self._a.password_enc)

    @property
    def cookie_data(self) -> dict | None:
        return self._a.cookie_data

    @property
    def expires_at(self) -> datetime | None:
        return self._a.expires_at

    @property
    def browser_identity(self) -> dict | None:
        return self._a.browser_identity

    async def store_session(
        self, db: AsyncSession, sid: str, expires_at: datetime
    ) -> None:
        now = datetime.now(UTC)
        self._a.cookie_data = {"sid": sid}
        self._a.expires_at = expires_at
        self._a.last_login_at = now
        self._a.last_refreshed_at = now
        await _persist(
            db,
            BotAccount,
            self._a.id,
            self._a,
            {
                "cookie_data": {"sid": sid},
                "expires_at": expires_at,
                "last_login_at": now,
                "last_refreshed_at": now,
            },
        )

    async def mark_dead(self, db: AsyncSession) -> None:
        self._a.is_active = False
        await _persist(db, BotAccount, self._a.id, self._a, {"is_active": False})


class PlayerCredentialAdapter:
    """A player's own login: encrypted email, ``is_valid`` flag, no refresh stamp."""

    def __init__(self, credential: PlayerCredential) -> None:
        self._c = credential

    @property
    def id(self) -> int:
        return self._c.id

    @property
    def email(self) -> str:
        return decrypt(self._c.email_enc)

    @property
    def password(self) -> str:
        return decrypt(self._c.password_enc)

    @property
    def cookie_data(self) -> dict | None:
        return self._c.cookie_data

    @property
    def expires_at(self) -> datetime | None:
        return self._c.expires_at

    @property
    def browser_identity(self) -> dict | None:
        return self._c.browser_identity

    async def store_session(
        self, db: AsyncSession, sid: str, expires_at: datetime
    ) -> None:
        now = datetime.now(UTC)
        self._c.cookie_data = {"sid": sid}
        self._c.expires_at = expires_at
        self._c.last_login_at = now
        await _persist(
            db,
            PlayerCredential,
            self._c.id,
            self._c,
            {"cookie_data": {"sid": sid}, "expires_at": expires_at, "last_login_at": now},
        )

    async def mark_dead(self, db: AsyncSession) -> None:
        self._c.is_valid = False
        await _persist(db, PlayerCredential, self._c.id, self._c, {"is_valid": False})
