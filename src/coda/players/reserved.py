"""Friend codes that are well-formed but must never be registered.

Checked after the shape validation in ``coda.utils.friend_code`` and **before any
network call** -- same reasoning as the shape check: lowiro will happily accept
these and answer with whatever it answers, and none of its replies would tell a
user anything useful. Deciding locally is what buys a real message.

Three kinds:

* **Easter eggs** -- partner codes built into the game. Not players; they have no
  scores to track.
* **The owner's code** -- anyone but an owner registering it is impersonation.
* **The bot's own accounts** -- the API would let a bot friend another bot, which
  burns a friend slot and creates a bot-watching-bot row. **This one is refused
  with a plain "you can't use that code"** (see :func:`is_bot_account`) -- no
  fake not-found and no mimicked latency: this repo is open source, so shrouding
  the pool behind a lie would fool nobody while telling a real user their code
  does not exist, which is false and unactionable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from coda.config import config
from coda.db.models import BotAccount

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ReservedCode:
    """Why a code is refused, and what to tell whoever tried."""

    reason: str
    message: str
    # True = an OWNER_IDS member may register it anyway.
    owner_may_register: bool = False


# In-game partner codes. Domain knowledge, per the project owner -- not
# derivable from the API, which has no notion of an easter egg.
_EASTER_EGGS: dict[str, ReservedCode] = {
    "000000001": ReservedCode(
        reason="easter_egg_hikari",
        message=(
            "That's **Hikari**'s code — a nice find, but she's a partner, not a "
            "player. She has no scores for me to track.\n\n"
            "Your own code is on the friends screen in-game."
        ),
    ),
    "000000002": ReservedCode(
        reason="easter_egg_tairitsu",
        message=(
            "That's **Tairitsu**'s code — a nice find, but she's a partner, not "
            "a player. She has no scores for me to track.\n\n"
            "Your own code is on the friends screen in-game."
        ),
    ),
}

_RESERVED: dict[str, ReservedCode] = dict(_EASTER_EGGS)

# The owner's code comes from env (OWNER_FRIEND_CODE unset = guard off) so the
# open-source tree does not publish it.
if config.owner_friend_code:
    _RESERVED[config.owner_friend_code] = ReservedCode(
        reason="owner_code",
        message=(
            "That's the **bot owner's** code. Nice try.\n\n"
            "If you're trying to register yourself, your own code is on the "
            "friends screen in-game."
        ),
        # The owner is not impersonating himself; let him through.
        owner_may_register=True,
    )

def check_static(code: str, discord_id: int) -> ReservedCode | None:
    """Reserved codes known without touching the DB. None = fine to proceed."""
    entry = _RESERVED.get(code)
    if entry is None:
        return None
    if entry.owner_may_register and discord_id in config.owner_ids:
        logger.info("reserved: allowing owner %s to register %s", discord_id, code)
        return None
    logger.info("reserved: refused %s for %s (%s)", code, discord_id, entry.reason)
    return entry


async def is_bot_account(db: AsyncSession, code: str) -> bool:
    """Whether the code belongs to one of our own bot accounts.

    **The caller refuses this with a plain "you can't use that code"** -- not a
    fake not-found. The old design mimicked an unknown-code 401 (same error, same
    latency) to stop /register becoming an oracle that enumerates the pool. That
    was dropped: this repo is open source, so the mechanism is public anyway, and
    the codes stay effectively unguessable at 10^9 with <50 real users -- a lie is
    a worse experience than an honest refusal.

    Bot accounts seeded before ``friend_code`` existed have it NULL and will not
    match -- re-run ``scripts/seed_bot_account.py`` to populate it.
    """
    row = await db.execute(
        select(BotAccount.id).where(BotAccount.friend_code == code).limit(1)
    )
    found = row.scalar_one_or_none() is not None
    if found:
        logger.info("reserved: %s is one of our bot accounts; refusing", code)
    return found


async def is_bot_email(db: AsyncSession, email: str) -> bool:
    """Whether this login email is one of our own bot accounts.

    Lets the credentials path refuse a bot account **before spending a login** --
    bot accounts are keyed by their unique ``email``, so no round trip is needed.
    This also catches rows seeded before ``friend_code`` existed (NULL), which the
    code-keyed :func:`is_bot_account` would miss.
    """
    row = await db.execute(
        select(BotAccount.id).where(BotAccount.email == email).limit(1)
    )
    found = row.scalar_one_or_none() is not None
    if found:
        # Do not log the email -- these lines reach shared sinks and an account
        # email is not needed to know a bot login was refused.
        logger.info("reserved: login email is one of our bot accounts; refusing")
    return found
