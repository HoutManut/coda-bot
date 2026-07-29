"""Whether an account's plays get recorded at all.

Per ACCOUNT, not per Discord user: several Discord users can link one Arcaea
account through the consent flow, and they would otherwise fight over one
switch. So the flag lives on ``arcaea_accounts`` and only the link with
``is_owner`` may move it -- the same link that already speaks for the account
everywhere else (approvals, notifications).

Turning it off stops new plays reaching ``play_scores``. It deletes nothing,
releases no friend slot and does not unregister: history is kept precisely
because there is no backfill to recover it from.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from coda.db.models import ArcaeaAccount, PlayerLink

logger = logging.getLogger(__name__)


class TrackingService:
    """Stateless; takes the session per call, like LiveUpdateService."""

    async def link_of(self, db: AsyncSession, discord_id: int) -> PlayerLink | None:
        """This Discord user's one link, or None if they are not registered."""
        row = await db.execute(
            select(PlayerLink).where(PlayerLink.discord_id == discord_id)
        )
        return row.scalar_one_or_none()

    async def account_of(self, db: AsyncSession, link: PlayerLink) -> ArcaeaAccount:
        """The account a link points at. The FK guarantees it exists."""
        row = await db.execute(
            select(ArcaeaAccount).where(ArcaeaAccount.id == link.arcaea_account_id)
        )
        return row.scalar_one()

    async def set_enabled(
        self, db: AsyncSession, account: ArcaeaAccount, enabled: bool
    ) -> None:
        account.tracking_enabled = enabled
        await db.commit()
        logger.info("tracking: account %s -> %s", account.id, "on" if enabled else "off")
