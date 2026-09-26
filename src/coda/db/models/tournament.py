"""Tournaments — the home channel, matches, their chart pool, and their rounds.

Three objects stack: a tournament decides which matches exist, a match owns
everything Discord-facing (roster, pool, pick/ban, best-of), and a round is the
only thing that touches ``play_scores`` — an eligible chart set plus a window.
A quick match is a match with ``tournament_id IS NULL``, not a second shape.

Windows are ``BigInteger`` UTC milliseconds so they compare directly against
``play_scores.time_played`` with no conversion at query time.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from coda.db.base import Base
from coda.db.enums import (
    DifficultyClass,
    MatchState,
    PoolEntryState,
    RoundState,
    ThreadVisibility,
    difficulty_class_type,
    match_state_type,
    pool_entry_state_type,
    round_state_type,
    thread_visibility_type,
)


class TournamentChannel(Base):
    """A guild's dedicated tournament channel. Every match thread hangs off it.

    A table rather than a settings ``REGISTRY`` key, for the reason
    ``chardle_channels`` gives: ``/config`` exposes every key as a
    freely-settable primitive, so a channel-id key would let any member point
    tournaments anywhere. A guild with no row is refused, never fallen back to
    the invoking channel.
    """

    __tablename__ = "tournament_channels"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    set_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    set_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TournamentMatch(Base):
    """What a thread holds and the board renders. Spawns rounds; reads no score.

    The pool filters live here rather than on the round because a pool spans
    every round of the match, and because the board has to print them while the
    match is still ``draft`` and no round exists yet.
    """

    __tablename__ = "tournament_matches"
    __table_args__ = (
        # The auto-act sweep reads this, mirroring the round table's
        # (state, end_ms) deadline sweep.
        Index("ix_tournament_matches_turn", "state", "turn_deadline_ms"),
        # Every message in a match thread resolves through this: a chat line
        # can stand in for the Ready button, so the listener looks a thread up
        # per message it does not immediately discard.
        Index("ix_tournament_matches_thread", "thread_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # NOT NULL: there is no DM leg. A bot can neither open a thread in a DM nor
    # create a group DM, so a DM room could hold neither the board nor a second
    # player. Privacy is a private thread instead.
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # The parent at creation. Thread reuse revalidates against the CURRENTLY
    # configured channel, not this -- a guild that moves its channel must
    # strand nobody.
    home_channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    thread_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    board_message_id: Mapped[int | None] = mapped_column(BigInteger)
    # The wait this match has already announced, recomputed from the match on
    # every pass so a restart says nothing twice. NULL = the match waits on
    # nobody it has to name.
    prompt_key: Mapped[str | None] = mapped_column(String(32))
    # The message that wait was announced on. Kept because no prompt is left
    # standing as an unanswered ask: when the wait ends the line is rewritten
    # into what happened, or removed where nothing happened worth reporting.
    prompt_message_id: Mapped[int | None] = mapped_column(BigInteger)
    visibility: Mapped[ThreadVisibility] = mapped_column(
        thread_visibility_type, nullable=False
    )
    # Who may PLAY, where visibility is who may READ. Off by default: a quick
    # match is an invitation to one person, and a third player arriving unasked
    # is a different match to the one those two agreed to. Only consulted while
    # the match is `draft` -- the roster freezes when it leaves.
    open_join: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # NULL = a quick match. The only difference between the two kinds.
    tournament_id: Mapped[int | None] = mapped_column(Integer)
    stage_label: Mapped[str | None] = mapped_column(String(32))
    pick_ban: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    best_of: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # NULL = "any" = song mode: a pool entry is a SONG and the round's chart set
    # is every one of its qualifying difficulties.
    difficulty_class: Mapped[DifficultyClass | None] = mapped_column(
        difficulty_class_type
    )
    # Encoded level (value*2, +1 for "+"), matching song_difficulties.level.
    # Both NULL = any level.
    level_min: Mapped[int | None] = mapped_column(SmallInteger)
    level_max: Mapped[int | None] = mapped_column(SmallInteger)
    state: Mapped[MatchState] = mapped_column(
        match_state_type, nullable=False, server_default="draft"
    )
    # Async formats only (handoff 14). NULL on a quick match, which is never
    # async: both players are already in the thread.
    play_by_ms: Mapped[int | None] = mapped_column(BigInteger)
    # Position in the pick/ban sequence; side_index = turn_index % 2.
    turn_index: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0"
    )
    turn_deadline_ms: Mapped[int | None] = mapped_column(BigInteger)
    # Attribution, not the roster -- the roster is arcaea_account_id.
    creator_discord_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # True = a server-wide event: transitions need the guild permission.
    admin_gated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TournamentThread(Base):
    """A crew's remembered quick-match thread. Tournament matches write no row.

    Stored rather than inferred from the newest match, for the reason
    ``chardle_player_threads`` exists: the inference returns nothing after any
    history gap, and cannot tell a thread under the home channel from one under
    any other.
    """

    __tablename__ = "tournament_threads"
    __table_args__ = (
        UniqueConstraint(
            "guild_id", "roster_key", "visibility", name="uq_tournament_threads_key"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Sorted and deduped arcaea_account_ids, so array equality IS set equality.
    # An array rather than a digest: it stays readable in psql and joins back to
    # arcaea_accounts when a thread has to be explained to someone.
    roster_key: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False)
    visibility: Mapped[ThreadVisibility] = mapped_column(
        thread_visibility_type, nullable=False
    )
    thread_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class TournamentPoolEntry(Base):
    """One offer in a match's chart pool, with its pick/ban state.

    An entry names a SONG always and a CHART only outside song mode, because
    ``class: any`` puts the difficulty choice in the player's hands. The
    round's resolved chart set is ``tournament_charts``, never this.
    """

    __tablename__ = "tournament_pool_entries"
    __table_args__ = (
        # Song-level, not chart-level: a pool must never offer two charts of one
        # song, and in class mode a song has at most one chart of that class.
        UniqueConstraint("match_id", "song_id", name="uq_tournament_pool_song"),
        UniqueConstraint("match_id", "ordinal", name="uq_tournament_pool_ordinal"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(
        ForeignKey("tournament_matches.id", ondelete="CASCADE"), nullable=False
    )
    song_id: Mapped[str] = mapped_column(
        ForeignKey("songs.song_id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
    )
    # NULL = song mode. RESTRICT: a pool a match was played against must not
    # silently lose a chart.
    song_difficulty_id: Mapped[int | None] = mapped_column(
        ForeignKey("song_difficulties.id", onupdate="CASCADE", ondelete="RESTRICT")
    )
    ordinal: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    state: Mapped[PoolEntryState] = mapped_column(
        pool_entry_state_type, nullable=False, server_default="available"
    )
    acted_by: Mapped[int | None] = mapped_column(
        ForeignKey("arcaea_accounts.id", ondelete="RESTRICT")
    )
    acted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The board marks these: an auto-ban reads differently from a chosen one.
    auto: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    round_id: Mapped[int | None] = mapped_column(
        ForeignKey("tournament_rounds.id", ondelete="SET NULL")
    )


class TournamentRound(Base):
    """One chart set plus one window. The only object that reads a score.

    Nothing on it knows what Discord is -- guild, channel and creator all live
    on the match.
    """

    __tablename__ = "tournament_rounds"
    __table_args__ = (
        UniqueConstraint("match_id", "ordinal", name="uq_tournament_rounds_ordinal"),
        # The cadence query and the deadline sweep both read this.
        Index("ix_tournament_rounds_deadline", "state", "end_ms"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(
        ForeignKey("tournament_matches.id", ondelete="CASCADE"), nullable=False
    )
    # 1..N in pick order, decider last.
    ordinal: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    state: Mapped[RoundState] = mapped_column(
        round_state_type, nullable=False, server_default="pending"
    )
    # Both set at the pending -> open transition, and never moved after: the
    # validity window is what makes "played inside the window" a guarantee.
    start_ms: Mapped[int | None] = mapped_column(BigInteger)
    end_ms: Mapped[int | None] = mapped_column(BigInteger)
    # Observation slack past end_ms. Polling is discrete, so a play at
    # end_ms - 1s may not be SEEN until after end_ms.
    grace_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    # When the round was actually decided. Stored rather than derived from
    # end_ms + grace_ms because grace ends the moment every score is in, so the
    # derived value is only ever the BACKSTOP -- and the break that follows is
    # measured from the real close, not from a deadline the round never spent.
    closed_ms: Mapped[int | None] = mapped_column(BigInteger)
    # When each of the round's two thread beats was posted -- the chart being
    # revealed, and the round being decided. NULL means the beat is still owed,
    # which is what makes announcing restart-safe: the sweep re-derives what to
    # say from these rather than from having witnessed the transition.
    revealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resulted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TournamentChart(Base):
    """One round's eligible chart set, as resolved catalog rows.

    Membership is on song_difficulty_id and never song_id, which is what makes
    byd_2 free: ingest resolves the wire pair before this layer sees a row.
    """

    __tablename__ = "tournament_charts"
    __table_args__ = (
        UniqueConstraint(
            "round_id", "song_difficulty_id", name="uq_tournament_charts_chart"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    round_id: Mapped[int] = mapped_column(
        ForeignKey("tournament_rounds.id", ondelete="CASCADE"), nullable=False
    )
    # RESTRICT: a round's set must not silently lose a chart.
    song_difficulty_id: Mapped[int] = mapped_column(
        ForeignKey("song_difficulties.id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
    )


class TournamentParticipant(Base):
    """One roster entry. Frozen when the match leaves ``draft``."""

    __tablename__ = "tournament_participants"
    __table_args__ = (
        # Reject a duplicate account at signup: a shared Arcaea account cannot
        # be two sides of one match.
        UniqueConstraint(
            "match_id", "arcaea_account_id", name="uq_tournament_participants_account"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(
        ForeignKey("tournament_matches.id", ondelete="CASCADE"), nullable=False
    )
    # RESTRICT matches play_scores: a roster is history.
    arcaea_account_id: Mapped[int] = mapped_column(
        ForeignKey("arcaea_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    # 0/1 for head-to-head; turn order and board side.
    side_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # The player's DISCORD name, captured when they joined the roster. The
    # board prefers it to the Arcaea one: a thread is a Discord room and people
    # recognise each other by the name Discord shows. Captured rather than
    # looked up because the members intent is not enabled, so the member cache
    # cannot be trusted -- and the one moment the real user object is
    # guaranteed in hand is the command that put them on the roster. NULL falls
    # back to the Arcaea name.
    display_name: Mapped[str | None] = mapped_column(String(64))
    # "This participant has said go for the CURRENT wait", cleared whenever a
    # new wait begins. One column and one button serve both the intermission
    # skip and the instant start.
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
