"""Per-difficulty-class search behaviour, read at startup and applied in Python.

One row per :class:`~coda.db.enums.DifficultyClass`. Drives the fuzzy-search
resolver (:mod:`coda.catalog.search`): whether a class is hidden from broad
search, the trigram floor to include a candidate, the cutoff above which a hit is
served directly (vs. a "did you mean" prompt), and the query suffixes that signal
deliberate ``err`` intent. Tunable without a deploy.

The ``search_index`` materialized view this cooperates with is created in the
same migration but has no ORM model — it is raw SQL Alembic cannot autogenerate.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Float, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from coda.db.base import Base
from coda.db.enums import DifficultyClass, difficulty_class_type


class DifficultySearchConfig(Base):
    __tablename__ = "difficulty_search_config"

    difficulty: Mapped[DifficultyClass] = mapped_column(
        difficulty_class_type, primary_key=True
    )
    hidden_from_broad: Mapped[bool] = mapped_column(Boolean, nullable=False)
    min_similarity: Mapped[float] = mapped_column(Float, nullable=False)
    # Trigram floor above which a top candidate is served directly; between
    # min_similarity and this it becomes a "did you mean" prompt instead.
    strong: Mapped[float] = mapped_column(Float, nullable=False)
    # Query suffixes signalling deliberate err intent (err only); NULL otherwise.
    af_suffixes: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
