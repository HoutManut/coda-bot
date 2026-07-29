"""Answer pools. A tier is a set of difficulty classes plus what the board
reveals about them — nothing more; level windows arrive as puzzle filters.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from coda.db.enums import DifficultyClass
from coda.db.models import SongDifficulty

# The joke is dated. Outside the April window it exists only as a rare surprise.
ERR_AMBIENT_CHANCE = 0.003
ERR_EVENT_CHANCE = 0.25

DAILY_ATTEMPTS = 6
ERR_ATTEMPT_CAP = 6

# Free play runs wider pools than the daily and shares one pool between everyone
# in the channel, so it gets more room. There is no unbounded board.
FREE_ATTEMPTS = 8
MAX_FREE_ATTEMPTS = 12


@dataclass(frozen=True)
class Tier:
    name: str
    label: str
    classes: frozenset[DifficultyClass]
    include_hidden: bool = False
    allow_sentinels: bool = False
    # What the picker calls this tier, when that has to differ from what the
    # board prints. extras is the only case: the dropdown must say which classes
    # it merges, the board must not.
    choice_name: str | None = None

    @property
    def pick_label(self) -> str:
        return self.choice_name or self.label


TIERS: dict[str, Tier] = {
    "pst": Tier("pst", "Past", frozenset({DifficultyClass.PST})),
    "prs": Tier("prs", "Present", frozenset({DifficultyClass.PRS})),
    "ftr": Tier("ftr", "Future", frozenset({DifficultyClass.FTR})),
    "etr": Tier("etr", "Eternal", frozenset({DifficultyClass.ETR})),
    # BYD_2 is a storage slot, not a class: both of Last's Beyonds belong to the
    # Beyond pool. See wiki h-chardle-extra-pool-hides-class.
    "byd": Tier(
        "byd",
        "Beyond",
        frozenset({DifficultyClass.BYD, DifficultyClass.BYD_2}),
    ),
    "extras": Tier(
        "extras",
        "Eternal + Beyond",
        frozenset(
            {DifficultyClass.BYD, DifficultyClass.BYD_2, DifficultyClass.ETR}
        ),
        choice_name="Eternal + Beyond",
    ),
    "err": Tier(
        "err",
        "Error",
        frozenset({DifficultyClass.ERR}),
        include_hidden=True,
        allow_sentinels=True,
    ),
}

DEFAULT_TIER = "ftr"
ERR_TIER = "err"

# Deliberately absent from the ordinary daily rotation: err is dated.
_DAILY_WEIGHTS: dict[str, float] = {
    "ftr": 0.55,
    "extras": 0.2,
    "prs": 0.15,
    "pst": 0.1,
}


def get(name: str) -> Tier:
    return TIERS[name]


def playable_names() -> list[str]:
    """Tiers a player may pick on ``/chardle play``.

    ``byd`` and ``etr`` are offered alone here but never as a daily: each is thin
    enough to repeat fast, which is why ``extras`` merges them for the rotation.

    ``err`` is included as **testing scaffolding** — the only way to exercise the
    April Fools mode out of season. Delete this one line before the joke is meant
    to land. See wiki ``h-chardle-err-is-an-event``.
    """
    return ["pst", "prs", "ftr", "byd", "etr", "extras", "err"]


def roll_daily_tier(rng: random.Random) -> str:
    names = list(_DAILY_WEIGHTS)
    return rng.choices(names, weights=[_DAILY_WEIGHTS[n] for n in names])[0]


def roll_err(rng: random.Random, *, in_event_window: bool) -> bool:
    chance = ERR_EVENT_CHANCE if in_event_window else ERR_AMBIENT_CHANCE
    return rng.random() < chance


async def err_attempts(db: AsyncSession) -> int:
    """Attempts for an err board, derived from the live catalog.

    ``min(max(N // 2, 1), 6)``: the floor keeps a shrunken roster from producing
    a board that is lost before its first guess, and the cap keeps the joke from
    out-running the daily. Counted directly rather than through the search
    layer, which cloaks err by design.
    """
    total = await db.scalar(
        select(func.count())
        .select_from(SongDifficulty)
        .where(SongDifficulty.difficulty == DifficultyClass.ERR)
    )
    return min(max((total or 0) // 2, 1), ERR_ATTEMPT_CAP)
