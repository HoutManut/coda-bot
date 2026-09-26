"""Friend objects from ``GET /webapi/friend/me``."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from coda.arcaea.dto.score import ScoreResult, from_friend_wire
from coda.arcaea.errors import UnexpectedResponse

logger = logging.getLogger(__name__)

# rating is PTT x1000 (12820 = 12.820), except -1, which means the player hides
# their PTT in-game. Was x100 until lowiro's 2026-08-27 maintenance added a
# third decimal -- see wiki/domains/potential.md.
_RATING_HIDDEN = -1


@dataclass(frozen=True, slots=True)
class Friend:
    """One entry of a bot account's friends list."""

    arc_user_id: int
    name: str
    # None = hidden by the player.
    rating: float | None
    is_mutual: bool
    is_profile_public: bool
    # At most one entry, always. Empty = this player has never played.
    recent_score: ScoreResult | None


def parse_friend(raw: dict[str, Any]) -> Friend:
    """Parse one friend object."""
    arc_user_id = raw.get("user_id")
    if not isinstance(arc_user_id, int):
        raise UnexpectedResponse(f"friend object has no usable user_id: {raw!r}")

    scores = raw.get("recent_score") or []
    recent = from_friend_wire(arc_user_id, scores[0]) if scores else None

    return Friend(
        arc_user_id=arc_user_id,
        name=str(raw.get("name", "")),
        rating=_parse_rating(raw.get("rating")),
        is_mutual=bool(raw.get("is_mutual", False)),
        is_profile_public=bool(raw.get("is_profile_public", False)),
        recent_score=recent,
    )


def parse_friends(body: dict[str, Any]) -> list[Friend]:
    """Parse a validated ``GET /webapi/friend/me`` body into friends.

    Never paginates: ``max_friend`` caps at 25, so the list is structurally
    incapable of needing it -- ``value.friends`` is always complete.
    """
    value = body.get("value")
    if not isinstance(value, dict):
        raise UnexpectedResponse(f"friend/me has no value object: {body!r}")

    raw_friends = value.get("friends")
    if not isinstance(raw_friends, list):
        raise UnexpectedResponse(f"friend/me has no friends list: {value!r}")

    friends: list[Friend] = []
    for f in raw_friends:
        if not isinstance(f, dict):
            logger.warning("friend/me: dropping non-dict friend entry: %r", f, extra={'discord': True})
            continue
        try:
            friends.append(parse_friend(f))
        except UnexpectedResponse as exc:
            logger.warning("friend/me: dropping unparseable friend entry: %s", exc, extra={'discord': True})
    return friends


def _parse_rating(value: object) -> float | None:
    """PTT x1000 -> float, mapping the hidden sentinel to None."""
    if not isinstance(value, int) or value == _RATING_HIDDEN:
        return None
    if value < 0:
        logger.warning("unexpected negative rating %r, treating as hidden", value)
        return None
    return value / 1000
