"""SpoilerVersion — one row per game version the owner has flagged as a spoiler.

Presence is the flag; there is no boolean column. A version absent from this
table is not a spoiler, which keeps ``spoiler remove`` a plain DELETE and makes
the cached set (``catalog/spoilers.py``) a straight ``SELECT version``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from coda.db.base import Base


class SpoilerVersion(Base):
    __tablename__ = "spoiler_versions"

    version: Mapped[str] = mapped_column(String, primary_key=True)
    set_by: Mapped[int | None] = mapped_column(BigInteger)
    set_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
