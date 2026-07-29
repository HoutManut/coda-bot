"""ScoreResult -- one score, from either path.

One type with nullable extras rather than a Raw/Resolved split: the extras are
absent on the friend path as a property of *the endpoint*, not of the user, so
a credentialed user read through a bot's friend list still yields tier-1 data.
That makes the nullability intrinsic rather than a modelling compromise.

Vocabulary translation happens here and stops here: the wire's
``perfect``/``near``/``miss`` become **pure/far/lost**, which is what the rest of
the codebase uses.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from coda.arcaea.dto.enums import ClearType, GaugeModifier

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ScoreResult:
    """A single play.

    ``song_id`` and ``difficulty`` are kept as the RAW wire values, always.
    Mapping them to a catalog row needs a DB lookup, which the DTO layer may not
    do, so ``difficulty_id`` is populated by the caller and stays None until then.
    An unresolvable chart is routine (a song ships in-game before our catalog is
    seeded) -- never a reason to drop the score.
    """

    arc_user_id: int
    song_id: str
    difficulty: int
    score: int
    time_played: int  # ms since epoch, UTC, assigned SERVER-side at submission.

    # FK -> song_difficulties.id. None = not resolved yet, or unknown chart.
    difficulty_id: int | None = None

    # Own-credentials path only; all None on the friend path.
    pure_count: int | None = None
    far_count: int | None = None
    lost_count: int | None = None
    shiny_pure_count: int | None = None
    health: int | None = None
    clear_type: ClearType | None = None
    modifier: GaugeModifier | None = None
    play_id: str | None = None  # Stable per-play id; tier 2+ dedup key.

    @property
    def is_hard_loss(self) -> bool:
        """A hard-gauge failure: the only play that submits before song length.

        Needs BOTH fields, so it is unanswerable on the friend path and returns
        False there -- which is why r10 is impossible on the friend path.
        """
        return self.clear_type is ClearType.TRACK_LOST and self.modifier is GaugeModifier.HARD


def from_friend_wire(arc_user_id: int, raw: dict[str, Any]) -> ScoreResult:
    """Parse a ``friends[].recent_score[]`` entry (tier 1: five fields)."""
    return ScoreResult(
        arc_user_id=arc_user_id,
        song_id=str(raw.get("song_id", "")),
        difficulty=_int_or_zero(raw.get("difficulty")),
        score=_int_or_zero(raw.get("score")),
        time_played=_int_or_zero(raw.get("time_played")),
    )


def from_own_wire(arc_user_id: int, raw: dict[str, Any]) -> ScoreResult:
    """Parse a ``/webapi/user/me`` ``recent_score[]`` entry (tier 2+: full detail)."""
    return ScoreResult(
        arc_user_id=arc_user_id,
        song_id=str(raw.get("song_id", "")),
        difficulty=_int_or_zero(raw.get("difficulty")),
        score=_int_or_zero(raw.get("score")),
        time_played=_int_or_zero(raw.get("time_played")),

        pure_count=_opt_int(raw.get("perfect_count")),
        far_count=_opt_int(raw.get("near_count")),
        lost_count=_opt_int(raw.get("miss_count")),
        shiny_pure_count=_opt_int(raw.get("shiny_perfect_count")),
        health=_opt_int(raw.get("health")),
        clear_type=ClearType.from_wire(raw.get("clear_type")),
        modifier=GaugeModifier.from_wire(raw.get("modifier")),
        play_id=str(raw["id"]) if raw.get("id") is not None else None,
    )


def _int_or_zero(value: object) -> int:
    """Coerce a required numeric field, defaulting to 0.

    score: 0 is a REAL score, so a falsy score must never be read as missing --
    which is exactly why this returns 0 rather than None and callers never test
    truthiness on it.
    """
    return value if isinstance(value, int) else 0


def _opt_int(value: object) -> int | None:
    return value if isinstance(value, int) else None
