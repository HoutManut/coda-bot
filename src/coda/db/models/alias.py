"""Search aliases for songs, difficulties, artists, and charters.

These tables are the search source of truth, populated by the catalog seed (the
Python service layer — no DB triggers). The trigram / materialized-view layer
that consumes them is a later phase; the tables exist now so seeding is complete.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from coda.db.base import Base


class SongAlias(Base):
    __tablename__ = "song_aliases"
    __table_args__ = (UniqueConstraint("song_id", "alias"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    song_id: Mapped[str] = mapped_column(
        ForeignKey("songs.song_id", onupdate="CASCADE"), nullable=False
    )
    alias: Mapped[str] = mapped_column(Text, nullable=False)


class DifficultyAlias(Base):
    __tablename__ = "difficulty_aliases"
    __table_args__ = (UniqueConstraint("difficulty_id", "alias"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    difficulty_id: Mapped[int] = mapped_column(
        ForeignKey("song_difficulties.id"), nullable=False
    )
    alias: Mapped[str] = mapped_column(Text, nullable=False)


class ArtistAlias(Base):
    __tablename__ = "artist_aliases"
    __table_args__ = (UniqueConstraint("artist_id", "alias"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    artist_id: Mapped[str] = mapped_column(
        ForeignKey("artists.artist_id", onupdate="CASCADE"), nullable=False
    )
    alias: Mapped[str] = mapped_column(Text, nullable=False)


class CharterAlias(Base):
    __tablename__ = "charter_aliases"
    __table_args__ = (UniqueConstraint("charter_id", "alias"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    charter_id: Mapped[str] = mapped_column(
        ForeignKey("charters.charter_id", onupdate="CASCADE"), nullable=False
    )
    alias: Mapped[str] = mapped_column(Text, nullable=False)
