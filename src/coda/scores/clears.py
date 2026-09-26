"""The reviewable slice of a potential pool, and the override that answers it.

A tier-1 row's clear status is a heuristic guess, and only some guesses are
worth asking about: one on a chart's resolved-best row that is currently inside
the counted pool. A buried row asks nothing of anyone, and a wire-confirmed one
is not the owner's to state (``d-clear-bonus-impossible-friend-path``).

This is the only module that writes ``play_scores.clear_override``.
"""

from __future__ import annotations

import logging
from typing import Literal

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from coda.db.models import PlayScore
from coda.scores.potential import PotentialEntry, PotentialResult
from coda.utils.scoring import ClearBasis

logger = logging.getLogger(__name__)

# `unconfirmed` is the queue proper. `all` also lists rows already answered,
# which is the only way back to a correction: setting an override removes the
# row from the queue, so without this mode an answer would be a one-way door.
type ReviewMode = Literal["unconfirmed", "all"]

_REVIEWABLE: dict[ReviewMode, tuple[ClearBasis, ...]] = {
    "unconfirmed": (ClearBasis.ASSUMED,),
    "all": (ClearBasis.ASSUMED, ClearBasis.OVERRIDE),
}


def reviewable(result: PotentialResult, mode: ReviewMode) -> list[PotentialEntry]:
    """The counted entries whose clear status is the owner's to state."""
    return [
        entry
        for entry in result.entries
        if entry.counted and entry.clear.basis in _REVIEWABLE[mode]
    ]


async def set_clear_override(
    db: AsyncSession, account_id: int, play_score_id: int, cleared: bool
) -> None:
    """Record the owner's answer for one stored play."""
    await _write(db, account_id, {cleared: [play_score_id]})


async def accept_assumptions(
    db: AsyncSession, account_id: int, entries: list[PotentialEntry]
) -> None:
    """Promote each entry's assumed status to an explicit answer.

    Numerically a no-op -- it writes back the value the heuristic already
    produced. The point is that the rows stop being questions.
    """
    by_answer: dict[bool, list[int]] = {True: [], False: []}
    for entry in entries:
        by_answer[entry.clear.cleared].append(entry.play_score_id)
    await _write(db, account_id, by_answer)


async def _write(
    db: AsyncSession, account_id: int, by_answer: dict[bool, list[int]]
) -> None:
    """One UPDATE per distinct answer, scoped to the account that owns the rows."""
    for cleared, play_score_ids in by_answer.items():
        if not play_score_ids:
            continue
        await db.execute(
            update(PlayScore)
            .where(
                PlayScore.id.in_(play_score_ids),
                PlayScore.arcaea_account_id == account_id,
            )
            .values(clear_override=cleared)
        )
        logger.info(
            "clears: account %s marked %s play(s) %s",
            account_id,
            len(play_score_ids),
            "cleared" if cleared else "failed",
        )
    await db.commit()
