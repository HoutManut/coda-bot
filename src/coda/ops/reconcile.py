"""``reconcile`` -- force a chart-resolution backfill, e.g. right after a seed."""

from __future__ import annotations

from coda.db.session import async_session
from coda.ops.types import Op, OpRequest, OpResult
from coda.scores.reconcile import reconcile

USAGE = ("`reconcile` -- backfill chart resolution on stored plays",)


async def _run(_: OpRequest) -> OpResult:
    async with async_session() as db:
        backfilled = await reconcile(db)
    return OpResult(f"Backfilled **{backfilled}** play(s).")


OP = Op(name="reconcile", summary="Backfill chart resolution", usage=USAGE, handler=_run)
