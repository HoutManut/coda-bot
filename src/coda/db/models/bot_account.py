"""BotAccount -- a lowiro account the bot logs into to read other players' scores.

Hand-created, unreplaceable, and capped at ~10 friends each
(``arcaea-auth-behavior.md`` §7.2). There are roughly five rows here and there
always will be; see ``arcaea-api-layer.md`` §6 before adding pool machinery.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from coda.db.base import Base


class BotAccount(Base):
    __tablename__ = "bot_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    password_enc: Mapped[str] = mapped_column(String, nullable=False)

    # This account's own 9-digit code, from /me's user_code at seed time.
    # Stored so registration can reject someone trying to register a bot as if
    # it were a player -- which the API would happily allow, wasting a friend
    # slot and creating a bot-watching-bot row. Nullable: a row inserted by hand
    # may not have it, and the reserved-code check simply skips those.
    friend_code: Mapped[str | None] = mapped_column(String(9), unique=True)

    # False = do not use. Set on a 403 from login (bad credentials, terminal --
    # never retried, since retrying a 403 is a login storm).
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    # HINTS ONLY -- never trust these for a capacity decision. max_friend is
    # per-account and mutable (10 on a fresh account, +5 with play, hard max 25),
    # so refresh both from the live /webapi/user/me at add time.
    friend_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    max_friends: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10, server_default="10"
    )

    # One fixed, self-consistent Chrome header set (UA + sec-ch-ua triplet) this
    # account impersonates for its whole life -- see coda.arcaea.identity. A real
    # browser does not change build between requests, and a UA that contradicts
    # its client hints flags harder than no spoofing. Assigned once at seed time;
    # nullable so a hand-inserted row falls back to the default identity.
    browser_identity: Mapped[dict | None] = mapped_column(JSONB)

    # {"sid": "<raw cookie value>"}. Opaque -- stored verbatim, never parsed or
    # rebuilt. Never pickled.
    cookie_data: Mapped[dict | None] = mapped_column(JSONB)
    # Login +30d, non-sliding. An optimization for proactive refresh only:
    # error_code 203 is the authoritative "session is dead" signal, and the
    # server can invalidate out-of-band. Never assume a non-expired sid is valid.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
