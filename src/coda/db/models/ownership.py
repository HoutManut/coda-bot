"""What a player can play -- one row per chart they have declared.

Chart grain even though the picker only ever asks by pack: a pack is a fan-out
at write time, never a stored fact, so the per-chart Beyond answer needs no
precedence rule against a coarser row that could contradict it. See
``wiki/domains/catalog.md`` §Ownership (design call 8.d).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from coda.db.base import Base


class OwnedChart(Base):
    """One chart a player has declared they can play.

    Presence is the whole meaning: there are no negation rows, and an account
    with no rows at all has not declared, which every reader treats as
    unconstrained rather than as owning nothing.
    """

    __tablename__ = "owned_charts"

    arcaea_account_id: Mapped[int] = mapped_column(
        ForeignKey("arcaea_accounts.id", ondelete="CASCADE"), primary_key=True
    )
    song_difficulty_id: Mapped[int] = mapped_column(
        ForeignKey("song_difficulties.id", ondelete="CASCADE"), primary_key=True
    )
    declared_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
