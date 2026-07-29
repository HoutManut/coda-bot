"""Effective-value resolution for a chart.

A ``SongDifficulty`` leaves overridable columns ``NULL`` to inherit the parent
song's value. :func:`effective` resolves that inheritance the same way the schema
doc's ``COALESCE(song_difficulties.field, songs.field)`` would.
"""

from __future__ import annotations

from typing import Any

from coda.db.models.difficulty import SongDifficulty
from coda.db.models.song import Song

# Columns that inherit from the song when the difficulty's value is NULL.
OVERRIDABLE_FIELDS = (
    "name_en",
    "name_jp",
    "artist",
    "bpm",
    "bpm_base",
    "time",
    "side",
    "world_unlock",
    "remote_download",
    "bg",
    "date",
    "version",
    "jacket",
    "jacket_designer",
)


def effective(song: Song, difficulty: SongDifficulty, field: str) -> Any:
    """Return the chart's effective value for ``field``.

    For overridable fields, the difficulty's value wins unless ``None``; otherwise
    the song's value is used. Non-overridable fields are read straight off the
    difficulty.
    """
    if field in OVERRIDABLE_FIELDS:
        value = getattr(difficulty, field)
        return getattr(song, field) if value is None else value
    return getattr(difficulty, field)
