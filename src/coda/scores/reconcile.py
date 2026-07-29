"""Backfill ``play_scores.song_difficulty_id`` once the catalog catches up.

A play is stored even when its wire chart resolves to nothing (song shipped
in-game before the seed, or a ``song_id`` drift the seed later corrected), so its
resolved FK lands NULL. This pass re-runs ``resolve_chart`` over exactly those
NULL rows and fills the ones the catalog can now answer. It is the sole writer of
this FK after first insert -- ingest omits it from its update set -- so there is
no write contention with the poller.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from coda.catalog.chart_resolution import resolve_chart
from coda.db.models import PlayScore
from coda.db.session import async_session

logger = logging.getLogger(__name__)

# Slow cleanup pass, not a hot path.
RECONCILE_INTERVAL = 300.0


async def reconcile(db: AsyncSession) -> int:
    """Resolve every still-unresolved play; return how many were backfilled.

    NULL rows only -- never re-resolves an already-set FK. A deleted chart
    re-orphans its rows to NULL (``ondelete="SET NULL"``), so the next pass picks
    them up on its own; no separate invalidation.
    """
    rows = (
        await db.execute(select(PlayScore).where(PlayScore.song_difficulty_id.is_(None)))
    ).scalars().all()

    backfilled = 0
    for row in rows:
        sd_id = await resolve_chart(db, row.wire_song_id, row.wire_difficulty)
        if sd_id is not None:
            row.song_difficulty_id = sd_id
            backfilled += 1

    await db.commit()
    return backfilled


async def run_reconcile_loop(*, interval: float = RECONCILE_INTERVAL) -> None:
    """Reconcile at startup (catch up on offline catalog changes), then forever."""
    while True:
        try:
            async with async_session() as db:
                n = await reconcile(db)
            if n:
                logger.info("reconcile: backfilled %d play(s)", n)
        except Exception:
            logger.exception("reconcile pass failed; retrying next interval")
        await asyncio.sleep(interval)
