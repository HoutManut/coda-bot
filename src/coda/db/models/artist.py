"""Artist entity and its song junction (relational links, distinct from the
free-form ``songs.artist`` display string)."""

from __future__ import annotations

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from coda.db.base import Base
from coda.db.enums import ArtistKind, artist_kind_type


class Artist(Base):
    __tablename__ = "artists"

    artist_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # person = one human; unit = a named act (band/duo) with member links in
    # ``artist_members``. Edges imply a unit, but a unit may list no members, so
    # the kind is stored explicitly rather than inferred.
    kind: Mapped[ArtistKind] = mapped_column(
        artist_kind_type,
        nullable=False,
        default=ArtistKind.PERSON,
        server_default=ArtistKind.PERSON.value,
    )


class ArtistMember(Base):
    """Membership edge: ``group_id`` (a unit) contains ``member_id`` (any other
    artist). Self-referential M:N; no constraint that the group's kind is unit
    (the admin sets that), and members may themselves be units (nesting allowed)."""

    __tablename__ = "artist_members"

    group_id: Mapped[str] = mapped_column(
        ForeignKey("artists.artist_id", onupdate="CASCADE"), primary_key=True
    )
    member_id: Mapped[str] = mapped_column(
        ForeignKey("artists.artist_id", onupdate="CASCADE"), primary_key=True
    )


class SongArtist(Base):
    __tablename__ = "song_artists"

    song_id: Mapped[str] = mapped_column(
        ForeignKey("songs.song_id", onupdate="CASCADE"), primary_key=True
    )
    artist_id: Mapped[str] = mapped_column(
        # onupdate CASCADE so an artist_id rename cascades here (mirrors the
        # song_id rename; see migration b3f1c2d4e5a6).
        ForeignKey("artists.artist_id", onupdate="CASCADE"), primary_key=True
    )


class DifficultyArtist(Base):
    """Per-chart artist override. No rows for a chart = inherit the song's links;
    any row replaces the song's set for that chart (see the resolution rule)."""

    __tablename__ = "difficulty_artists"

    difficulty_id: Mapped[int] = mapped_column(
        ForeignKey("song_difficulties.id"), primary_key=True
    )
    artist_id: Mapped[str] = mapped_column(
        ForeignKey("artists.artist_id", onupdate="CASCADE"), primary_key=True
    )
