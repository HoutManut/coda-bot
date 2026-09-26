"""Which poll key covers an account -- own path if it can, else friend.

Lifted out of ``/recent`` when tournaments became the second caller. It is the
only place that answers "how do we reach this player", and it answers with an
opaque ``PollKey``, so no caller learns what a ``bot_account_id`` is.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from coda.db.models import ArcaeaAccount, PlayerCredential
from coda.scores.keys import OWN, PollKey
from coda.sessions.pool import SessionPool


async def poll_key_for(db: AsyncSession, account: ArcaeaAccount) -> PollKey | None:
    """Which path to poll this account on.

    None means neither is available (strayed, or the friend slot was released),
    which is a plain error: there is nothing to refresh.
    """
    if not account.is_active:
        return None
    credential = await db.scalar(
        select(PlayerCredential.id).where(
            PlayerCredential.arcaea_account_id == account.id,
            PlayerCredential.is_valid.is_(True),
        )
    )
    if credential is not None:
        return (OWN, account.id)
    return SessionPool(db).poll_key(account)


async def poll_keys_for(
    db: AsyncSession, account_ids: Iterable[int]
) -> set[PollKey]:
    """The keys covering these accounts, skipping any that cannot be reached.

    Deduped: several players on one bot account collapse to one friend key,
    which is exactly the batching the friend path exists for.
    """
    ids = set(account_ids)
    if not ids:
        return set()
    rows = await db.execute(
        select(ArcaeaAccount).where(ArcaeaAccount.id.in_(ids))
    )
    keys = set()
    for account in rows.scalars():
        key = await poll_key_for(db, account)
        if key is not None:
            keys.add(key)
    return keys
