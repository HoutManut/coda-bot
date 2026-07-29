"""Own-path sessions: one per credentialed player, for the poller.

The friend path iterates bot accounts (:meth:`SessionPool.active`); the own path
iterates players who opted in with their own login. This is that iterator, kept
in ``players/`` rather than ``sessions/`` because the terminal-403 handling ends
in a Discord DM (``notify``), which ``sessions/`` must not import.

Each yielded session is an :class:`~coda.sessions.AccountSession` over a
:class:`~coda.sessions.PlayerCredentialAdapter`, so it re-logs-in and deactivates
through the exact same core the bot path uses. On a terminal 403 the adapter has
already flipped ``is_valid=False`` (excluding the row next cycle); the caller
calls :meth:`handle_invalid` to DM the owner -- once.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

import hikari
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from coda.db.models import ArcaeaAccount, PlayerCredential
from coda.players.notify import notify_credential_invalid
from coda.sessions import AccountSession, PlayerCredentialAdapter

logger = logging.getLogger(__name__)


class PlayerSessionProvider:
    """Hands out own-path sessions and owns their terminal-failure notification.

    Takes the DB session per instance (like the services) and the hikari app so
    it can DM on a dead credential.
    """

    def __init__(self, db: AsyncSession, app: hikari.RESTAware) -> None:
        self._db = db
        self._app = app

    async def poll_sessions(
        self,
    ) -> AsyncIterator[tuple[ArcaeaAccount, AccountSession]]:
        """Yield ``(account, session)`` for every pollable own-path player.

        Only ``is_valid`` credentials on ``is_active`` accounts: an invalid one
        is a terminal 403 that must never be retried, and a strayed account is
        paused. The caller drives ``session.call`` and, on
        :class:`~coda.arcaea.errors.InvalidCredentials`, calls
        :meth:`handle_invalid`.
        """
        rows = await self._db.execute(self._pollable())
        for account, credential in rows.all():
            yield account, AccountSession(PlayerCredentialAdapter(credential), self._db)

    async def session_for(
        self, arcaea_account_id: int
    ) -> tuple[ArcaeaAccount, AccountSession] | None:
        """One pollable player's ``(account, session)``, or None.

        Same filter as :meth:`poll_sessions` -- an invalid credential or a
        strayed account yields None rather than a session, so a targeted
        refresh can never revive what the sweep deliberately skips.
        """
        row = await self._db.execute(
            self._pollable().where(ArcaeaAccount.id == arcaea_account_id)
        )
        pair = row.first()
        if pair is None:
            return None
        account, credential = pair
        return account, AccountSession(PlayerCredentialAdapter(credential), self._db)

    def _pollable(self) -> Select[tuple[ArcaeaAccount, PlayerCredential]]:
        """Accounts with a usable own-path login: valid credential, not strayed."""
        return (
            select(ArcaeaAccount, PlayerCredential)
            .join(
                PlayerCredential,
                PlayerCredential.arcaea_account_id == ArcaeaAccount.id,
            )
            .where(PlayerCredential.is_valid.is_(True))
            .where(ArcaeaAccount.is_active.is_(True))
        )

    async def handle_invalid(self, account: ArcaeaAccount) -> None:
        """Notify after a session raised ``InvalidCredentials`` for ``account``.

        The credential is already ``is_valid=False`` (the adapter flipped it on
        the terminal 403), so it drops out of the next ``poll_sessions`` -- this
        just tells the owner. Safe to call once per terminal failure.
        """
        await notify_credential_invalid(self._db, self._app, account.id)
