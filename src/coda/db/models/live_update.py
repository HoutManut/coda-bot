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

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Integer,
    SmallInteger,
    UniqueConstraint,
    func,
)
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

    # The guild floor: GATES only, never triggers. AND-ed with whatever the user
    # already set, so the effective bar is the stricter of the two. Intersecting
    # two TRIGGER sets could void a user's whole selection silently, which is why
    # a guild may raise the bar but never change what counts as newsworthy.
    # NULL = no floor. Level is encoded (x2, +1 for "+"); grade is a Grade
    # ordinal.
    min_level: Mapped[int | None] = mapped_column(SmallInteger)
    min_grade: Mapped[int | None] = mapped_column(SmallInteger)


class LiveUpdatePref(Base):
    """One Discord user's live-update preference."""

    __tablename__ = "live_update_prefs"

    discord_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # NULL = direct messages, the default. Otherwise a channel that was in some
    # guild's allowlist when chosen -- re-checked at post time, since an admin
    # may have removed it since.
    channel_id: Mapped[int | None] = mapped_column(BigInteger)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # --- Filters. TRIGGERS are OR-ed ("is this play worth telling someone
    # about"); GATES are AND-ed over the result ("do I care about this chart at
    # all"). OR-ing a level gate would make "10+ only" a reason to post, so a
    # level-3 PM would still post; AND-ing the triggers would make pb + pm mean
    # "a PB that is also a PM", so picking two would usually produce silence. ---
    post_all: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # The default on first enable, and what the migration hands every user who
    # was already switched on before filters existed.
    post_pb: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    post_pm: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Own-login accounts only -- the friend payload carries no lost_count, so
    # this can never fire for a friend-tier player. The command says so.
    post_fr: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # bX trigger: post when the play lands in the account's top X. NULL = off.
    best_of: Mapped[int | None] = mapped_column(SmallInteger)
    # grade_up floor, as a Grade ordinal. NULL = off.
    min_grade: Mapped[int | None] = mapped_column(SmallInteger)
    # Level gate, stored ENCODED (x2, +1 for "+"), so "10+ and above" is 21.
    min_level: Mapped[int | None] = mapped_column(SmallInteger)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
