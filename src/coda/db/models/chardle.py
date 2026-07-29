"""Chardle — puzzles, sessions, guesses.

A mode is a shape of rows, not a column: ``puzzle_number IS NOT NULL`` is a
daily, ``channel_id`` vs ``discord_id`` is free play vs daily. The constraints
here are load-bearing — they are what stops a channel board pointing at a daily
puzzle and farming its stats.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from coda.db.base import Base
from coda.db.enums import ChardleState, chardle_state_type


class ChardlePuzzle(Base):
    """One answer chart plus the clue columns frozen onto it.

    The answer is stored, never re-derived: a ``hash(date) % len(songs)`` scheme
    would let an admin catalog edit silently rewrite yesterday's daily.
    """

    __tablename__ = "chardle_puzzles"
    __table_args__ = (
        # Only reason this exists: it lets chardle_sessions reach is_daily
        # through a composite FK, which is what makes the ownership CHECK
        # checkable across the two tables.
        UniqueConstraint("id", "is_daily", name="uq_chardle_puzzles_id_daily"),
        CheckConstraint(
            "puzzle_number IS NULL OR filters IS NULL",
            name="ck_chardle_puzzles_daily_unfiltered",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # RESTRICT, not CASCADE: a puzzle is a historical record, and cascading a
    # song deletion into it would rewrite a past daily and orphan the streaks
    # derived from it. The admin editor fails loudly instead.
    song_difficulty_id: Mapped[int] = mapped_column(
        ForeignKey("song_difficulties.id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
    )
    # Membership only. Render order is a canonical constant, so two boards on
    # one puzzle agree column-for-column.
    clue_columns: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    max_attempts: Mapped[int | None] = mapped_column(SmallInteger)
    puzzle_number: Mapped[int | None] = mapped_column(Integer, unique=True)
    is_daily: Mapped[bool] = mapped_column(
        Boolean, Computed("puzzle_number IS NOT NULL", persisted=True), nullable=False
    )
    tier: Mapped[str] = mapped_column(String, nullable=False)
    # none_as_null: without it a Python None persists as JSON 'null', which is
    # not SQL NULL, and ck_chardle_puzzles_daily_unfiltered rejects every daily.
    filters: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ChardleSession(Base):
    """One player's (or one channel's) attempt at a puzzle."""

    __tablename__ = "chardle_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["puzzle_id", "is_daily"],
            ["chardle_puzzles.id", "chardle_puzzles.is_daily"],
            ondelete="CASCADE",
            name="fk_chardle_sessions_puzzle",
        ),
        # user-owned <=> daily. An equivalence, not a xor: it also forbids a
        # channel board from pointing at a daily puzzle, which would dodge
        # uq_chardle_sessions_daily_player and let a channel co-op the daily.
        CheckConstraint(
            "(discord_id IS NOT NULL) = is_daily "
            "AND (channel_id IS NOT NULL) = (NOT is_daily)",
            name="ck_chardle_sessions_owner",
        ),
        CheckConstraint(
            "channel_id IS NULL OR channel_id = board_channel_id",
            name="ck_chardle_sessions_board_in_owner",
        ),
        UniqueConstraint(
            "puzzle_id", "discord_id", name="uq_chardle_sessions_daily_player"
        ),
        # One live free-play board per channel -- in a DM, one per user. Daily
        # sessions carry channel_id IS NULL and never contend, so several people
        # can run the daily from the same channel.
        Index(
            "uq_chardle_sessions_channel_live",
            "channel_id",
            unique=True,
            postgresql_where=text("state = 'playing'"),
        ),
        Index("ix_chardle_sessions_board", "board_channel_id", "message_id"),
        Index("ix_chardle_sessions_player", "discord_id", "state"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    puzzle_id: Mapped[int] = mapped_column(Integer, nullable=False)
    discord_id: Mapped[int | None] = mapped_column(BigInteger)
    # OWNERSHIP (free play only), as opposed to board_channel_id below.
    channel_id: Mapped[int | None] = mapped_column(BigInteger)
    # TRANSPORT: the private thread, DM, or channel the board message lives in.
    board_channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_daily: Mapped[bool] = mapped_column(Boolean, nullable=False)
    guild_id: Mapped[int | None] = mapped_column(BigInteger)
    state: Mapped[ChardleState] = mapped_column(
        chardle_state_type, nullable=False, server_default="playing"
    )
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChardleChannel(Base):
    """A guild's dedicated Chardle channel, and the sticky scoreboard in it.

    ``guild_id`` is the PK, not a ``(guild_id, channel_id)`` unique: unlike the
    live-update allowlist this is a single destination, because the scoreboard
    needs exactly one place to live and "threads go under it" means nothing if
    there are several. Setting it again replaces the row.

    Not a settings ``REGISTRY`` key, for the reason live_update.py gives:
    ``/config`` exposes every key as a freely-settable primitive, so a channel-id
    key would let any member point Chardle anywhere. The sticky pointer is bot
    state rather than config and rides along here, 1:1 with the channel.
    """

    __tablename__ = "chardle_channels"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    scoreboard_message_id: Mapped[int | None] = mapped_column(BigInteger)
    # Which daily that message renders. A mismatch is what makes the next
    # refresh post a fresh board instead of editing yesterday's.
    scoreboard_puzzle_number: Mapped[int | None] = mapped_column(Integer)
    set_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    set_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ChardlePlayerThread(Base):
    """The daily board thread reused for one player in one guild.

    Stored rather than inferred from the player's most recent session: that
    inference could not tell a thread under the Chardle channel from one under
    any other channel, and it lost the thread entirely whenever the session
    history did not line up.
    """

    __tablename__ = "chardle_player_threads"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    discord_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    thread_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ChardleGuess(Base):
    """One guess on a board. Feedback is recomputed from the catalog, never stored."""

    __tablename__ = "chardle_guesses"
    __table_args__ = (
        UniqueConstraint("session_id", "ordinal", name="uq_chardle_guesses_ordinal"),
        # Duplicate rejection in the schema, and doubling as the cursor for
        # ambiguity cycling: "next candidate not already on this board".
        UniqueConstraint(
            "session_id", "song_difficulty_id", name="uq_chardle_guesses_chart"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("chardle_sessions.id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    song_difficulty_id: Mapped[int] = mapped_column(
        ForeignKey("song_difficulties.id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
    )
    discord_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
