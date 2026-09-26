"""PlayScore -- one observed play, accumulated by the poller.

The wire exposes only the latest play per account, so these rows are the only
play history that will ever exist. Identity is the wire tuple, never the
resolved chart FK, so an unresolved play is stored and re-resolved later
without identity churn. See wiki/modules/scores.md.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
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

from coda.arcaea.dto.enums import ClearType, GaugeModifier
from coda.db.base import Base
from coda.db.enums import clear_type_type, gauge_modifier_type


class PlayScore(Base):
    __tablename__ = "play_scores"
    __table_args__ = (
        # The play-identity key. All five fields exist on BOTH the friend and
        # own payloads, and time_played is server-assigned ms (immutable across
        # observations, arcaea-auth-behavior.md §time_played), so this tuple is
        # stable whether a play is first seen via the friend or the own path.
        # Ingest UPSERTs on it: a friend sighting then an own sighting of the
        # same play collapse to one row that gets enriched in place -- no
        # cross-tier duplicate. score: 0 is a REAL score (a sentinel, not
        # "empty") and is part of the key; never skip a row because score is 0.
        UniqueConstraint(
            "arcaea_account_id",
            "wire_song_id",
            "wire_difficulty",
            "score",
            "time_played",
            name="uq_play_identity",
        ),
        # /recent, history, and the live-update feed: latest-first per account.
        Index("ix_play_scores_account_time", "arcaea_account_id", "time_played"),
        # Personal best per chart and best-pool scans.
        Index(
            "ix_play_scores_account_chart_score",
            "arcaea_account_id",
            "song_difficulty_id",
            "score",
        ),
        # Secondary guard: lowiro's own-path play id is globally unique, so no
        # two own-tier rows may share one. Partial -- friend rows have no id.
        Index(
            "uq_play_scores_wire_play_id",
            "wire_play_id",
            unique=True,
            postgresql_where="wire_play_id IS NOT NULL",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # RESTRICT, not CASCADE: this history is irreplaceable (no score backfill on
    # the friend/free-own tiers), and straying an account deliberately KEEPS its
    # rows -- it never deletes the ArcaeaAccount. A future account delete must be
    # a conscious act that first deals with the scores, not a silent cascade.
    arcaea_account_id: Mapped[int] = mapped_column(
        ForeignKey("arcaea_accounts.id", ondelete="RESTRICT"), nullable=False
    )

    # --- WIRE identity: immutable, present on both tiers. Never dedup on the
    # resolved FK below; always on these. ---
    wire_song_id: Mapped[str] = mapped_column(String, nullable=False)
    wire_difficulty: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    # Milliseconds since epoch, UTC, assigned server-side at submission.
    time_played: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # --- Resolved chart: DERIVED, nullable, backfillable. NULL = the song was
    # not in the catalog when observed (routine staleness, not a dropped play).
    # A reconcile pass fills it after the seed catches up; SET NULL re-orphans
    # cleanly if the chart is later deleted. ---
    song_difficulty_id: Mapped[int | None] = mapped_column(
        ForeignKey("song_difficulties.id", ondelete="SET NULL")
    )

    # --- Own-credentials path only. NULL on friend-tier rows. In-game vocab
    # (pure/far/lost); the API's perfect/near/miss names stop at the DTO. ---
    shiny_pure_count: Mapped[int | None] = mapped_column(Integer)
    pure_count: Mapped[int | None] = mapped_column(Integer)
    far_count: Mapped[int | None] = mapped_column(Integer)
    lost_count: Mapped[int | None] = mapped_column(Integer)
    health: Mapped[int | None] = mapped_column(SmallInteger)
    # Stored as native pg enums (string values), matching difficulty_class_type.
    # best_clear_type is intentionally absent: the DTO drops it and it is
    # derivable from our own accumulated rows (MAX clear over the chart).
    clear_type: Mapped[ClearType | None] = mapped_column(clear_type_type)
    modifier: Mapped[GaugeModifier | None] = mapped_column(gauge_modifier_type)
    # lowiro's stable per-play id. Own tier only; NULL on friend. Enrichment and
    # trace column, NOT the dedup key (friend rows have none) -- see uq above.
    wire_play_id: Mapped[str | None] = mapped_column(String)

    # The account owner's correction to the assumed-clear heuristic that stands in
    # for a missing clear_type. Per ROW, not per chart: a later play on the same
    # chart carries no override of its own and falls back to the heuristic. Only
    # meaningful while clear_type is NULL -- a wire-known clear type is fact and
    # wins (resolve_clear, utils/scoring.py).
    clear_override: Mapped[bool | None] = mapped_column(Boolean)

    # 'friend' | 'own' -- which path observed THIS row. Tells whether the detail
    # columns are trustworthy and drives cross-tier enrichment (a 'friend'
    # sighting must not overwrite detail on an existing 'own' row).
    source: Mapped[str] = mapped_column(String(8), nullable=False)

    # When WE captured it -- distinct from time_played (when it was played).
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
