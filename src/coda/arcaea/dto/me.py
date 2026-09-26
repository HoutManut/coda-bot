"""Own profile from ``GET /webapi/user/me``.

**This endpoint has no friends list.** lowiro removed the ``friends`` key;
friends come from ``GET /webapi/friend/me``, which is also far lighter (267 B vs
3,294 B for one friend) and is what score polling should use. Reach for /user/me
only when own-profile fields are actually needed.

It is self-validating -- 200 with a live session, 400/203 without -- so it is
both the auth check and the fetch, and there is no separate auth probe.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from coda.arcaea.dto.score import ScoreResult, from_own_wire
from coda.arcaea.errors import UnexpectedResponse

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Me:
    """The authenticated account's own profile."""

    arc_user_id: int
    name: str
    friend_code: str
    # Live capacity. Per-account and mutable: 10 on a fresh account, increasable by 5, hard max 25.
    max_friends: int
    rating: float | None
    # 0 = no Arcaea Online subscription. The tier-3 discriminator; compare
    # against now() at read time so a lapsed subscription is a non-event.
    arcaea_online_expire_ts: int
    recent_score: ScoreResult | None


def parse_me(body: dict[str, Any]) -> Me:
    """Parse a validated ``GET /webapi/user/me`` body."""
    value = body.get("value")
    if not isinstance(value, dict):
        raise UnexpectedResponse(f"user/me has no value object: {body!r}")

    arc_user_id = value.get("user_id")
    if not isinstance(arc_user_id, int):
        raise UnexpectedResponse(f"user/me has no usable user_id: {value!r}")

    scores = value.get("recent_score") or []
    recent = from_own_wire(arc_user_id, scores[0]) if scores else None

    rating = value.get("rating")
    return Me(
        arc_user_id=arc_user_id,
        name=str(value.get("name", "")),
        # The wire calls our own code "user_code"; friends' codes are never
        # exposed at all, which is why registration must diff (see endpoints).
        friend_code=str(value.get("user_code", "")),
        max_friends=value["max_friend"] if isinstance(value.get("max_friend"), int) else 10,
        # PTT x1000 (was x100 until lowiro's 2026-08-27 maintenance added a
        # third decimal); -1 means hidden, handled by the >= 0 guard below.
        rating=rating / 1000 if isinstance(rating, int) and rating >= 0 else None,
        arcaea_online_expire_ts=(
            value["arcaea_online_expire_ts"]
            if isinstance(value.get("arcaea_online_expire_ts"), int)
            else 0
        ),
        recent_score=recent,
    )
