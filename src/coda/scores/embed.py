"""Render one stored play as a Discord embed.

Pure: takes rows, returns an embed. ``/recent`` and the live-update poster show
the same play the same way, so the format lives here and not in either caller.

Everything below the score degrades. A friend-tier row carries no note counts, a
chart may not be in the catalog yet (routine -- a song can ship in-game before a
seed), and a delisted chart hides its CC. Each of those drops its line rather
than inventing a value.
"""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class PlayerIdentity:
    """Who played it, for a post that has no interaction header to say so."""

    name: str
    avatar_url: str | None = None


def score_embed(
    row: PlayScore,
    chart: SongDifficulty | None,
    song: Song | None,
    *,
    locale: object,
    night: bool,
    player: PlayerIdentity | None = None,
    live: bool = False,
    untracked: bool = False,
) -> tuple[hikari.Embed, hikari.File | None]:
    """The embed for one play, plus the jacket file it references.

    ``chart``/``song`` are None when the play's chart is unresolved. The caller
    sends the returned file only via the embed -- passing it as an attachment
    too uploads a second copy.

    ``player`` adds an author line. ``/recent`` omits it -- Discord's own
    interaction header already attributes the reply to whoever invoked it -- but
    a live post is bot-authored, so in a channel following several players a
    bare embed would say nothing about whose play it is.

    ``live`` marks a poster-authored update; ``untracked`` marks a play the bot
    only observed and never stored (the account has tracking off). Both surface
    as a word in the footer, next to the timestamp.
    """
    embed = hikari.Embed(
        title=_title(row, chart, song, locale),
        description=_body(row, chart),
        color=_color(row, chart),
        # time_played is server-assigned ms; the embed's own timestamp field
        # renders it in the footer, localised by Discord per viewer.
        timestamp=datetime.fromtimestamp(row.time_played / 1000, tz=UTC),
    )
    footer = _footer(live, untracked)
    if footer is not None:
        embed.set_footer(footer)
    if player is not None:
        embed.set_author(name=player.name, icon=player.avatar_url)
    file = chart_jacket(song, chart, locale, night) if song and chart else None
    if file is not None:
        embed.set_thumbnail(file)
    return embed, file


def _footer(live: bool, untracked: bool) -> str | None:
    """A minimal marker beside the timestamp, or None for a plain stored play."""
    marks: list[str] = []
    if live:
        marks.append("Live")
    if untracked:
        marks.append("Untracked")
    return " · ".join(marks) if marks else None


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
