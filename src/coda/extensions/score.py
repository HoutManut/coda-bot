"""/score -- your best play on a chart, and where it ranks.

Resolution is the shared seam under ``/song`` (:mod:`coda.catalog.search`), so
the query grammar is the same one; only the presentation differs. Everything
shown comes from stored rows, so this command never polls and never touches
lowiro: a personal best is history, and ``play_scores`` is the only history that
will ever exist.

A query that pins no class opens the highest class the player has a score on --
the chart they got furthest on is the one they meant. The class buttons then
offer only their other SCORED charts, since a button leading to "no score" would
replace a real result with a dead end.

Components use the raw ``score:`` custom-id contract dispatched below, and every
id carries the invoker: a click renders that person's scores or nothing, so a
passer-by can never drive someone else's lookup or spill their own into it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import hikari
import lightbulb
from hikari.impl import MessageActionRowBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from coda.catalog.autocomplete import song_choices
from coda.catalog.jackets import display_name, is_night
from coda.catalog.labels import CLASS_OPTIONS, class_full, class_short, sorted_charts
from coda.catalog.lookup import load_chart, load_song
from coda.catalog.resolution import effective
from coda.catalog.spoilers import chart_spoilered
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
from coda.db.enums import DifficultyClass
from coda.db.models import Song, SongDifficulty
from coda.db.session import async_session
from coda.scores import PotentialService, TrackingService
from coda.scores.potential_stat import StatMode, rank_line
from coda.scores.best import best_play, scored_charts
from coda.scores.embed import score_embed
from coda.settings import ConfigService
from coda.settings.zone import effective_zone
from coda.utils.render import Rendered, apply, button_row, notice, respond

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()

_CUSTOM_ID_PREFIX = "score"

_NOT_REGISTERED = "You're not registered yet. Run `/register` first."
_NOT_YOURS = "That's someone else's lookup. Run `/score` to see your own."
_PROMPT = (
    "Type a song name or an alias."
)
_TOO_BROAD = (
    "That matched a lot of charts."
)
_TRACKING_OFF = (
    "Score tracking is off for your account, so nothing new is being recorded. "
    "Turn it back on with `/tracking`."
)
# The one thing a player reads "no score" wrong about: the bot has no backfill,
# so a chart they cleared last year is blank until they play it again.
_NO_HISTORY = (
    "-# The bot only knows plays it has seen since you registered."
)


@dataclass(frozen=True)
class _Viewer:
    """Whose scores are being rendered, and how they want them shown."""

    account_id: int
    discord_id: int
    tracking_enabled: bool
    depth: StatMode
    locale: object
    night: bool
    potential: PotentialService


async def _ac_song(ctx: lightbulb.AutocompleteContext[str]) -> None:
    """Song rows only -- a level/CC browse has no single chart to score."""
    typed = str(ctx.focused.value or "").strip()
    async with async_session() as db:
        choices = await song_choices(db, typed, numeric_echo=False)
    await ctx.respond(choices[:25])


@loader.command
class ScoreCommand(
    lightbulb.SlashCommand,
    name="score",
    description="Show your best score on a chart",
):
    q = lightbulb.string("q", "Song name or alias", autocomplete=_ac_song)
    difficulty = lightbulb.string(
        "difficulty",
        "The difficulty of the chart",
        default=None,
        choices=[
            lightbulb.Choice(name="Past", value="pst"),
            lightbulb.Choice(name="Present", value="prs"),
            lightbulb.Choice(name="Future", value="ftr"),
            lightbulb.Choice(name="Eternal", value="etr"),
            lightbulb.Choice(name="Beyond", value="byd"),
        ],
    )
    # Unset, not False: a spoilered chart then decides the default for itself,
    # while an explicit false still shares it.
    ephemeral = lightbulb.boolean(
        "ephemeral",
        "Show only to you (default: false)",
        default=None,
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context, search: SearchService) -> None:
        query = (self.q or "").strip()
        difficulty = CLASS_OPTIONS.get(self.difficulty) if self.difficulty else None

        # No defer, as in /song: every read here is indexed and local, so the
        # reply lands well inside the 3s budget, and a direct (create) response
        # uploads the jacket reliably where the post-defer edit path does not.
        async with async_session() as db:
            viewer = await _viewer(db, ctx.interaction)
            if viewer is None:
                await ctx.respond(_NOT_REGISTERED, ephemeral=True)
                return
            if not query:
                rendered = notice("Score lookup", _PROMPT)
            else:
                res = await search.resolve(db, query, difficulty=difficulty)
                rendered = await _render(db, res, query=query, viewer=viewer)
            await respond(ctx, rendered, ephemeral=self.ephemeral)


async def _viewer(
    db: AsyncSession,
    interaction: hikari.CommandInteraction | hikari.ComponentInteraction,
) -> _Viewer | None:
    """Assemble the caller's context, or None when they are not registered."""
    tracking = TrackingService()
    link = await tracking.link_of(db, int(interaction.user.id))
    if link is None:
        return None
    account = await tracking.account_of(db, link)

    settings = ConfigService()
    guild_id = int(interaction.guild_id) if interaction.guild_id is not None else None
    channel_id = int(interaction.channel_id)
    discord_id = int(interaction.user.id)
    zone = await effective_zone(
        db, settings, guild_id=guild_id, channel_id=channel_id, user_id=discord_id
    )
    depth = await settings.resolve(
        db,
        "score_rank_depth",
        guild_id=guild_id,
        channel_id=channel_id,
        user_id=discord_id,
        is_dm=guild_id is None,
    )
    return _Viewer(
        account_id=account.id,
        discord_id=discord_id,
        tracking_enabled=account.tracking_enabled,
        depth=depth,
        locale=interaction.locale,
        night=is_night(zone),
        potential=PotentialService(),
    )


# --- rendering --------------------------------------------------------------


async def _render(
    db: AsyncSession, res: Resolution, *, query: str, viewer: _Viewer
) -> Rendered:
    match res:
        case ChartHit(difficulty_id=difficulty_id):
            return await _render_chart(db, difficulty_id, viewer)
        case SongHit(song_id=song_id, missing_class=missing):
            return await _render_song(db, song_id, viewer, missing)
        case SongDupes(song_ids=song_ids):
            return await _render_song_dupes(db, song_ids, viewer)
        case ChartPick(difficulty_ids=difficulty_ids):
            return await _render_chart_pick(db, difficulty_ids, viewer)
        case DidYouMean():
            return await _render_did_you_mean(db, res, viewer)
        case ChartList():
            return notice("Too many charts", _TOO_BROAD, transient=True)
        case NoMatch(reason=reason):
            return notice(
                "No results", reason or f"Nothing matched **{query}**.", transient=True
            )
    return notice("Score lookup", _PROMPT)


async def _render_chart(
    db: AsyncSession, difficulty_id: int, viewer: _Viewer
) -> Rendered:
    """The best stored play on one chart, ranked against the account's others."""
    song, chart = await load_chart(db, difficulty_id)
    best = await best_play(db, viewer.account_id, difficulty_id)
    if best is None:
        name = _song_name(song, chart, viewer)
        return _no_score(f"{name} — {class_full(chart.difficulty, chart.alt)}", viewer)

    embed, file = score_embed(
        best, chart, song, locale=viewer.locale, night=viewer.night
    )
    line = await rank_line(
        db, viewer.potential, chart, mode=viewer.depth, account_id=viewer.account_id
    )
    if line is not None:
        embed.description = f"{embed.description}\n{line}"

    _, charts = await load_song(db, song.song_id)
    scored = await scored_charts(db, viewer.account_id, [c.id for c in charts])
    return Rendered(
        embed,
        file,
        _switch_rows(charts, scored, viewer, current_id=difficulty_id),
        spoiler=chart_spoilered(song, chart),
    )


async def _render_song(
    db: AsyncSession,
    song_id: str,
    viewer: _Viewer,
    missing: DifficultyClass | None,
) -> Rendered:
    """The song's highest class this account has a score on."""
    song, charts = await load_song(db, song_id)
    scored = await scored_charts(db, viewer.account_id, [c.id for c in charts])
    chart = _highest_scored(charts, scored)
    if chart is None:
        name = display_name(song.name_en, song.name_jp, viewer.locale)
        return _no_score(name, viewer)

    rendered = await _render_chart(db, chart.id, viewer)
    if missing is not None:
        rendered.embed.description = (
            f"-# This song has no {class_full(missing)} chart.\n"
            f"{rendered.embed.description}"
        )
    return rendered


def _highest_scored(
    charts: list[SongDifficulty], scored: set[int]
) -> SongDifficulty | None:
    """The hardest class with a stored play, reading the display order upwards."""
    for chart in reversed(sorted_charts(charts)):
        if chart.difficulty is not DifficultyClass.ERR and chart.id in scored:
            return chart
    return None


def _no_score(target: str, viewer: _Viewer) -> Rendered:
    reason = _TRACKING_OFF if not viewer.tracking_enabled else _NO_HISTORY
    return notice(
        "No score yet", f"Nothing recorded on **{target}**.\n{reason}", transient=True
    )


def _song_name(song: Song, chart: SongDifficulty, viewer: _Viewer) -> str:
    return display_name(
        effective(song, chart, "name_en"),
        effective(song, chart, "name_jp"),
        viewer.locale,
    )


# --- pickers ----------------------------------------------------------------


def _picker(title: str, description: str, buttons: list[tuple[str, str]]) -> Rendered:
    """An ambiguity payload: an explainer, plus one row of choices."""
    rendered = notice(title, description)
    rendered.rows = [button_row(buttons)]
    return rendered


async def _render_song_dupes(
    db: AsyncSession, song_ids: list[str], viewer: _Viewer
) -> Rendered:
    songs = [await db.get(Song, song_id) for song_id in song_ids]
    buttons = [
        (
            f"{display_name(s.name_en, s.name_jp, viewer.locale)} — {s.artist}",
            _song_id(s.song_id, viewer),
        )
        for s in songs
        if s is not None
    ]
    return _picker("Which one?", "A few songs share that name.", buttons)


async def _render_chart_pick(
    db: AsyncSession, difficulty_ids: list[int], viewer: _Viewer
) -> Rendered:
    buttons = []
    for difficulty_id in difficulty_ids:
        song, chart = await load_chart(db, difficulty_id)
        buttons.append(
            (f"{_song_name(song, chart, viewer)} — Beyond", _chart_id(chart.id, viewer))
        )
    return _picker(
        "Which Beyond?", "That song has two Beyond charts.", buttons
    )


async def _render_did_you_mean(
    db: AsyncSession, res: DidYouMean, viewer: _Viewer
) -> Rendered:
    buttons = []
    for candidate in res.candidates:
        if candidate.difficulty_id is None:
            song = await db.get(Song, candidate.song_id)
            if song is not None:
                buttons.append(
                    (
                        display_name(song.name_en, song.name_jp, viewer.locale),
                        _song_id(song.song_id, viewer),
                    )
                )
            continue
        song, chart = await load_chart(db, candidate.difficulty_id)
        buttons.append(
            (
                f"{_song_name(song, chart, viewer)} — "
                f"{class_short(chart.difficulty, chart.alt)}",
                _chart_id(chart.id, viewer),
            )
        )
    return _picker("Did you mean?", "No exact match. Closest results:", buttons)


def _switch_rows(
    charts: list[SongDifficulty],
    scored: set[int],
    viewer: _Viewer,
    *,
    current_id: int,
) -> list[MessageActionRowBuilder]:
    """A button per scored chart of this song, the one on screen disabled."""
    playable = [chart for chart in sorted_charts(charts) if chart.id in scored]
    if len(playable) < 2:
        return []
    row = MessageActionRowBuilder()
    for chart in playable:
        row.add_interactive_button(
            hikari.ButtonStyle.SECONDARY,
            _chart_id(chart.id, viewer),
            label=class_short(chart.difficulty, chart.alt),
            is_disabled=chart.id == current_id,
        )
    return [row]


# The invoker sits ahead of the payload: a song id may itself contain a colon,
# so it has to be the part that runs to the end of the id.
def _chart_id(difficulty_id: int, viewer: _Viewer) -> str:
    return f"{_CUSTOM_ID_PREFIX}:c:{viewer.discord_id}:{difficulty_id}"


def _song_id(song_id: str, viewer: _Viewer) -> str:
    return f"{_CUSTOM_ID_PREFIX}:s:{viewer.discord_id}:{song_id}"


# --- persistent component listener ------------------------------------------


@loader.listener(hikari.InteractionCreateEvent)
async def _on_score_component(event: hikari.InteractionCreateEvent) -> None:
    interaction = event.interaction
    if not isinstance(interaction, hikari.ComponentInteraction):
        return
    parts = interaction.custom_id.split(":")
    if parts[0] != _CUSTOM_ID_PREFIX or len(parts) < 4:
        return

    if int(parts[2]) != int(interaction.user.id):
        await interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_CREATE,
            _NOT_YOURS,
            flags=hikari.MessageFlag.EPHEMERAL,
        )
        return

    rendered = await _dispatch_component(interaction, parts)
    if rendered is None:
        return
    await apply(interaction, rendered)


async def _dispatch_component(
    interaction: hikari.ComponentInteraction, parts: list[str]
) -> Rendered | None:
    async with async_session() as db:
        viewer = await _viewer(db, interaction)
        if viewer is None:
            return notice("No longer registered", _NOT_REGISTERED, transient=True)
        if parts[1] == "c":
            return await _render_chart(db, int(parts[3]), viewer)
        if parts[1] == "s":
            return await _render_song(db, ":".join(parts[3:]), viewer, None)
    return None
