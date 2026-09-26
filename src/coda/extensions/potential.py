"""/potential -- the counted pool behind your PTT, and the clear review it needs.

Self-only by design: the figure is a rating, and invocation is the consent that
makes showing one acceptable at all (``potential.md`` §Traps). The passive
surfaces that suppress a hidden PTT are the ones nobody asked for; this is not
one of them.

The review card is the only place ``play_scores.clear_override`` is ever set,
and it is pull-only -- reached from this command's own button, never pushed at a
player from a score embed (``d-clear-bonus-impossible-friend-path``).

Components use the raw ``pot:`` custom-id contract dispatched below, and every
id carries the invoker: a click renders that person's pool or nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

import hikari
import lightbulb
from hikari.impl import MessageActionRowBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from coda.catalog.colors import class_color
from coda.catalog.jackets import chart_jacket, display_name, is_night
from coda.catalog.labels import chart_rating_line, class_short
from coda.catalog.resolution import effective
from coda.catalog.spoilers import chart_spoilered
from coda.db.session import async_session
from coda.scores import PotentialService, TrackingService
from coda.scores.clears import (
    ReviewMode,
    accept_assumptions,
    reviewable,
    set_clear_override,
)
from coda.scores.potential import POOL, PotentialEntry, PotentialResult
from coda.settings import ConfigService
from coda.settings.zone import effective_zone
from coda.utils.render import Rendered, apply, is_ephemeral, notice, respond
from coda.utils.scoring import ASSUMED_MARK, ClearBasis, format_rating, format_score

loader = lightbulb.Loader()

_CUSTOM_ID_PREFIX = "pot"
_PAGE = 10

# Short enough to leave the custom id well inside Discord's 100 characters.
_MODE_CODE: dict[str, ReviewMode] = {"u": "unconfirmed", "a": "all"}
_MODE_LETTER = {mode: letter for letter, mode in _MODE_CODE.items()}

_NOT_REGISTERED = "You're not registered yet. Run `/register` first."
_NOT_YOURS = "That's someone else's pool. Run `/potential` to see your own."
_NO_PLAYS = "Nothing to average yet. No stored play has a rateable chart."
_TRACKING_OFF = "Score tracking is off, so this pool stops here until you `/tracking` it back on."

_NOTHING_REVIEWABLE = "Nothing to confirm."
_NOTHING_UNCONFIRMED = "Nothing left to confirm."
_END_OF_QUEUE = "This is the end of the queue."


@dataclass(frozen=True)
class _Viewer:
    """Whose pool is being rendered, and how they want it shown."""

    account_id: int
    discord_id: int
    tracking_enabled: bool
    # A public board can't be dismissed by the reader, so it carries its own
    # delete button; an ephemeral one already has Discord's.
    public: bool
    locale: object
    night: bool
    potential: PotentialService


@loader.command
class PotentialCommand(
    lightbulb.SlashCommand,
    name="potential",
    description="Show the plays your potential is averaged from",
):
    # A rating is the caller's own business by default; sharing it is opt-in.
    ephemeral = lightbulb.boolean(
        "ephemeral",
        "Show only to you (default: true)",
        default=True,
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        # No defer: every read is one indexed scan of the caller's own rows, and
        # a direct response uploads the jacket reliably where an edit does not.
        async with async_session() as db:
            viewer = await _viewer(db, ctx.interaction, public=not self.ephemeral)
            if viewer is None:
                await ctx.respond(_NOT_REGISTERED, ephemeral=True)
                return
            rendered = await _render_pool(db, viewer, page=0)
            await respond(ctx, rendered, ephemeral=self.ephemeral)


async def _viewer(
    db: AsyncSession,
    interaction: hikari.CommandInteraction | hikari.ComponentInteraction,
    *,
    public: bool,
) -> _Viewer | None:
    """Assemble the caller's context, or None when they are not registered."""
    tracking = TrackingService()
    link = await tracking.link_of(db, int(interaction.user.id))
    if link is None:
        return None
    account = await tracking.account_of(db, link)

    guild_id = int(interaction.guild_id) if interaction.guild_id is not None else None
    zone = await effective_zone(
        db,
        ConfigService(),
        guild_id=guild_id,
        channel_id=int(interaction.channel_id),
        user_id=int(interaction.user.id),
    )
    return _Viewer(
        account_id=account.id,
        discord_id=int(interaction.user.id),
        tracking_enabled=account.tracking_enabled,
        public=public,
        locale=interaction.locale,
        night=is_night(zone),
        potential=PotentialService(),
    )


# --- the pool listing --------------------------------------------------------


async def _render_pool(db: AsyncSession, viewer: _Viewer, *, page: int) -> Rendered:
    """One page of the counted pool, headed by the potential it averages to."""
    result = await viewer.potential.compute(db, viewer.account_id, limit=POOL)
    if not result.entries:
        # The excluded counts, not just "no plays": a player whose only stored
        # plays are on TBA charts has plenty of history and an empty pool, and
        # would otherwise read this as the bot having lost them.
        return notice(
            "Potential", "\n".join([_NO_PLAYS] + _notes(result, viewer)), transient=True
        )

    pages = -(-len(result.entries) // _PAGE)
    page = max(0, min(page, pages - 1))
    window = result.entries[page * _PAGE : (page + 1) * _PAGE]
    notes = _notes(result, viewer)

    # The figure IS the title: `as_container` renders a title as `##`, so a
    # separate heading for it would stack two of the same level.
    embed = hikari.Embed(
        title=_headline(result),
        description="\n".join(
            [_entry_line(entry, viewer) for entry in window]
            + ([""] + notes if notes else [])
        ),
        # The top entry's class, not the page's: an accent that changed on every
        # page turn would read as a different view rather than the same one.
        color=class_color(result.entries[0].song_difficulty.difficulty),
    )
    if pages > 1:
        embed.set_footer(f"Page {page + 1} of {pages}")
    return Rendered(
        embed,
        rows=[_pool_row(result, viewer, page=page, pages=pages)],
        spoiler=any(
            chart_spoilered(entry.song, entry.song_difficulty) for entry in window
        ),
    )


def _headline(result: PotentialResult) -> str:
    """The figure, at the game's own fixed 3 decimals rather than trimmed."""
    mark = ASSUMED_MARK if result.assumed_count else ""
    return f"{mark}{result.potential:.3f}"


def _entry_line(entry: PotentialEntry, viewer: _Viewer) -> str:
    chart = entry.song_difficulty
    name = display_name(
        effective(entry.song, chart, "name_en"),
        effective(entry.song, chart, "name_jp"),
        viewer.locale,
    )
    return (
        f"`#{entry.rank:>2}` **{name}** · {class_short(chart.difficulty, chart.alt)}"
        f" · {_rating(entry)}"
    )


def _rating(entry: PotentialEntry) -> str:
    mark = ASSUMED_MARK if entry.clear.basis is ClearBasis.ASSUMED else ""
    return f"**{mark}{format_rating(entry.play_rating)}**"


def _notes(result: PotentialResult, viewer: _Viewer) -> list[str]:
    """The caveats that explain a figure the game disagrees with."""
    notes = []
    if result.assumed_count:
        notes.append(
            f"-# {ASSUMED_MARK} {result.assumed_count} of {len(result.entries)} "
            "counted plays have an assumed clear status."
        )
    if result.tba_excluded_count:
        notes.append(
            f"-# {result.tba_excluded_count} chart(s) skipped: no constant yet."
        )
    if result.unresolved_excluded_count:
        notes.append(
            f"-# {result.unresolved_excluded_count} play(s) skipped: chart "
            "unknown to the bot."
        )
    if not viewer.tracking_enabled:
        notes.append(f"-# {_TRACKING_OFF}")
    return notes


def _pool_row(
    result: PotentialResult, viewer: _Viewer, *, page: int, pages: int
) -> MessageActionRowBuilder:
    """Paging, plus the one entry point into the review queue."""
    row = MessageActionRowBuilder()
    row.add_interactive_button(
        hikari.ButtonStyle.SECONDARY,
        _pool_id(page - 1, viewer),
        label="‹",
        is_disabled=page == 0,
    )
    row.add_interactive_button(
        hikari.ButtonStyle.SECONDARY,
        _pool_id(page + 1, viewer),
        label="›",
        is_disabled=page >= pages - 1,
    )
    unconfirmed = reviewable(result, "unconfirmed")
    if unconfirmed:
        row.add_interactive_button(
            hikari.ButtonStyle.PRIMARY,
            _review_id("unconfirmed", 0, viewer),
            label=f"Review {len(unconfirmed)} assumed",
        )
    elif reviewable(result, "all"):
        row.add_interactive_button(
            hikari.ButtonStyle.SECONDARY,
            _review_id("all", 0, viewer),
            label="Edit clear status",
        )
    return _with_dismiss(row, viewer)


def _with_dismiss(
    row: MessageActionRowBuilder, viewer: _Viewer
) -> MessageActionRowBuilder:
    """A shared board has no reader-side dismiss, so its owner gets a delete."""
    # "Dismiss", not "Clear": this command already spends that word on clear
    # status, and two meanings in one row would collide.
    if viewer.public:
        row.add_interactive_button(
            hikari.ButtonStyle.SECONDARY, _dismiss_id(viewer), label="Dismiss"
        )
    return row


# --- the review card ---------------------------------------------------------


async def _render_review(
    db: AsyncSession, viewer: _Viewer, mode: ReviewMode, index: int
) -> Rendered:
    """One play's clear status, asked as a question.

    The queue is rebuilt from source on every interaction rather than carried in
    the custom id: answering a row can promote a previously-buried play into a
    chart's winning slot, and a remembered list would hide it.
    """
    result = await viewer.potential.compute(db, viewer.account_id, limit=POOL)
    queue = reviewable(result, mode)
    if not queue or index >= len(queue):
        return _review_done(viewer, mode, exhausted=bool(queue))

    index = max(0, index)
    entry = queue[index]
    chart = entry.song_difficulty
    embed = hikari.Embed(
        title=display_name(
            effective(entry.song, chart, "name_en"),
            effective(entry.song, chart, "name_jp"),
            viewer.locale,
        ),
        description="\n".join(
            [
                format_score(entry.score),
                chart_rating_line(entry.score, chart, entry.clear),
                "",
                _status_line(entry),
            ]
        ),
        color=class_color(chart.difficulty, chart.alt),
    )
    embed.set_footer(f"#{entry.rank} in your pool · {index + 1} of {len(queue)}")
    file = chart_jacket(entry.song, chart, viewer.locale, viewer.night)
    if file is not None:
        embed.set_thumbnail(file)
    return Rendered(
        embed,
        file,
        _review_rows(entry, queue, viewer, mode=mode, index=index),
        spoiler=chart_spoilered(entry.song, chart),
    )


def _status_line(entry: PotentialEntry) -> str:
    state = "cleared" if entry.clear.cleared else "not cleared"
    if entry.clear.basis is ClearBasis.OVERRIDE:
        return f"You marked this play **{state}**."
    return f"Assumed **{state}**."


def _review_rows(
    entry: PotentialEntry,
    queue: list[PotentialEntry],
    viewer: _Viewer,
    *,
    mode: ReviewMode,
    index: int,
) -> list[MessageActionRowBuilder]:
    """The answer, then the ways out of the queue."""
    answered = entry.clear.basis is ClearBasis.OVERRIDE
    answers = MessageActionRowBuilder()
    answers.add_interactive_button(
        hikari.ButtonStyle.SUCCESS,
        _answer_id(mode, index, entry.play_score_id, True, viewer),
        label="Cleared",
        is_disabled=answered and entry.clear.cleared,
    )
    answers.add_interactive_button(
        hikari.ButtonStyle.DANGER,
        _answer_id(mode, index, entry.play_score_id, False, viewer),
        label="Failed",
        is_disabled=answered and not entry.clear.cleared,
    )
    answers.add_interactive_button(
        hikari.ButtonStyle.SECONDARY,
        _review_id(mode, index + 1, viewer),
        label="Skip",
    )

    exits = MessageActionRowBuilder()
    if mode == "unconfirmed" and len(queue) > 1:
        exits.add_interactive_button(
            hikari.ButtonStyle.SECONDARY,
            _accept_all_id(viewer),
            label=f"Accept all {len(queue)} guesses",
        )
    exits.add_interactive_button(
        hikari.ButtonStyle.SECONDARY, _pool_id(0, viewer), label="Back"
    )
    return [answers, _with_dismiss(exits, viewer)]


def _review_done(viewer: _Viewer, mode: ReviewMode, *, exhausted: bool) -> Rendered:
    """The end of a pass, or a queue that was empty to begin with."""
    if exhausted:
        body = _END_OF_QUEUE
    else:
        body = _NOTHING_UNCONFIRMED if mode == "unconfirmed" else _NOTHING_REVIEWABLE
    rendered = notice("Clear review", body)
    rendered.rows = [
        _with_dismiss(
            MessageActionRowBuilder().add_interactive_button(
                hikari.ButtonStyle.SECONDARY, _pool_id(0, viewer), label="Back"
            ),
            viewer,
        )
    ]
    return rendered


# --- custom ids --------------------------------------------------------------

# The invoker sits ahead of the payload, as in `/score`: the gate reads it
# without having to know which of the five shapes below it is looking at.


def _pool_id(page: int, viewer: _Viewer) -> str:
    return f"{_CUSTOM_ID_PREFIX}:p:{viewer.discord_id}:{page}"


def _review_id(mode: ReviewMode, index: int, viewer: _Viewer) -> str:
    return f"{_CUSTOM_ID_PREFIX}:r:{viewer.discord_id}:{_MODE_LETTER[mode]}:{index}"


def _answer_id(
    mode: ReviewMode, index: int, play_score_id: int, cleared: bool, viewer: _Viewer
) -> str:
    return (
        f"{_CUSTOM_ID_PREFIX}:s:{viewer.discord_id}:{_MODE_LETTER[mode]}:{index}"
        f":{play_score_id}:{int(cleared)}"
    )


def _dismiss_id(viewer: _Viewer) -> str:
    return f"{_CUSTOM_ID_PREFIX}:d:{viewer.discord_id}"


def _accept_all_id(viewer: _Viewer) -> str:
    return f"{_CUSTOM_ID_PREFIX}:x:{viewer.discord_id}"


# --- persistent component listener -------------------------------------------


@loader.listener(hikari.InteractionCreateEvent)
async def _on_potential_component(event: hikari.InteractionCreateEvent) -> None:
    interaction = event.interaction
    if not isinstance(interaction, hikari.ComponentInteraction):
        return
    parts = interaction.custom_id.split(":")
    if parts[0] != _CUSTOM_ID_PREFIX or len(parts) < 3:
        return

    if int(parts[2]) != int(interaction.user.id):
        await interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_CREATE,
            _NOT_YOURS,
            flags=hikari.MessageFlag.EPHEMERAL,
        )
        return

    if parts[1] == "d":
        # Deferred update first: deleting the source message without answering
        # the interaction leaves the clicker an "interaction failed" toast.
        await interaction.create_initial_response(
            hikari.ResponseType.DEFERRED_MESSAGE_UPDATE
        )
        await interaction.delete_initial_response()
        return

    rendered = await _dispatch_component(interaction, parts)
    if rendered is not None:
        await apply(interaction, rendered)


async def _dispatch_component(
    interaction: hikari.ComponentInteraction, parts: list[str]
) -> Rendered | None:
    async with async_session() as db:
        viewer = await _viewer(
            db, interaction, public=not is_ephemeral(interaction.message)
        )
        if viewer is None:
            return notice("No longer registered", _NOT_REGISTERED, transient=True)
        match parts[1]:
            case "p":
                return await _render_pool(db, viewer, page=int(parts[3]))
            case "r":
                return await _render_review(
                    db, viewer, _MODE_CODE[parts[3]], int(parts[4])
                )
            case "s":
                mode, index = _MODE_CODE[parts[3]], int(parts[4])
                await set_clear_override(
                    db, viewer.account_id, int(parts[5]), bool(int(parts[6]))
                )
                # Same index, not the next one: in the unconfirmed queue the row
                # just answered drops out, so this IS the next play, while in
                # `all` mode it re-renders the answer that was just recorded.
                return await _render_review(db, viewer, mode, index)
            case "x":
                result = await viewer.potential.compute(
                    db, viewer.account_id, limit=POOL
                )
                await accept_assumptions(
                    db, viewer.account_id, reviewable(result, "unconfirmed")
                )
                return await _render_pool(db, viewer, page=0)
    return None
