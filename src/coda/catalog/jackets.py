"""Locale-aware names, day/night, and layered jacket-file resolution.

Names and jacket art depend on the viewer's locale (JP vs. everything else) and,
for a few songs, the time of day. These helpers are the single source for both,
shared by every ``/song`` render path.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import hikari

from coda.catalog.resolution import effective
from coda.db.models import Song, SongDifficulty

JACKETS_DIR = Path("assets/jackets")
# Shown when a song/chart resolves to no jacket file at all.
BASE_JACKET = JACKETS_DIR / "base.jpg"

# GMT+7 until an opt-in /timezone preference exists (handoff 09 §12). is_night
# ignores user_id today; the signature keeps the seam so per-user lands with no
# change to render code.
_OFFSET = timezone(timedelta(hours=7))

# Songs shipping a locale/time variant jacket.
_JP_VARIANTS: frozenset[str] = frozenset({"solitarydream"})
_NIGHT_VARIANTS: frozenset[str] = frozenset({"melodyoflove"})


def is_jp_locale(locale: object) -> bool:
    """True when the interaction locale is Japanese."""
    return str(locale or "").lower().startswith("ja")


def display_name(name_en: str, name_jp: str | None, locale: object) -> str:
    """The effective localised name: JP name for a JP viewer when it differs,
    else the English name."""
    if is_jp_locale(locale) and name_jp and name_jp != name_en:
        return name_jp
    return name_en


def is_night(user_id: int, now: datetime | None = None) -> bool:
    """Whether it is night for the viewer. 06:00–19:59 (GMT+7) is day."""
    local = (now or datetime.now(_OFFSET)).astimezone(_OFFSET)
    return not (6 <= local.hour < 20)


def jacket_path(
    song_id: str, base_stem: str, *, jp: bool, night: bool
) -> Path | None:
    """Resolve a jacket file, applying JP then NIGHT variants, falling back a
    layer for any missing file. ``None`` when even the base is absent."""
    stems: list[str] = [base_stem]
    if night and song_id in _NIGHT_VARIANTS:
        stems.insert(0, f"{base_stem}_NIGHT")
    if jp and song_id in _JP_VARIANTS:
        stems.insert(0, f"{base_stem}_JP")
    for stem in stems:
        candidate = JACKETS_DIR / f"{stem}.jpg"
        if candidate.exists():
            return candidate
    return None


def _jacket_file(path: Path | None) -> hikari.File | None:
    """The File for a resolved jacket, else the base placeholder, else None --
    never a File for a path that doesn't exist (which crashes at send)."""
    if path is not None:
        return hikari.File(path)
    if BASE_JACKET.exists():
        return hikari.File(BASE_JACKET)
    return None


def song_jacket(song: Song, locale: object, night: bool) -> hikari.File | None:
    """The song-level jacket for a viewer."""
    path = jacket_path(song.song_id, song.jacket, jp=is_jp_locale(locale), night=night)
    return _jacket_file(path)


def chart_jacket(
    song: Song, chart: SongDifficulty, locale: object, night: bool
) -> hikari.File | None:
    """The chart's jacket, falling back a layer at a time.

    A chart whose own jacket file is absent falls back to the song's, then to
    the base placeholder: some consolidated charts store a stem with no asset.
    """
    jp = is_jp_locale(locale)
    stem = effective(song, chart, "jacket")
    path = jacket_path(song.song_id, stem, jp=jp, night=night)
    if path is None and stem != song.jacket:
        path = jacket_path(song.song_id, song.jacket, jp=jp, night=night)
    return _jacket_file(path)
