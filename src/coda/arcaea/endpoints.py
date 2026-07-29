"""The endpoint catalog. Takes a sid; never logs in.

Auth is a session concern -- ``sessions/session.py`` owns acquiring, refreshing
and persisting a sid and calls through here. Each function returns the validated
raw body; parsing into DTOs is the caller's choice, so a caller that only needs
one field does not pay for a full parse.
"""

from __future__ import annotations

import logging
from typing import Any

from coda.arcaea.client import request
from coda.arcaea.dto.friend import Friend, parse_friend
from coda.arcaea.errors import raise_for_envelope

logger = logging.getLogger(__name__)


async def fetch_me(sid: str) -> dict[str, Any]:
    """``GET /webapi/user/me`` -- own profile and own recent_score.

    Carries NO friends list (lowiro removed the key). Self-validating: it is the
    auth check and the fetch at once. Heavy (3-33 KB) -- for score polling use
    :func:`fetch_friends` instead.
    """
    body = await request("GET", "/webapi/user/me", sid=sid)
    return raise_for_envelope(body)


async def fetch_friends(sid: str) -> dict[str, Any]:
    """``GET /webapi/friend/me`` -- the friends list. No params, no body.

    The polling unit is the bot ACCOUNT, not the player: this returns every
    friend in one call, so ~5 requests covers the whole user base.
    """
    body = await request("GET", "/webapi/friend/me", sid=sid)
    return raise_for_envelope(body)


async def add_friend(sid: str, friend_code: str) -> dict[str, Any]:
    """``POST /webapi/friend/me/add`` -- add by 9-digit FRIEND CODE.

    Cannot tell you the new player's ``arc_user_id``: no friend object carries a
    ``friend_code`` and no endpoint maps one to the other, so the caller must
    diff ``value.friends`` against prior state. Any design of the form
    ``add_friend(code) -> arc_user_id`` is unimplementable.

    Raises PlayerNotFound (401) for an unknown code -- a PLAYER error: do not
    flag the account and do not try the next one, since every account 401s on
    the same code. Raises AlreadyFriend (602) with no body to diff.
    """
    logger.info("add_friend %s", friend_code)
    body = await request(
        "POST", "/webapi/friend/me/add", sid=sid, form={"friend_code": friend_code}
    )
    return raise_for_envelope(body)


async def remove_friend(sid: str, friend_id: int) -> dict[str, Any]:
    """``POST /webapi/friend/me/delete`` -- remove by ``user_id``.

    NOTE THE ASYMMETRY: add takes a 9-digit friend_code, delete takes the
    arc_user_id. Passing a friend code here fails or silently no-ops.
    ``ArcaeaAccount`` stores both; use the right one.
    """
    logger.info("remove_friend user_id=%s", friend_id)
    body = await request(
        "POST", "/webapi/friend/me/delete", sid=sid, form={"friend_id": str(friend_id)}
    )
    return raise_for_envelope(body)


def unknown_friends(body: dict[str, Any], known: set[int]) -> list[Friend]:
    """Friends in an add/delete response we did not already know about.

    The only way to learn a newly added player's ``arc_user_id``: no friend
    object carries a friend_code. Returns whole Friend objects rather than bare
    ids so the caller also gets their name and PTT without a second request.

    Expect exactly one. The caller decides what an ambiguous result means -- it
    must never guess, since guessing mis-attributes a stranger's scores to a
    Discord user.

    NB the add/delete friend shape is slightly leaner than /friend/me's (no
    title, no is_profile_public), which is fine: parsing is defensive and the
    missing keys fall back to their defaults.
    """
    value = body.get("value")
    friends = value.get("friends") if isinstance(value, dict) else None
    if not isinstance(friends, list):
        return []
    parsed = [parse_friend(f) for f in friends if isinstance(f, dict)]
    return [f for f in parsed if f.arc_user_id not in known]
