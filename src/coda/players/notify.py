"""Tell a player their stored login stopped working.

Fired when an own-path session hits a terminal 403 -- almost always because the
account's password was changed server-side, which invalidates the stored sid
(the next authed call 401s) and then fails the re-login. The credential is
already marked ``is_valid=False`` by then, so it is skipped on the next poll and
this DM fires exactly once.

DM the **owner only**: they hold the password and are the one who can re-register.
A shared account's coexisting linkers lose own-path detail silently but keep the
friend path, so nothing they can act on is lost.
"""

from __future__ import annotations

import logging

import hikari
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from coda.db.models import PlayerLink
from coda.utils.dm import send_dm

logger = logging.getLogger(__name__)


def _invalid_embed() -> hikari.Embed:
    return hikari.Embed(
        title="Your Arcaea login stopped working",
        description=(
            "I could no longer sign in to your Arcaea account -- this usually "
            "means the password changed. Run `/register` again to reconnect.\n\n"
            "Your friend-path score updates are unaffected."
        ),
        color=0xE67E22,
    )


async def notify_credential_invalid(
    db: AsyncSession, app: hikari.RESTAware, arcaea_account_id: int
) -> None:
    """DM the owner of ``arcaea_account_id`` that their credential went invalid.

    No-op (logged) if the account has no owner link -- there is no one to tell,
    and that must never raise into a poll cycle.
    """
    row = await db.execute(
        select(PlayerLink.discord_id)
        .where(PlayerLink.arcaea_account_id == arcaea_account_id)
        .where(PlayerLink.is_owner.is_(True))
    )
    owner_id = row.scalar_one_or_none()
    if owner_id is None:
        logger.warning(
            "credential invalid for arcaea_account %s but it has no owner link; "
            "nobody to notify",
            arcaea_account_id,
        )
        return

    await send_dm(app, owner_id, embed=_invalid_embed())
    logger.info(
        "notified owner %s that arcaea_account %s credential is invalid",
        owner_id,
        arcaea_account_id,
    )
