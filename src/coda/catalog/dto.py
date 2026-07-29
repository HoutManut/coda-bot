"""Parse one ``arcsongs.json`` record into plain, ORM-ready Python.

The JSON shape: a ``default`` block holds song-level values, sibling keys
(``pst``/``prs``/``ftr``/``byd``/``etr``) hold per-difficulty data, and
``difficulties`` lists which of those keys are present. Per-difficulty *override*
fields are copied only when present — absent keys stay ``None`` so the DB row
inherits from the song (``NULL`` = inherit). ``charters``/``artists`` lists are
relational id lists; ``chart_designer`` is the per-chart display string.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from coda.db.enums import DifficultyClass

# Fields a difficulty may override; absent => inherit (stays None).
OVERRIDABLE = (
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


@dataclass(frozen=True, slots=True)
class ParsedDifficulty:
    difficulty: DifficultyClass
    level: int
    rating: int
    note: int
    chart_designer: str | None
    game_song_id: str | None
    # Overridable columns; None means inherit from the song.
    overrides: dict[str, Any]
    # Relational charter ids declared on this difficulty.
    charter_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ParsedSong:
    song_id: str
    idx: int
    pack_id: str | None
    fields: dict[str, Any]
    difficulties: tuple[ParsedDifficulty, ...]
    artist_ids: tuple[str, ...]
    # Union of charter ids across the song default and every difficulty.
    charter_ids: tuple[str, ...]
    aliases: tuple[str, ...]


def parse_song(record: dict[str, Any]) -> ParsedSong:
    default: dict[str, Any] = record["default"]

    charter_ids: list[str] = list(default.get("charters", []) or [])
    difficulties: list[ParsedDifficulty] = []

    for key in record.get("difficulties", []):
        diff_data: dict[str, Any] = record[key]
        diff_charters = tuple(diff_data.get("charters", []) or [])
        charter_ids.extend(diff_charters)

        difficulties.append(
            ParsedDifficulty(
                difficulty=DifficultyClass(key),
                level=diff_data["level"],
                rating=diff_data["rating"],
                note=diff_data.get("note", 0),
                chart_designer=diff_data.get("chart_designer"),
                game_song_id=diff_data.get("game_song_id"),
                overrides={
                    name: diff_data[name]
                    for name in OVERRIDABLE
                    if name in diff_data
                },
                charter_ids=diff_charters,
            )
        )

    song_fields = {
        "pack_name": default.get("pack_name", ""),
        "name_en": default.get("name_en", ""),
        "name_jp": default.get("name_jp", ""),
        "artist": default.get("artist", ""),
        "bpm": default.get("bpm", ""),
        "bpm_base": default.get("bpm_base", 0.0),
        "time": default.get("time", 0),
        "side": default.get("side", 0),
        "world_unlock": default.get("world_unlock", False),
        "remote_download": default.get("remote_download", True),
        "bg": default.get("bg", ""),
        "date": default.get("date", 0),
        "version": default.get("version", ""),
        "jacket": default.get("jacket", ""),
        "jacket_designer": default.get("jacket_designer"),
    }

    return ParsedSong(
        song_id=record["song_id"],
        idx=record["idx"],
        pack_id=default.get("pack") or None,
        fields=song_fields,
        difficulties=tuple(difficulties),
        artist_ids=tuple(default.get("artists", []) or []),
        charter_ids=tuple(dict.fromkeys(charter_ids)),  # dedupe, keep order
        aliases=tuple(default.get("aliases", []) or []),
    )


def parse_catalog(data: dict[str, Any]) -> list[ParsedSong]:
    """Parse the full ``{"songs": [...]}`` document."""
    return [parse_song(record) for record in data["songs"]]
