"""/calc -- what would this score be worth?

Takes a score plus either a raw chart constant or a catalog target, and answers
with the play rating it earns. The math is :mod:`coda.utils.scoring` and the
target resolution is :class:`~coda.catalog.search.SearchService`; this module is
parsing and presentation only.

Unlike ``/song``, a bare number here is always a CC (``11`` = ``11.0``), never a
level -- a calculator's most common input is the constant itself.

Multi-match resolutions are answered, not refused: a song lists every chart, a
two-Beyond song lists both. Only a genuine ambiguity between *songs* asks, via
the same raw ``calc:`` custom-id contract ``/song`` uses -- the score rides in
the id, so a click recomputes statelessly.
"""

from __future__ import annotations

import logging
import re

import hikari
import lightbulb
from hikari.impl import MessageActionRowBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from coda.catalog.colors import CLASS_COLORS, SIDE_COLORS
from coda.catalog.jackets import chart_jacket, display_name, is_night, song_jacket
from coda.catalog.labels import (
    CLASS_FULL,
    CLASS_OPTIONS,
    CLASS_SHORT,
    chart_rating_line,
    format_cc,
    sorted_charts,
)
from coda.catalog.lookup import load_chart, load_charts_ordered, load_song
from coda.catalog.resolution import effective
from coda.catalog.search import (
    ChartHit,
    ChartList,
    ChartPick,
    DidYouMean,
    NoMatch,
    Resolution,
    SearchService,
    SongDupes,
    SongHit,
)
from coda.db.enums import DifficultyClass, Side
from coda.db.models import Song, SongDifficulty
from coda.db.session import async_session
from coda.settings import ConfigService
from coda.settings.zone import effective_zone
from coda.utils.scoring import (
    MAX_SCORE,
    PURE_MEMORY,
    calculate_play_rating,
    format_rating,
    format_score,
)

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()

_CUSTOM_ID_PREFIX = "calc"
_COLOR_INFO = 0x5865F2

# Dividers a human types into a score. Not a general "strip non-digits": that
# turns garbage into a plausible number (see friend_code.py for the same rule).
_DIVIDERS_RE = re.compile(r"[\s,'_]")
_DIGITS_RE = re.compile(r"^\d{1,8}$")
_MAX_SCORE_TEXT = format_score(MAX_SCORE)
_RAW_CC_RE = re.compile(r"^\d{1,2}(\.\d+)?$")
_CC_MIN = 0.1
_CC_MAX = 13.0

_BAD_SCORE = (
    f"That's not a score."
)
_BAD_CC = f"That's not a chart constant/"
_IMPOSSIBLE = "That score is above the maximum for this chart."
_NO_LISTS = "Name a song or a chart."
_NO_SUCH_CHART = "There's no chart with that id. Pick one from the suggestions."

# An autocomplete row points at one chart by id. Not part of the typed grammar:
# a class token can't name a second Beyond, and the row already says which one.
_CHART_REF = "#"
_CHART_REF_RE = re.compile(r"^#(\d+)$")

# Autocomplete tags: byd_2 shows as plain "BYD" -- its row is told apart by the
# chart's own name ("Last | Eternity"), which is what a player actually knows.
_CLASS_TAG = CLASS_SHORT | {DifficultyClass.BYD_2: "BYD"}


# --- parsing ----------------------------------------------------------------


def _parse_score(text: str) -> int | None:
    """A typed score with its dividers removed, or ``None`` if it isn't one.

    Bounded by :data:`~coda.utils.scoring.MAX_SCORE` -- no chart in the game can
    pay out more. A chart-specific ceiling (``10M + note``) is tighter still and
    is applied where the chart is known.
    """
    digits = _DIVIDERS_RE.sub("", text.strip())
    if not _DIGITS_RE.match(digits):
        return None
    score = int(digits)
    return score if score <= MAX_SCORE else None


def _parse_cc(text: str) -> float | None:
    """A raw chart constant, truncated to one decimal, or ``None`` when the
    target isn't numeric. In range but malformed returns ``None`` too -- the
    caller distinguishes with :func:`_looks_numeric`."""
    if not _RAW_CC_RE.match(text):
        return None
    whole, _, frac = text.partition(".")
    value = float(f"{whole}.{frac[0] if frac else 0}")
    return value if _CC_MIN <= value <= _CC_MAX else None


def _looks_numeric(text: str) -> bool:
    return bool(_RAW_CC_RE.match(text))


# --- rendered payload -------------------------------------------------------


class _Rendered:
    """An embed + optional jacket + component rows, ready to send or edit-into."""

    def __init__(
        self,
        embed: hikari.Embed,
        file: hikari.File | None = None,
        rows: list[MessageActionRowBuilder] | None = None,
        *,
        transient: bool = False,
    ) -> None:
        self.embed = embed
        self.file = file
        self.rows = rows or []
        self.transient = transient


def _error(text: str) -> _Rendered:
    return _Rendered(
        hikari.Embed(title="Nothing to calculate", description=text, color=_COLOR_INFO),
        transient=True,
    )


# --- renderers --------------------------------------------------------------


def _render_raw_cc(score: int, cc: float) -> _Rendered:
    rating = calculate_play_rating(score, cc)
    embed = hikari.Embed(
        title=format_score(score),
        description=f"{cc:.1f} → **{format_rating(rating)}**",
        color=_COLOR_INFO,
    )
    return _Rendered(embed)


def _title(name: str, score: int) -> str:
    return f"{name} — {format_score(score)}"


def _song_color(song: Song) -> int:
    """Song mode takes the side's colour; chart mode takes the class's (``/song``)."""
    return SIDE_COLORS[Side.from_id(song.side)]


def _chart_lines(score: int, charts: list[SongDifficulty]) -> str:
    return "\n".join(
        f"- {chart_rating_line(score, chart)}"
        for chart in sorted_charts(charts)
        if chart.difficulty != DifficultyClass.ERR
    )


async def _render_song(
    db: AsyncSession, song_id: str, score: int, locale: object, night: bool
) -> _Rendered:
    song, charts = await load_song(db, song_id)
    embed = hikari.Embed(
        title=_title(display_name(song.name_en, song.name_jp, locale), score),
        description=_chart_lines(score, charts),
        color=_song_color(song),
    )
    file = song_jacket(song, locale, night)
    if file is not None:
        embed.set_thumbnail(file)
    return _Rendered(embed, file)


async def _render_chart(
    db: AsyncSession, difficulty_id: int, score: int, locale: object, night: bool
) -> _Rendered:
    song, chart = await load_chart(db, difficulty_id)
    if score > PURE_MEMORY + chart.note:
        return _error(_IMPOSSIBLE)
    name = display_name(
        effective(song, chart, "name_en"), effective(song, chart, "name_jp"), locale
    )
    embed = hikari.Embed(
        title=_title(name, score),
        description=chart_rating_line(score, chart),
        color=CLASS_COLORS[chart.difficulty],
    )
    file = chart_jacket(song, chart, locale, night)
    if file is not None:
        embed.set_thumbnail(file)
    return _Rendered(embed, file)


async def _render_chart_ref(
    db: AsyncSession, difficulty_id: int, score: int, locale: object, night: bool
) -> _Rendered:
    """A ``#<id>`` target. Unlike the component path the id is typed, so a miss
    is a user error, not a bug."""
    if await db.get(SongDifficulty, difficulty_id) is None:
        return _error(_NO_SUCH_CHART)
    return await _render_chart(db, difficulty_id, score, locale, night)


async def _render_chart_pick(
    db: AsyncSession, difficulty_ids: list[int], score: int, locale: object, night: bool
) -> _Rendered:
    entries = await load_charts_ordered(db, difficulty_ids)
    charts = [chart for chart, _ in entries]
    song = entries[0][1]
    embed = hikari.Embed(
        title=_title(display_name(song.name_en, song.name_jp, locale), score),
        description=_chart_lines(score, charts),
        color=_song_color(song),
    )
    file = song_jacket(song, locale, night)
    if file is not None:
        embed.set_thumbnail(file)
    return _Rendered(embed, file)


def _song_row(score: int, labels: list[tuple[str, str]]) -> MessageActionRowBuilder:
    row = MessageActionRowBuilder()
    for label, song_id in labels[:5]:
        row.add_interactive_button(
            hikari.ButtonStyle.SECONDARY,
            f"{_CUSTOM_ID_PREFIX}:s:{score}:{song_id}",
            label=label[:80],
        )
    return row


def _chart_row(score: int, labels: list[tuple[str, int]]) -> MessageActionRowBuilder:
    row = MessageActionRowBuilder()
    for label, difficulty_id in labels[:5]:
        row.add_interactive_button(
            hikari.ButtonStyle.SECONDARY,
            f"{_CUSTOM_ID_PREFIX}:c:{score}:{difficulty_id}",
            label=label[:80],
        )
    return row


async def _render_song_dupes(
    db: AsyncSession, song_ids: list[str], score: int, locale: object
) -> _Rendered:
    songs = [await db.get(Song, sid) for sid in song_ids]
    labels = [
        (
            f"{display_name(s.name_en, s.name_jp, locale)} — {s.artist} ({s.pack_name})",
            s.song_id,
        )
        for s in songs
        if s is not None
    ]
    embed = hikari.Embed(
        title=format_score(score),
        description="A few songs share that name — pick one:",
        color=_COLOR_INFO,
    )
    return _Rendered(embed, None, [_song_row(score, labels)])


async def _render_did_you_mean(
    db: AsyncSession, res: DidYouMean, score: int, locale: object
) -> _Rendered:
    song_labels: list[tuple[str, str]] = []
    chart_labels: list[tuple[str, int]] = []
    for cand in res.candidates:
        if cand.difficulty_id is None:
            song = await db.get(Song, cand.song_id)
            if song is not None:
                song_labels.append(
                    (display_name(song.name_en, song.name_jp, locale), song.song_id)
                )
        else:
            song, chart = await load_chart(db, cand.difficulty_id)
            chart_labels.append(
                (
                    f"{display_name(song.name_en, song.name_jp, locale)} — "
                    f"{CLASS_SHORT[chart.difficulty]}",
                    chart.id,
                )
            )
    embed = hikari.Embed(
        title=format_score(score),
        description="No exact match. Closest results:",
        color=_COLOR_INFO,
    )
    rows: list[MessageActionRowBuilder] = []
    if song_labels:
        rows.append(_song_row(score, song_labels))
    if chart_labels:
        rows.append(_chart_row(score, chart_labels))
    return _Rendered(embed, None, rows)


async def _render(
    db: AsyncSession,
    res: Resolution,
    *,
    score: int,
    target: str,
    locale: object,
    night: bool,
) -> _Rendered:
    match res:
        case SongHit(song_id=song_id, missing_class=missing):
            rendered = await _render_song(db, song_id, score, locale, night)
            if missing is not None:
                rendered.embed.set_footer(
                    f"This song has no {CLASS_FULL[missing]} chart."
                )
            return rendered
        case ChartHit(difficulty_id=cid):
            return await _render_chart(db, cid, score, locale, night)
        case ChartPick(difficulty_ids=ids):
            return await _render_chart_pick(db, ids, score, locale, night)
        case SongDupes(song_ids=ids):
            return await _render_song_dupes(db, ids, score, locale)
        case DidYouMean():
            return await _render_did_you_mean(db, res, score, locale)
        case ChartList():
            return _error(_NO_LISTS)
        case NoMatch(reason=reason):
            return _error(reason or f"Nothing matched **{target}**.")
    return _error(_NO_LISTS)


# --- command ----------------------------------------------------------------


async def _ac_target(ctx: lightbulb.AutocompleteContext[str]) -> None:
    """A raw-CC echo, one row per matching song, or -- once only one song is
    left -- that song's charts, so the pick lands straight on a chart."""
    typed = str(ctx.focused.value or "").strip()
    if not typed:
        await ctx.respond([])
        return
    cc = _parse_cc(typed)
    if cc is not None:
        await ctx.respond([(f"CC {cc:.1f} — calculate directly", typed)])
        return
    async with async_session() as db:
        choices = await _target_choices(db, typed, ctx.interaction.locale)
    await ctx.respond(choices[:25])


async def _target_choices(
    db: AsyncSession, typed: str, locale: object
) -> list[tuple[str, str]]:
    candidates = await SearchService().candidate_songs(db, typed, limit=25)
    if len(candidates) != 1:
        return [(name[:100], song_id) for song_id, name, _, _ in candidates]
    song_id, name, _, _ = candidates[0]
    return await _chart_choices(db, song_id, name, locale)


async def _chart_choices(
    db: AsyncSession, song_id: str, name: str, locale: object
) -> list[tuple[str, str]]:
    """The song's own row, then one per chart.

    Each row carries the chart's *own* resolved name, so a second Beyond reads
    "Last | Eternity BYD" rather than "Last BYD 2" -- the ``byd_2`` slot is an
    app-side distinction and never shown. Two Beyond rows then name two different
    charts, so the value is a direct ``#<difficulty_id>`` reference: the class
    token ``byd`` names both and would collapse them back into a pick.
    """
    song, charts = await load_song(db, song_id)
    rows = [(f"{name} — all charts"[:100], song_id)]
    for chart in sorted_charts(charts):
        if chart.difficulty == DifficultyClass.ERR:
            continue
        chart_name = display_name(
            effective(song, chart, "name_en"), effective(song, chart, "name_jp"), locale
        )
        label = f"{chart_name} {_CLASS_TAG[chart.difficulty]}"
        cc = format_cc(chart.rating)
        rows.append(
            (f"{label} ({cc})"[:100] if cc else label[:100], f"{_CHART_REF}{chart.id}")
        )
    return rows



@loader.command
class CalcCommand(
    lightbulb.SlashCommand,
    name="calc",
    description="Work out the play rating a score would earn",
):
    score = lightbulb.string("score", "The score, e.g. 9123456 or 9'123'456")
    target = lightbulb.string(
        "target", "A chart constant (11.0) or a song/chart", autocomplete=_ac_target
    )
    difficulty = lightbulb.string(
        "difficulty",
        "Pin a specific chart class",
        default=None,
        choices=[
            lightbulb.Choice(name="Past", value="pst"),
            lightbulb.Choice(name="Present", value="prs"),
            lightbulb.Choice(name="Future", value="ftr"),
            lightbulb.Choice(name="Beyond", value="byd"),
            lightbulb.Choice(name="Eternal", value="etr"),
        ],
    )
    ephemeral = lightbulb.boolean(
        "ephemeral", "Show only to you (default: shareable)", default=False
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context, svc: SearchService) -> None:
        # No defer: catalog reads and pure math answer inside the 3s budget, and
        # a direct response uploads the jacket reliably (see /song).
        score = _parse_score(self.score)
        target = (self.target or "").strip()
        if score is None:
            await _respond(ctx, _error(_BAD_SCORE), ephemeral=self.ephemeral)
            return

        async with async_session() as db:
            zone = await effective_zone(
                db,
                ConfigService(),
                guild_id=int(ctx.guild_id) if ctx.guild_id is not None else None,
                channel_id=int(ctx.channel_id),
                user_id=int(ctx.user.id),
            )
            rendered = await _resolve_target(
                db,
                svc,
                score,
                target,
                difficulty=CLASS_OPTIONS.get(self.difficulty or ""),
                locale=ctx.interaction.locale,
                night=is_night(zone),
            )
            await _respond(ctx, rendered, ephemeral=self.ephemeral)


async def _resolve_target(
    db: AsyncSession,
    svc: SearchService,
    score: int,
    target: str,
    *,
    difficulty: DifficultyClass | None,
    locale: object,
    night: bool,
) -> _Rendered:
    if _looks_numeric(target):
        cc = _parse_cc(target)
        return _render_raw_cc(score, cc) if cc is not None else _error(_BAD_CC)
    ref = _CHART_REF_RE.match(target)
    if ref is not None:
        return await _render_chart_ref(db, int(ref.group(1)), score, locale, night)
    res = await svc.resolve(db, target, difficulty=difficulty)
    return await _render(
        db, res, score=score, target=target, locale=locale, night=night
    )


async def _respond(
    ctx: lightbulb.Context, rendered: _Rendered, *, ephemeral: bool
) -> None:
    if rendered.transient:
        ephemeral = True
    await ctx.respond(
        embed=rendered.embed, components=rendered.rows, ephemeral=ephemeral
    )


# --- persistent component listener ------------------------------------------


@loader.listener(hikari.InteractionCreateEvent)
async def _on_calc_component(event: hikari.InteractionCreateEvent) -> None:
    interaction = event.interaction
    if not isinstance(interaction, hikari.ComponentInteraction):
        return
    parts = interaction.custom_id.split(":")
    if parts[0] != _CUSTOM_ID_PREFIX or len(parts) < 4:
        return

    locale = interaction.locale
    score = int(parts[2])
    async with async_session() as db:
        night = is_night(
            await effective_zone(
                db,
                ConfigService(),
                guild_id=int(interaction.guild_id) if interaction.guild_id is not None else None,
                channel_id=int(interaction.channel_id),
                user_id=int(interaction.user.id),
            )
        )
        if parts[1] == "s":
            rendered = await _render_song(
                db, ":".join(parts[3:]), score, locale, night
            )
        else:
            rendered = await _render_chart(db, int(parts[3]), score, locale, night)

    # Edit via edit_initial_response so the builder rebuilds `attachments` from
    # the embed's File, replacing the prior jacket instead of stacking a second.
    await interaction.create_initial_response(
        hikari.ResponseType.DEFERRED_MESSAGE_UPDATE
    )
    await interaction.edit_initial_response(
        embed=rendered.embed,
        components=rendered.rows,
        attachments=hikari.UNDEFINED if rendered.file is not None else None,
    )
