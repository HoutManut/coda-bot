"""SongDifficulty — one chart (difficulty slot) of a song.

Overridable columns are nullable: ``NULL`` means "inherit the song's value".
The non-inherited columns (``level``, ``rating``, ``note``, ``chart_designer``,
``game_song_id``) are always chart-specific.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from coda.db.base import Base
from coda.db.enums import DifficultyClass, difficulty_class_type


class SongDifficulty(Base):
    __tablename__ = "song_difficulties"
    __table_args__ = (UniqueConstraint("song_id", "difficulty"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    song_id: Mapped[str] = mapped_column(
        ForeignKey("songs.song_id", onupdate="CASCADE"), nullable=False
    )
    difficulty: Mapped[DifficultyClass] = mapped_column(
        difficulty_class_type, nullable=False
    )

    # Never inherited. level stored encoded (x2, +1 for "+"); rating stored x10.
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    note: Mapped[int] = mapped_column(Integer, nullable=False)
    chart_designer: Mapped[str | None] = mapped_column(String)
    game_song_id: Mapped[str | None] = mapped_column(String)

    # Relational-link override flags. False = inherit the song's artist/charter
    # links. True = use this chart's own set (which may be empty = explicitly
    # unknown, e.g. a chart whose charter is unknown while the song's is known).
    artists_overridden: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    charters_overridden: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # Overridable: NULL = inherit from the parent song row.
    name_en: Mapped[str | None] = mapped_column(String)
    name_jp: Mapped[str | None] = mapped_column(String)
    artist: Mapped[str | None] = mapped_column(String)
    bpm: Mapped[str | None] = mapped_column(String)
    bpm_base: Mapped[float | None] = mapped_column(Float)
    time: Mapped[int | None] = mapped_column(Integer)
    side: Mapped[int | None] = mapped_column(SmallInteger)
    world_unlock: Mapped[bool | None] = mapped_column(Boolean)
    remote_download: Mapped[bool | None] = mapped_column(Boolean)
    bg: Mapped[str | None] = mapped_column(String)
    date: Mapped[int | None] = mapped_column(BigInteger)
    version: Mapped[str | None] = mapped_column(String)
    jacket: Mapped[str | None] = mapped_column(String)
    jacket_designer: Mapped[str | None] = mapped_column(String)
