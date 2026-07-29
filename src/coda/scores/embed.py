"""Render one stored play as a Discord embed.

Pure: takes rows, returns an embed. ``/recent`` and the live-update poster show
the same play the same way, so the format lives here and not in either caller.

Everything below the score degrades. A friend-tier row carries no note counts, a
chart may not be in the catalog yet (routine -- a song can ship in-game before a
seed), and a delisted chart hides its CC. Each of those drops its line rather
than inventing a value.
"""

from __future__ import annotations

from datetime import UTC, datetime

import hikari

from coda.catalog.colors import CLASS_COLORS
from coda.catalog.jackets import chart_jacket, display_name
from coda.catalog.labels import chart_rating_line
from coda.catalog.resolution import effective
from coda.db.enums import DifficultyClass
from coda.db.models import PlayScore, Song, SongDifficulty
from coda.utils.scoring import PURE_MEMORY, format_score

# A max score is worth celebrating, so it gets the one thing embed text can't
# otherwise do -- colour. A link renders blue; where it goes is between you and
# the person who clicked it.
_MAX_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

_COLOR_UNKNOWN = 0x5865F2

_UNRESOLVED_NOTE = (
    "-# This chart isn't known to the bot, so the song name, jacket and "
    "rating are unavailable."
)


def score_embed(
    row: PlayScore,
    chart: SongDifficulty | None,
    song: Song | None,
    *,
    locale: object,
    night: bool,
) -> tuple[hikari.Embed, hikari.File | None]:
    """The embed for one play, plus the jacket file it references.

    ``chart``/``song`` are None when the play's chart is unresolved. The caller
    sends the returned file only via the embed -- passing it as an attachment
    too uploads a second copy.
    """
    embed = hikari.Embed(
        title=_title(row, chart, song, locale),
        description=_body(row, chart),
        color=_color(row, chart),
        # time_played is server-assigned ms; the embed's own timestamp field
        # renders it in the footer, localised by Discord per viewer.
        timestamp=datetime.fromtimestamp(row.time_played / 1000, tz=UTC),
    )
    file = chart_jacket(song, chart, locale, night) if song and chart else None
    if file is not None:
        embed.set_thumbnail(file)
    return embed, file


def _title(
    row: PlayScore, chart: SongDifficulty | None, song: Song | None, locale: object
) -> str:
    """The chart's localized name, or the raw wire id when unresolved."""
    if song is None or chart is None:
        return row.wire_song_id
    return display_name(
        effective(song, chart, "name_en"), effective(song, chart, "name_jp"), locale
    )


def _color(row: PlayScore, chart: SongDifficulty | None) -> int:
    """The played difficulty's colour, from the chart or the raw wire int."""
    difficulty = chart.difficulty if chart else _wire_class(row)
    if difficulty is None:
        return _COLOR_UNKNOWN
    return CLASS_COLORS[difficulty]


def _wire_class(row: PlayScore) -> DifficultyClass | None:
    return DifficultyClass.from_ordinal(row.wire_difficulty)


def _body(row: PlayScore, chart: SongDifficulty | None) -> str:
    lines = [_score_line(row.score, chart.note if chart else None)]
    if chart is not None:
        lines.append(chart_rating_line(row.score, chart))
    if row.pure_count is not None:
        lines.append(_detail_line(row))
    if chart is None:
        lines.append(_UNRESOLVED_NOTE)
    return "\n".join(lines)


def _score_line(score: int, note: int | None) -> str:
    """The score, plus how far from max it is when that is knowable.

    Below a PM this is just the grouped digits. At or above one, the distance
    from max (10M + one point per note) is the interesting number -- but only
    the catalog knows the note count, so an unresolved chart shows the PM alone.
    """
    text = format_score(score)
    if score < PURE_MEMORY:
        return text

    if not note:
        return text

    short = PURE_MEMORY + note - score
    if short == 0:
        return f"[{text} (MPM)]({_MAX_URL})"
    if short < 0:
        return text
    return f"{text} (MPM-{short})"


def _detail_line(row: PlayScore) -> str:
    """Pure/far/lost counter"""
    pure = f"{row.pure_count}"
    if row.shiny_pure_count is not None:
        pure = f"{pure} ({row.shiny_pure_count})"
    return f"*Pure:* {pure} *Far:* {row.far_count} *Lost:* {row.lost_count}"
