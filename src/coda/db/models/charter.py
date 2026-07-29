"""Charter entity and its song junction (relational links; the per-difficulty
``chart_designer`` column carries the free-form display string)."""

from __future__ import annotations

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from coda.db.base import Base


class Charter(Base):
    __tablename__ = "charters"

    charter_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)


class SongCharter(Base):
    __tablename__ = "song_charters"

    song_id: Mapped[str] = mapped_column(
        ForeignKey("songs.song_id", onupdate="CASCADE"), primary_key=True
    )
    charter_id: Mapped[str] = mapped_column(
        # onupdate CASCADE so a charter_id rename cascades here (mirrors the
        # song_id rename; see migration b3f1c2d4e5a6).
        ForeignKey("charters.charter_id", onupdate="CASCADE"), primary_key=True
    )


class DifficultyCharter(Base):
    """Per-chart charter override. No rows for a chart = inherit the song's links;
    any row replaces the song's set for that chart (see the resolution rule)."""

    __tablename__ = "difficulty_charters"

    difficulty_id: Mapped[int] = mapped_column(
        ForeignKey("song_difficulties.id"), primary_key=True
    )
    charter_id: Mapped[str] = mapped_column(
        ForeignKey("charters.charter_id", onupdate="CASCADE"), primary_key=True
    )
