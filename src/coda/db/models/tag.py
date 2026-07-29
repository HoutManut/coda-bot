"""Tags — a curated, multi-membership label vocabulary, orthogonal to packs.

A pack reflects the game's own grouping (a song belongs to exactly one). Tags
are a separate, looser axis: one song or chart can carry many, and one tag spans
many songs/charts. That cardinality is why tags are a many-to-many (join tables)
while aliases stay one-to-many — and why searching a *tag* yields the whole list
of matches, where an *alias* resolves to a single entity.

Tags group under categories (genre / event / collab / …) so the vocabulary stays
browsable. ``slug`` is globally unique: in a search-by-tag system one slug must
mean one tag, so the same label cannot recur across categories.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from coda.db.base import Base


class TagCategory(Base):
    __tablename__ = "tag_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    sort: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # ``#rrggbb`` base color used to tint this category's chips. Seeded from the
    # slug when a category is created without an explicit pick (see
    # ``presenters.seed_category_color``); nullable rows fall back to a default.
    color: Mapped[str | None] = mapped_column(String)


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("tag_categories.id", ondelete="CASCADE"), nullable=False
    )
    slug: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class SongTag(Base):
    __tablename__ = "song_tags"

    song_id: Mapped[str] = mapped_column(
        # onupdate CASCADE so a song_id rename cascades here (see migration
        # 66ad9752c1d2 — the rename route relies on every song-child FK doing this).
        ForeignKey("songs.song_id", ondelete="CASCADE", onupdate="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )


class DifficultyTag(Base):
    __tablename__ = "difficulty_tags"

    difficulty_id: Mapped[int] = mapped_column(
        ForeignKey("song_difficulties.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )
