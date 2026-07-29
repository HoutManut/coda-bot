"""/song -- look up a song, a specific chart, or browse by level/CC.

The query grammar and resolution live in :mod:`coda.catalog.search`; this module
is pure presentation: it turns a :data:`~coda.catalog.search.Resolution` into an
embed (mode A song / mode B chart / multi-match pickers), attaches the layered
jacket, and wires the interactive buttons.

Components use a raw ``song:`` custom-id contract dispatched by the persistent
listener below (the approvals pattern), not a lightbulb ``Menu``: a click can
jump song->chart->chart or page a list, all statelessly, by encoding the target
in the id. The listener filters strictly on the ``song:`` prefix so it never
double-handles lightbulb's own components.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections import Counter

import hikari
import lightbulb
from hikari.impl import MessageActionRowBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from coda.catalog.colors import CLASS_COLORS, SIDE_COLORS
from coda.catalog.jackets import (
    chart_jacket,
    display_name,
    is_night,
    song_jacket,
)
from coda.catalog.labels import (
    CLASS_FULL,
    CLASS_OPTIONS,
    CLASS_ORDER,
    CLASS_SHORT,
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
from coda.utils.encoding import decode_level, encode_level

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()

_CUSTOM_ID_PREFIX = "song"
_PAGE_SIZE = 25
# A transient dead end that can't be made ephemeral (it landed on an already
# public message) is auto-removed after this many seconds instead of lingering.
_DEAD_END_TTL = 15

# The one place the accepted grammar is stated to the user -- shared by the
# empty-query prompt and the zero-match reply (handoff 09 §8.3).
_SYNTAX_HELP = (
    "Type a song name, an alias, a level like `10+`, or a CC like `10.9`."
)
_COLOR_INFO = 0x5865F2

_DIFF_CHARS: dict[DifficultyClass, str] = {
    DifficultyClass.PST: "p",
    DifficultyClass.PRS: "r",
    DifficultyClass.FTR: "f",
    DifficultyClass.BYD: "b",
    DifficultyClass.ETR: "e",
}
_CHARS_DIFF = {char: cls for cls, char in _DIFF_CHARS.items()}


# --- pure formatters --------------------------------------------------------


def _cc_paren(rating: int) -> str:
    value = format_cc(rating)
    return f" ({value})" if value is not None else ""


def _duration(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


def _side_name(side_id: int) -> str:
    return Side.from_id(side_id).name.title()


# --- jackets ----------------------------------------------------------------


def _attach_image(embed: hikari.Embed, file: hikari.File | None) -> None:
    """Attach the jacket via the embed's own File: hikari registers the resource
    and uploads it, wiring the ``attachment://`` reference. Passing a bare
    ``attachment://`` string instead makes hikari try to open it as a local file
    (FileNotFoundError), and a separate ``attachment=`` uploads a second copy."""
    if file is not None:
        embed.set_image(file)


# --- embeds -----------------------------------------------------------------


def _song_embed(song: Song, charts: list[SongDifficulty], locale: object) -> hikari.Embed:
    name = display_name(song.name_en, song.name_jp, locale)
    embed = hikari.Embed(title=name, color=SIDE_COLORS[Side.from_id(song.side)])
    if song.name_jp and song.name_jp != name:
        embed.description = song.name_jp

    embed.add_field("Artist", song.artist, inline=True)
    embed.add_field("Pack", song.pack_name, inline=True)
    embed.add_field("BPM", song.bpm, inline=True)
    embed.add_field("Length", _duration(song.time), inline=True)
    embed.add_field("Side", _side_name(song.side), inline=True)
    embed.add_field("Version", song.version, inline=True)

    bullets = _chart_bullets(charts)
    if bullets:
        embed.add_field("Charts", bullets, inline=False)
    if song.jacket_designer:
        embed.set_footer(f"Illustrator: {song.jacket_designer}")
    return embed


def _chart_bullets(charts: list[SongDifficulty]) -> str:
    lines = []
    for chart in sorted_charts(charts):
        if chart.difficulty == DifficultyClass.ERR:
            continue
        label = CLASS_FULL[chart.difficulty]
        lines.append(f"• {label} {decode_level(chart.level)}{_cc_paren(chart.rating)}")
    return "\n".join(lines)


def _chart_embed(song: Song, chart: SongDifficulty, locale: object) -> hikari.Embed:
    name = display_name(
        effective(song, chart, "name_en"), effective(song, chart, "name_jp"), locale
    )
    cls = CLASS_FULL[chart.difficulty]
    embed = hikari.Embed(
        title=f"{name} - {cls}", color=CLASS_COLORS[chart.difficulty]
    )
    cc = format_cc(chart.rating)
    embed.add_field("Level", decode_level(chart.level), inline=True)
    embed.add_field("CC", cc if cc is not None else "?.?", inline=True)
    embed.add_field("Notes", f"{chart.note}", inline=True)
    embed.add_field("Artist", effective(song, chart, "artist"), inline=True)
    embed.add_field("Charter", chart.chart_designer or "-", inline=True)
    embed.add_field("BPM", effective(song, chart, "bpm"), inline=True)
    embed.add_field("Pack", song.pack_name, inline=True)
    embed.add_field("Side", _side_name(effective(song, chart, "side")), inline=True)
    embed.add_field("Version", effective(song, chart, "version"), inline=True)
    illustrator = effective(song, chart, "jacket_designer")
    if illustrator:
        embed.set_footer(f"Illustrator: {illustrator}")
    return embed


# --- component rows ---------------------------------------------------------


def _switch_rows(
    song: Song, charts: list[SongDifficulty], *, current_id: int | None
) -> list[MessageActionRowBuilder]:
    """One row of PST...ETR chart buttons (current disabled); a Song button when a
    chart is shown."""
    row = MessageActionRowBuilder()
    has_button = False
    for chart in sorted_charts(charts):
        if chart.difficulty == DifficultyClass.ERR:
            continue
        row.add_interactive_button(
            hikari.ButtonStyle.SECONDARY,
            f"{_CUSTOM_ID_PREFIX}:c:{chart.id}",
            label=CLASS_SHORT[chart.difficulty],
            is_disabled=chart.id == current_id,
        )
        has_button = True
    rows = [row] if has_button else []
    if current_id is not None:
        back = MessageActionRowBuilder()
        back.add_interactive_button(
            hikari.ButtonStyle.PRIMARY,
            f"{_CUSTOM_ID_PREFIX}:s:{song.song_id}",
            label="←",
        )
        rows.append(back)
    return rows


def _song_button_row(labels: list[tuple[str, str]]) -> MessageActionRowBuilder:
    """A row of song buttons: (label, song_id)."""
    row = MessageActionRowBuilder()
    for label, song_id in labels[:5]:
        row.add_interactive_button(
            hikari.ButtonStyle.SECONDARY,
            f"{_CUSTOM_ID_PREFIX}:s:{song_id}",
            label=label[:80],
        )
    return row


def _chart_button_row(labels: list[tuple[str, int]]) -> MessageActionRowBuilder:
    """A row of chart buttons: (label, difficulty_id)."""
    row = MessageActionRowBuilder()
    for label, difficulty_id in labels[:5]:
        row.add_interactive_button(
            hikari.ButtonStyle.SECONDARY,
            f"{_CUSTOM_ID_PREFIX}:c:{difficulty_id}",
            label=label[:80],
        )
    return row


def _list_rows(
    entries: list[tuple[SongDifficulty, Song]],
    *,
    token: str,
    diff_char: str,
    page: int,
    total_pages: int,
    locale: object,
) -> list[MessageActionRowBuilder]:
    select_row = MessageActionRowBuilder()
    menu = select_row.add_text_menu(
        f"{_CUSTOM_ID_PREFIX}:selc", placeholder="Open a chart", min_values=1, max_values=1
    )
    for chart, song in entries:
        name = display_name(
            effective(song, chart, "name_en"), effective(song, chart, "name_jp"), locale
        )
        label = (
            f"{name} — {CLASS_SHORT[chart.difficulty]} "
            f"{decode_level(chart.level)}{_cc_paren(chart.rating)}"
        )
        menu.add_option(label[:100], str(chart.id))

    if total_pages <= 1:
        return [select_row]

    pager = MessageActionRowBuilder()
    pager.add_interactive_button(
        hikari.ButtonStyle.SECONDARY,
        f"{_CUSTOM_ID_PREFIX}:pg:{page - 1}:{token}:{diff_char}",
        label="◀ Prev",
        is_disabled=page <= 0,
    )
    pager.add_interactive_button(
        hikari.ButtonStyle.SECONDARY,
        f"{_CUSTOM_ID_PREFIX}:pgc",
        label=f"Page {page + 1}/{total_pages}",
        is_disabled=True,
    )
    pager.add_interactive_button(
        hikari.ButtonStyle.SECONDARY,
        f"{_CUSTOM_ID_PREFIX}:pg:{page + 1}:{token}:{diff_char}",
        label="Next ▶",
        is_disabled=page >= total_pages - 1,
    )
    return [select_row, pager]


# --- rendered payload -------------------------------------------------------


class _Rendered:
    """An embed + optional jacket + component rows, ready to send or edit-into."""

    def __init__(
        self,
        embed: hikari.Embed,
        file: hikari.File | None,
        rows: list[MessageActionRowBuilder],
        *,
        transient: bool = False,
    ) -> None:
        self.embed = embed
        self.file = file
        self.rows = rows
        # A dead end (no result / error): never worth leaving in a channel.
        # `_respond` forces it ephemeral; the component path deletes it after a
        # timeout when it lands on a message that is already public.
        self.transient = transient


def _prompt(reason: str | None) -> _Rendered:
    """The empty-query helper -- the one place the grammar is offered. Not a
    dead end: shown when the user opens ``/song`` without a query."""
    text = reason or _SYNTAX_HELP
    return _Rendered(
        hikari.Embed(title="Song search", description=text, color=_COLOR_INFO),
        None,
        [],
    )


def _dead_end(query: str, reason: str | None) -> _Rendered:
    """A search that found nothing. Says so plainly for the given query -- no
    grammar dump (that belongs on the empty-query prompt) -- and is transient."""
    text = reason or f"Nothing matched **{query}**."
    return _Rendered(
        hikari.Embed(title="No results", description=text, color=_COLOR_INFO),
        None,
        [],
        transient=True,
    )


async def _render_song(
    db: AsyncSession, song_id: str, locale: object, night: bool
) -> _Rendered:
    song, charts = await load_song(db, song_id)
    embed = _song_embed(song, charts, locale)
    file = song_jacket(song, locale, night)
    _attach_image(embed, file)
    return _Rendered(embed, file, _switch_rows(song, charts, current_id=None))


async def _render_chart(
    db: AsyncSession, difficulty_id: int, locale: object, night: bool
) -> _Rendered:
    song, chart = await load_chart(db, difficulty_id)
    _, charts = await load_song(db, song.song_id)
    embed = _chart_embed(song, chart, locale)
    file = chart_jacket(song, chart, locale, night)
    _attach_image(embed, file)
    return _Rendered(embed, file, _switch_rows(song, charts, current_id=difficulty_id))


async def _render_song_dupes(
    db: AsyncSession, song_ids: list[str], locale: object
) -> _Rendered:
    songs = [await db.get(Song, sid) for sid in song_ids]
    labels = [
        (f"{display_name(s.name_en, s.name_jp, locale)} — {s.artist} ({s.pack_name})", s.song_id)
        for s in songs
        if s is not None
    ]
    embed = hikari.Embed(
        title="Which one?",
        description="A few songs share that name — pick one:",
        color=_COLOR_INFO,
    )
    return _Rendered(embed, None, [_song_button_row(labels)])


async def _render_chart_pick(
    db: AsyncSession, difficulty_ids: list[int], locale: object
) -> _Rendered:
    entries = await load_charts_ordered(db, difficulty_ids)
    labels = [
        (
            f"{display_name(effective(s, c, 'name_en'), effective(s, c, 'name_jp'), locale)}"
            f" — Beyond {decode_level(c.level)}",
            c.id,
        )
        for c, s in entries
    ]
    embed = hikari.Embed(
        title="Which Beyond?",
        description="That song has two Beyond charts — pick one:",
        color=_COLOR_INFO,
    )
    return _Rendered(embed, None, [_chart_button_row(labels)])


async def _render_did_you_mean(
    db: AsyncSession, res: DidYouMean, locale: object
) -> _Rendered:
    song_labels: list[tuple[str, str]] = []
    chart_labels: list[tuple[str, int]] = []
    for cand in res.candidates:
        if cand.difficulty_id is None:
            song = await db.get(Song, cand.song_id)
            if song is not None:
                song_labels.append(
                    (
                        f"{display_name(song.name_en, song.name_jp, locale)} — "
                        f"{song.artist} ({song.pack_name})",
                        song.song_id,
                    )
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
        title="Did you mean…?",
        description="No exact match. Closest results:",
        color=_COLOR_INFO,
    )
    rows: list[MessageActionRowBuilder] = []
    if song_labels:
        rows.append(_song_button_row(song_labels))
    if chart_labels:
        rows.append(_chart_button_row(chart_labels))
    return _Rendered(embed, None, rows)


async def _render_list(
    db: AsyncSession,
    ids: list[int],
    *,
    token: str,
    diff_char: str,
    page: int,
    locale: object,
) -> _Rendered:
    total_pages = max(1, (len(ids) + _PAGE_SIZE - 1) // _PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    page_ids = ids[page * _PAGE_SIZE : (page + 1) * _PAGE_SIZE]
    entries = await load_charts_ordered(db, page_ids)
    embed = hikari.Embed(
        title=f"{len(ids)} charts",
        description="Pick one from the menu below.",
        color=_COLOR_INFO,
    )
    rows = _list_rows(
        entries,
        token=token,
        diff_char=diff_char,
        page=page,
        total_pages=total_pages,
        locale=locale,
    )
    return _Rendered(embed, None, rows)


async def _render(
    db: AsyncSession,
    res: Resolution,
    *,
    query: str,
    difficulty: DifficultyClass | None,
    locale: object,
    night: bool,
) -> _Rendered:
    match res:
        case SongHit(song_id=song_id, missing_class=missing):
            rendered = await _render_song(db, song_id, locale, night)
            if missing is not None:
                rendered.embed.description = (
                    f"*This song has no {CLASS_FULL[missing]} chart.*"
                )
            return rendered
        case ChartHit(difficulty_id=cid):
            return await _render_chart(db, cid, locale, night)
        case SongDupes(song_ids=ids):
            return await _render_song_dupes(db, ids, locale)
        case ChartPick(difficulty_ids=ids):
            return await _render_chart_pick(db, ids, locale)
        case ChartList(difficulty_ids=ids):
            return await _render_list(
                db,
                ids,
                token=query.strip().lower(),
                diff_char=_DIFF_CHARS.get(difficulty, "_") if difficulty else "_",
                page=0,
                locale=locale,
            )
        case DidYouMean():
            return await _render_did_you_mean(db, res, locale)
        case NoMatch(reason=reason):
            return _dead_end(query, reason)
    return _prompt(None)


# --- command ----------------------------------------------------------------


async def _ac_song(ctx: lightbulb.AutocompleteContext[str]) -> None:
    """Discriminated song rows, a level/CC echo row, or the newest songs."""
    typed = str(ctx.focused.value or "").strip()
    async with async_session() as db:
        choices = await _autocomplete_choices(db, typed)
    await ctx.respond(choices[:25])


async def _autocomplete_choices(
    db: AsyncSession, typed: str
) -> list[tuple[str, str]]:
    if not typed:
        return await _newest_songs(db)
    echo = _numeric_echo(typed)
    if echo is not None:
        return echo
    return await _song_rows(db, typed)


def _numeric_echo(typed: str) -> list[tuple[str, str]] | None:
    """One selectable echo row confirming a level/CC interpretation, or None."""
    norm = typed.lower()
    if re.fullmatch(r"\d{1,2}\+?", norm):
        if decode_level(encode_level(norm)) == "?":
            return None
        return [(f"Level {norm} — list all charts", norm)]
    if re.fullmatch(r"\d{1,2}\.\d+", norm):
        whole, frac = norm.split(".")
        return [(f"CC {whole}.{frac[0]} — list all charts", norm)]
    return None


async def _newest_songs(db: AsyncSession) -> list[tuple[str, str]]:
    rows = (
        await db.execute(
            select(Song.song_id, Song.name_en, Song.artist, Song.pack_name)
            .order_by(Song.idx.desc())
            .limit(25)
        )
    ).all()
    candidates = [
        (sid, name, artist, pack)
        for sid, name, artist, pack in rows
        if not _is_delisted_name(name)
    ]
    return _labeled_rows(candidates)


async def _song_rows(db: AsyncSession, typed: str) -> list[tuple[str, str]]:
    candidates = await SearchService().candidate_songs(db, typed, limit=25)
    return _labeled_rows(candidates)


def _labeled_rows(
    candidates: list[tuple[str, str, str, str]],
) -> list[tuple[str, str]]:
    """Row is the song name alone; only a shared name gets the discriminating
    ``— artist (pack)`` suffix (dropping the pack if it overflows 100 chars)."""
    counts = Counter(name for _sid, name, _artist, _pack in candidates)
    rows: list[tuple[str, str]] = []
    for song_id, name, artist, pack in candidates:
        if counts[name] > 1:
            label = f"{name} — {artist} ({pack})"
            if len(label) > 100:
                label = f"{name} — {artist}"
        else:
            label = name
        rows.append((label[:100], song_id))
    return rows


def _is_delisted_name(name: str) -> bool:
    return len(name) >= 2 and name.startswith("_") and name.endswith("_")


@loader.command
class SongCommand(
    lightbulb.SlashCommand,
    name="song",
    description="Look up a song, a chart, or browse by level/CC",
):
    q = lightbulb.string(
        "q", "Song name, alias, level (10+), or CC (10.9)", autocomplete=_ac_song
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
        query = (self.q or "").strip()
        locale = ctx.interaction.locale
        night = is_night(int(ctx.user.id))
        difficulty = CLASS_OPTIONS.get(self.difficulty) if self.difficulty else None

        # No defer: /song makes no external calls, so it answers within the 3s
        # budget, and a direct (create) response uploads the jacket reliably --
        # the post-defer edit path does not.
        async with async_session() as db:
            if not query:
                rendered = _prompt(None)
            else:
                res = await svc.resolve(db, query, difficulty=difficulty)
                rendered = await _render(
                    db, res, query=query, difficulty=difficulty,
                    locale=locale, night=night,
                )
            await _respond(ctx, rendered, ephemeral=self.ephemeral)


async def _respond(
    ctx: lightbulb.Context, rendered: _Rendered, *, ephemeral: bool
) -> None:
    # A dead end never clutters a channel: force the initial response ephemeral
    # (always allowed on create), overriding the user's share choice. Because
    # this is the first response, ephemeral always succeeds -- no timeout needed.
    if rendered.transient:
        ephemeral = True
    # The jacket rides on the embed (set_image(File)); hikari uploads it. No
    # attachments= here -- that would upload a second copy.
    await ctx.respond(
        embed=rendered.embed, components=rendered.rows, ephemeral=ephemeral
    )


# --- persistent component listener ------------------------------------------


@loader.listener(hikari.InteractionCreateEvent)
async def _on_song_component(event: hikari.InteractionCreateEvent) -> None:
    interaction = event.interaction
    if not isinstance(interaction, hikari.ComponentInteraction):
        return
    parts = interaction.custom_id.split(":")
    if not parts or parts[0] != _CUSTOM_ID_PREFIX or len(parts) < 2:
        return

    locale = interaction.locale
    night = is_night(int(interaction.user.id))
    rendered = await _dispatch_component(interaction, parts, locale, night)
    if rendered is None:
        return
    # Edit via edit_initial_response, not MESSAGE_UPDATE: only the edit builder
    # rebuilds `attachments` from the embed's File, replacing the prior jacket
    # instead of leaving it behind as a second image. The embed carries the new
    # jacket (set_image(File)); attachments=None clears it when a view has none.
    await interaction.create_initial_response(
        hikari.ResponseType.DEFERRED_MESSAGE_UPDATE
    )
    await interaction.edit_initial_response(
        embed=rendered.embed,
        components=rendered.rows,
        attachments=hikari.UNDEFINED if rendered.file is not None else None,
    )
    # A dead end reached via a button edits a message that is already public and
    # can't be made ephemeral after the fact -- so tear it down after a timeout
    # rather than leave the error sitting in the channel. (An ephemeral source
    # message needs nothing; Discord drops it on its own.)
    if rendered.transient and not _is_ephemeral(interaction.message):
        asyncio.create_task(_delete_after(interaction, _DEAD_END_TTL))


def _is_ephemeral(message: hikari.Message | None) -> bool:
    return message is not None and bool(
        message.flags & hikari.MessageFlag.EPHEMERAL
    )


async def _delete_after(
    interaction: hikari.ComponentInteraction, delay: float
) -> None:
    await asyncio.sleep(delay)
    try:
        await interaction.delete_initial_response()
    except hikari.NotFoundError:
        pass  # already gone (dismissed, or another edit deleted it)


async def _dispatch_component(
    interaction: hikari.ComponentInteraction,
    parts: list[str],
    locale: object,
    night: bool,
) -> _Rendered | None:
    kind = parts[1]
    async with async_session() as db:
        if kind == "s":
            return await _render_song(db, ":".join(parts[2:]), locale, night)
        if kind == "c":
            return await _render_chart(db, int(parts[2]), locale, night)
        if kind == "selc":
            return await _render_chart(db, int(interaction.values[0]), locale, night)
        if kind == "pg":
            return await _render_pager(db, parts, locale)
    return None


async def _render_pager(
    db: AsyncSession, parts: list[str], locale: object
) -> _Rendered | None:
    page = int(parts[2])
    token = parts[3]
    diff_char = parts[4] if len(parts) > 4 else "_"
    difficulty = _CHARS_DIFF.get(diff_char)
    res = await SearchService().resolve(db, token, difficulty=difficulty)
    if not isinstance(res, ChartList):
        return None
    return await _render_list(
        db, res.difficulty_ids, token=token, diff_char=diff_char, page=page, locale=locale
    )
