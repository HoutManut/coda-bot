"""Where live score updates are allowed to post, and where each user wants theirs.

Two tables rather than settings ``REGISTRY`` keys, for two reasons:

* ``/config`` exposes every registered key as a settable primitive, so a
  channel-id key would let any user type any channel ID straight past the guild
  allowlist.
* The allowlist is a *set* per guild, which the scalar ``(key, scope, scope_id)``
  config table cannot represent.

A user's stored channel is validated against the allowlist at post time, not
just at set time. An admin removing a channel therefore drops its followers back
to DM on its own -- no cleanup job, and no stored flag that could leak.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from coda.db.base import Base


class LiveUpdateChannel(Base):
    """A channel a guild's admins permit live score updates in."""

    __tablename__ = "live_update_channels"
    __table_args__ = (UniqueConstraint("guild_id", "channel_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    added_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LiveUpdatePref(Base):
    """One Discord user's live-update preference."""

    __tablename__ = "live_update_prefs"

    discord_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # NULL = direct messages, the default. Otherwise a channel that was in some
    # guild's allowlist when chosen -- re-checked at post time, since an admin
    # may have removed it since.
    channel_id: Mapped[int | None] = mapped_column(BigInteger)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
