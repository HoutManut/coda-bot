"""SessionPool -- which bot account holds whom."""

from __future__ import annotations

import logging
from collections.abc import Set as AbstractSet

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from coda.arcaea import endpoints
from coda.arcaea.dto import parse_me
from coda.arcaea.errors import ArcaeaError
from coda.db.models import ArcaeaAccount, BotAccount
from coda.scores.keys import BOT, PollKey
from coda.sessions.session import BotSession

logger = logging.getLogger(__name__)


class NoCapacity(Exception):
    """Every active bot account is full. Terminal."""


class SessionPool:
    """Loads bot accounts and hands out sessions."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def active(self) -> list[BotSession]:
        """Every usable bot account's session. The polling unit.

        One /friend/me per account covers every player it holds, so this list --
        not the player list -- is what a poll iterates.
        """
        rows = await self._db.execute(
            select(BotAccount).where(BotAccount.is_active.is_(True)).order_by(BotAccount.id)
        )
        accounts = list(rows.scalars())
        logger.debug("pool: %d active bot accounts", len(accounts))
        return [BotSession(a, self._db) for a in accounts]

    async def get(self, account_id: int) -> BotSession | None:
        """One account's session, or None if it is gone or went inactive.

        The poller sweeps account-at-a-time on its own DB session, so it needs
        to re-open a session for an id it listed earlier -- the account can be
        deactivated in between, which is what the None is for.
        """
        account = await self._db.get(BotAccount, account_id)
        if account is None or not account.is_active:
            return None
        return BotSession(account, self._db)

    async def place(
        self, friend_code: str, exclude: AbstractSet[int] = frozenset()
    ) -> tuple[BotSession, set[int]]:
        """Pick an account with room for one more friend.

        Returns the session and the ``arc_user_id``s it is already known to
        hold, because the caller must diff against them to learn who was added
        -- no friend object carries a friend_code, so there is no other way.

        Capacity is read from the live /me, never from the stored hints:
        ``max_friend`` is per-account and mutable (10 to 25), so a cached
        value can be wrong in the direction that matters.

        ``exclude`` names bot-account ids to skip. It exists for the last-slot
        race: two concurrent placements can both see the same free slot, and the
        loser's add is rejected (ApiError). The caller (``_acquire``) re-enters
        ``place`` with the colliding account excluded so it falls through to the
        next one instead of failing the registration. See
        ``wiki/flows/session-lease.md``.
        """
        for session in await self.active():
            if session.account_id in exclude:
                continue
            capacity = await self._capacity(session)
            if capacity is None:
                continue
            friend_count, max_friends = capacity
            if friend_count >= max_friends:
                logger.info(
                    "pool: bot account %s full (%d/%d), trying next",
                    session.account_id,
                    friend_count,
                    max_friends,
                )
                continue

            known = await self.known_arc_user_ids(session.account_id)
            logger.info(
                "pool: placing %s on bot account %s (%d/%d used)",
                friend_code,
                session.account_id,
                friend_count,
                max_friends,
            )
            return session, known
        logger.warning("every active bot account is at its friend cap", extra={"discord": True, "ping": True})
        raise NoCapacity("every active bot account is at its friend cap")

    async def release(self, account: ArcaeaAccount) -> None:
        """Give an account's friend slot back. The inverse of ``place``.

        Called when an account strays (its last link went away). Releasing the
        slot IS pool business: ``bot_account_id`` is written only here, and live
        capacity counts friends, so the slot is not truly free until lowiro no
        longer holds the friend.

        Unfriend FIRST, NULL second.
        """
        bot_account_id = account.bot_account_id
        if bot_account_id is None:
            return

        bot_account = await self._db.get(BotAccount, bot_account_id)
        if bot_account is None:
            logger.warning(
                "pool.release: bot account %s gone; leaving %s assigned for reconcile",
                bot_account_id,
                account.friend_code,
            )
            return

        session = BotSession(bot_account, self._db)
        try:
            await session.call(endpoints.remove_friend, account.arc_user_id)
        except ArcaeaError:
            logger.exception(
                "pool.release: unfriending %s from bot account %s failed; leaving "
                "assigned for reconcile",
                account.arc_user_id,
                bot_account_id,
            )
            return

        account.bot_account_id = None
        logger.info(
            "pool.release: freed %s from bot account %s",
            account.friend_code,
            bot_account_id,
        )

    def poll_key(self, account: ArcaeaAccount) -> PollKey | None:
        """The poll key of the bot account holding this player, or None.

        A key, not the id: an on-demand refresh has to name what it wants
        polled, and this is how it does so without ``bot_account_id`` escaping
        this module. None means nobody holds them, so the friend path is
        unavailable for that player.
        """
        if account.bot_account_id is None:
            return None
        return (BOT, account.bot_account_id)

    async def known_arc_user_ids(self, bot_account_id: int) -> set[int]:
        """The arc_user_ids we believe this account holds."""
        rows = await self._db.execute(
            select(ArcaeaAccount.arc_user_id).where(
                ArcaeaAccount.bot_account_id == bot_account_id
            )
        )
        return set(rows.scalars())

    async def _capacity(self, session: BotSession) -> tuple[int, int] | None:
        """Live ``(friend_count, max_friends)``, or None if the account is unusable.

        Counts friends from /friend/me rather than trusting the stored hint --
        the two drift whenever an add or remove fails partway.
        """
        try:
            me = parse_me(await session.call(endpoints.fetch_me))
            friends = await session.call(endpoints.fetch_friends)
        except ArcaeaError:
            # A broken account must not block placement on a working one.
            logger.exception(
                "pool: bot account %s unusable, skipping", session.account_id
            )
            return None

        value = friends.get("value") or {}
        friend_count = len(value.get("friends") or [])
        return friend_count, me.max_friends
