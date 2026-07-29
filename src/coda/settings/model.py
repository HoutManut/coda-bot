from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from coda.db.base import Base


class ConfigValue(Base):
    __tablename__ = "config_values"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    scope: Mapped[str] = mapped_column(String, primary_key=True)
    scope_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    set_by: Mapped[int | None] = mapped_column(BigInteger)
    set_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
