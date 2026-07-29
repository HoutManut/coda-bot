"""Song pack — the store/collection a song belongs to."""

from __future__ import annotations

from sqlalchemy import BigInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from coda.db.base import Base


class Pack(Base):
    __tablename__ = "packs"

    pack_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    cover_art: Mapped[str | None] = mapped_column(String)
    release_date: Mapped[int | None] = mapped_column(BigInteger)
