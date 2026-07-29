"""Song — one row per song, holding the default field values (from ``ftr``)."""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from coda.db.base import Base


class Song(Base):
    __tablename__ = "songs"

    song_id: Mapped[str] = mapped_column(String, primary_key=True)
    idx: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    # onupdate CASCADE so a pack_id rename repoints its songs (mirrors the
    # song_id rename; see migration b3f1c2d4e5a6).
    pack_id: Mapped[str | None] = mapped_column(
        ForeignKey("packs.pack_id", onupdate="CASCADE")
    )

    # Per-song, always authoritative even when pack_id is shared.
    pack_name: Mapped[str] = mapped_column(String, nullable=False)
    name_en: Mapped[str] = mapped_column(String, nullable=False)
    name_jp: Mapped[str] = mapped_column(String, nullable=False, default="")
    artist: Mapped[str] = mapped_column(String, nullable=False)
    bpm: Mapped[str] = mapped_column(String, nullable=False)
    bpm_base: Mapped[float] = mapped_column(Float, nullable=False)
    time: Mapped[int] = mapped_column(Integer, nullable=False)
    # Visual theme, stored as the game's numeric side id (0-3); see db.enums.Side.
    side: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    world_unlock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    remote_download: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    bg: Mapped[str] = mapped_column(String, nullable=False)
    date: Mapped[int] = mapped_column(BigInteger, nullable=False)
    version: Mapped[str] = mapped_column(String, nullable=False)
    jacket: Mapped[str] = mapped_column(String, nullable=False)
    jacket_designer: Mapped[str | None] = mapped_column(String)
