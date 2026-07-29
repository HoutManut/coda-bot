"""/chardle -- Wordle over the Arcaea catalog.

Two input paths, both stateless: the slash command, and a reply to the board
message. Neither keeps game state in memory, so a restart never kills a game.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import hikari
import lightbulb
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from coda.catalog.search import SearchService
from coda.chardle import board as board_builder
from coda.chardle import render, schedule, sticky, tiers, transport
from coda.chardle.channels import ChardleChannelService
from coda.chardle.columns import CANONICAL_ORDER, LABELS
from coda.chardle.feedback import Windows
from coda.chardle.guess import (
    Accepted,
    Duplicate,
    GuessService,
    Invalid,
    Searched,
)
from coda.chardle.puzzle import EmptyPool, PuzzleService
from coda.chardle.session import SessionService
from coda.chardle.stats import StatsService
from coda.db.enums import ChardleState, DifficultyClass, Side
from coda.db.models import ChardleGuess, ChardlePuzzle, ChardleSession
from coda.db.session import async_session
from coda.settings import ConfigService
from coda.settings.zone import effective_zone
from coda.utils.encoding import encode_level
from coda.utils.permissions import can_send_in, can_view, everyone_can_view

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()
chardle_group = lightbulb.Group("chardle", "Guess the chart")

_COLOR_OK = 0x57F287
_COLOR_ERR = 0xED4245
_MAX_CHOICES = 25

_NO_BOARD = "No Chardle board here. Start one with `/chardle play`."
_FINISHED = "That board is already finished."
_NOT_YOUR_DAILY = "That's someone else's daily."
_ALREADY_LIVE = (
    "This channel already has a board running. Finish it, or end it with "
    "`/chardle end`."
)
_EMPTY_POOL = "No songs match that configuration. Try a different level or side."
_CANT_SEE_CHANNEL = (
    "Chardle threads open in this server's Chardle channel that you don't have access to. Start it here with "
    "`thread: No thread`, or ask an admin for access to that channel."
)
_NO_DM_HOME = (
    "This server hasn't set a Chardle channel, so your daily goes to DMs but "
    "I can't DM you. Open your DMs, or ask a server admin to set one with "
    "`/chardle channel` so it can go in a private thread instead."
)
_HIDDEN_DM_HOME = (
    "Your daily would go in a thread in this server's Chardle channel, but you can't access it. "
    "I also can't DM you. Open your "
    "DMs, or ask an admin for access to that channel."
)
_NO_THREAD_HOME = (
    "Chardle threads all live in one channel, and this server hasn't set one. "
    "A server admin can pick it with `/chardle channel`. Until then, start the "
    "board here with `thread: No thread`."
)
_DAILY_DONE = "You've already played today's Chardle."
_NO_BOARD_HOME = (
    "I can't post a board here. Give me **Send Messages** and **Embed Links** in "
    "this channel, or start the board somewhere else."
)

# After this, anyone may end a board -- see _may_end.
_PUBLIC_END_AFTER = timedelta(minutes=15)

_THREAD_NONE = "none"
_THREAD_PUBLIC = "public"
_THREAD_PRIVATE = "private"


def _embed(title: str, description: str, *, ok: bool = True) -> hikari.Embed:
    return hikari.Embed(
        title=title, description=description, color=_COLOR_OK if ok else _COLOR_ERR
    )


def _link(guild_id: int | None, channel_id: int, message_id: int) -> str:
    return (
        f"https://discord.com/channels/{guild_id or '@me'}/{channel_id}/{message_id}"
    )


# --- settings ---------------------------------------------------------------


@dataclass(frozen=True)
class _View:
    """How to draw a board: the two tuning windows, plus the debug switch."""

    windows: Windows
    debug: bool


async def _view(
    db, settings: ConfigService, *, guild_id: int | None, channel_id: int, user_id: int
) -> _View:
    async def value(key: str):
        return await settings.resolve(
            db,
            key,
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=user_id,
            is_dm=guild_id is None,
        )

    return _View(
        windows=Windows(
            bpm=int(await value("chardle_bpm_window")),
            note=int(await value("chardle_note_window")),
        ),
        debug=str(await value("chardle_debug_board")) == "on",
    )


async def _epoch(db, settings: ConfigService) -> date:
    raw = await settings.resolve(
        db, "chardle_epoch", guild_id=None, channel_id=0, user_id=0, is_dm=True
    )
    return date.fromisoformat(str(raw))


# --- board plumbing ---------------------------------------------------------


async def _render(
    db, puzzle: ChardlePuzzle, session: ChardleSession, view: _View
) -> tuple[hikari.Embed, hikari.Bytes | None]:
    """The board embed and, unless this is the debug view, its image."""
    board = await board_builder.build(db, puzzle, session, view.windows)
    # Compositing a board is megapixel-scale CPU work plus a jacket decode, and
    # it runs on every guess -- off the event loop it goes.
    return await asyncio.to_thread(
        render.board_embed, board, debug=view.debug, revision=len(board.rows)
    )


async def _refresh(
    app: hikari.RESTAware, db, puzzle: ChardlePuzzle, session: ChardleSession, view: _View
) -> None:
    """Edit the board in place. A dead board message must not kill the game."""
    embed, image = await _render(db, puzzle, session, view)
    try:
        await app.rest.edit_message(
            session.board_channel_id,
            session.message_id,
            embed=embed,
            # The embed already carries the image, and hikari uploads embed
            # resources on top of anything passed here -- naming it again would
            # send the board twice. Only the imageless debug view needs this, to
            # clear the attachment the previous render left behind.
            attachment=hikari.UNDEFINED if image else None,
        )
    except hikari.HikariError:
        logger.info("chardle: cannot edit board %s", session.id)


async def _puzzle_of(db, session: ChardleSession) -> ChardlePuzzle:
    return await db.get(ChardlePuzzle, session.puzzle_id)


# --- /chardle daily ---------------------------------------------------------


@loader.command
@chardle_group.register
class Daily(
    lightbulb.SlashCommand, name="daily", description="Today's Chardle puzzle"
):
    @lightbulb.invoke
    async def invoke(
        self,
        ctx: lightbulb.Context,
        puzzles: PuzzleService,
        sessions: SessionService,
        settings: ConfigService,
        channels: ChardleChannelService,
    ) -> None:
        await ctx.defer(ephemeral=True)
        await ctx.respond(
            await start_daily(
                ctx.client.app,
                user=ctx.user,
                member=ctx.member,
                guild_id=int(ctx.guild_id) if ctx.guild_id is not None else None,
                invoked_channel_id=int(ctx.channel_id),
                puzzles=puzzles,
                sessions=sessions,
                settings=settings,
                channels=channels,
            )
        )


async def start_daily(
    app: hikari.RESTAware,
    *,
    user: hikari.User,
    member: hikari.Member | None,
    guild_id: int | None,
    invoked_channel_id: int,
    puzzles: PuzzleService,
    sessions: SessionService,
    settings: ConfigService,
    channels: ChardleChannelService,
) -> hikari.Embed:
    """Open (or resume) the caller's daily and return the ephemeral reply.

    Shared by ``/chardle daily`` and the scoreboard's Play button, which differ
    only in how the caller reached it.
    """
    user_id = int(user.id)
    async with async_session() as db:
        await sessions.expire_dailies_of(db, user_id)
        epoch = await _epoch(db, settings)
        tz = await effective_zone(
            db,
            settings,
            guild_id=guild_id,
            channel_id=invoked_channel_id,
            user_id=user_id,
        )
        number = schedule.puzzle_number(epoch, tz, datetime.now(UTC))
        try:
            puzzle = await puzzles.daily(db, epoch, number)
        except EmptyPool:
            return _embed("Nope", _EMPTY_POOL, ok=False)

        existing = await sessions.daily_of(db, puzzle.id, user_id)
        if existing is not None:
            return _resume(existing, guild_id)

        configured_id = await channels.channel_id(db, guild_id)
        # A thread under a channel they cannot see would be invisible to them,
        # so drop to the DM leg rather than post a board nobody can reach.
        parent_id = configured_id if _reachable(app, configured_id, member) else None
        view = await _view(
            db,
            settings,
            guild_id=guild_id,
            channel_id=invoked_channel_id,
            user_id=user_id,
        )
        posted = await _post_daily_board(
            app,
            db,
            channels,
            puzzle=puzzle,
            view=view,
            user=user,
            guild_id=guild_id,
            parent_channel_id=parent_id,
        )
        if posted is None:
            return _embed(
                "Nowhere private to play",
                _no_transport(configured_id, parent_id),
                ok=False,
            )
        board_channel_id, message_id = posted

        try:
            opened = await sessions.open_daily(
                db,
                puzzle,
                discord_id=user_id,
                guild_id=guild_id,
                board_channel_id=board_channel_id,
                message_id=message_id,
                expires_at=schedule.expires_at(epoch, tz, number),
            )
        except IntegrityError:
            await db.rollback()
            await _delete_quietly(app, board_channel_id, message_id)
            return _embed("Already played", _DAILY_DONE, ok=False)

        if guild_id is not None:
            await sticky.refresh(
                app, db, channels, settings, guild_id=guild_id, puzzle=puzzle
            )
    return _resume(opened, guild_id)


async def _post_daily_board(
    app: hikari.RESTAware,
    db,
    channels: ChardleChannelService,
    *,
    puzzle: ChardlePuzzle,
    view: _View,
    user: hikari.User,
    guild_id: int | None,
    parent_channel_id: int | None,
) -> tuple[int, int] | None:
    """Resolve a private destination and put the board in it.

    Retries once without the remembered thread: a thread can be deleted or
    locked between the fetch that approved it and the send, and losing a daily
    to that is worse than one extra round trip.
    """
    remembered = (
        await channels.player_thread(db, guild_id, int(user.id))
        if guild_id is not None
        else None
    )
    for reuse in (remembered, None):
        resolved = await transport.resolve_daily(
            app,
            user=user,
            guild_id=guild_id,
            parent_channel_id=parent_channel_id,
            reuse_channel_id=reuse,
        )
        if resolved is None:
            return None

        channel_id = resolved.destination.channel_id
        draft = ChardleSession(
            puzzle_id=puzzle.id,
            is_daily=True,
            state=ChardleState.PLAYING,
            message_id=0,
            board_channel_id=channel_id,
        )
        embed, _ = await _render(db, puzzle, draft, view)
        try:
            message = await app.rest.create_message(channel_id, embed=embed)
        except hikari.HikariError:
            logger.info("chardle: cannot post a daily board in %s", channel_id)
            # Retrying only helps when the destination was a *remembered* thread
            # that went bad. A thread we just opened and cannot post in is a
            # permission problem, and looping would open a second orphan.
            if reuse is None or guild_id is None or resolved.created:
                return None
            await channels.forget_thread(db, guild_id, int(user.id))
            continue

        if guild_id is not None:
            await _remember_transport(db, channels, guild_id, user, resolved)
        return channel_id, int(message.id)
    return None


async def _remember_transport(
    db,
    channels: ChardleChannelService,
    guild_id: int,
    user: hikari.User,
    resolved: transport.Resolved,
) -> None:
    """Keep the thread id if we opened one; drop it if we fell back to a DM, so
    the next daily does not re-fetch a channel that cannot host a guild board."""
    if resolved.created:
        await channels.remember_thread(
            db, guild_id, int(user.id), resolved.destination.channel_id
        )
    elif not resolved.destination.is_thread:
        await channels.forget_thread(db, guild_id, int(user.id))


def _reachable(
    app: hikari.RESTAware, channel_id: int | None, member: hikari.Member | None
) -> bool:
    """Whether a thread opened under ``channel_id`` would be reachable by
    ``member``. Only False rejects -- see :func:`_can_post`."""
    if channel_id is None or member is None:
        return True
    if not isinstance(app, hikari.CacheAware):
        return True
    return can_view(app, channel_id, member) is not False


def _no_transport(configured_id: int | None, parent_id: int | None) -> str:
    """Why the daily has nowhere to go. Three causes, three answers: one needs an
    admin to set a channel, one needs access to the channel that exists, and only
    the third is about thread permissions."""
    if parent_id is not None:
        return transport.NO_TRANSPORT
    return _NO_DM_HOME if configured_id is None else _HIDDEN_DM_HOME


async def _delete_quietly(
    app: hikari.RESTAware, channel_id: int, message_id: int
) -> None:
    try:
        await app.rest.delete_message(channel_id, message_id)
    except hikari.HikariError:
        logger.info("chardle: could not clean up board message %s", message_id)


async def _delete_quietly_channel(app: hikari.RESTAware, channel_id: int) -> None:
    try:
        await app.rest.delete_channel(channel_id)
    except hikari.HikariError:
        logger.info("chardle: could not clean up thread %s", channel_id)


def _resume(session: ChardleSession, guild_id: int | None) -> hikari.Embed:
    where = _link(guild_id, session.board_channel_id, session.message_id)
    if session.state is not ChardleState.PLAYING:
        return _embed("Already played", f"{_DAILY_DONE} [Board]({where})")
    return _embed(
        "Your daily is ready",
        f"[Open the board]({where}) and reply to it, or use `/chardle guess`.",
    )


# --- /chardle play ----------------------------------------------------------


@loader.command
@chardle_group.register
class Play(
    lightbulb.SlashCommand,
    name="play",
    description="Start a free-play board in this channel",
):
    tier = lightbulb.string(
        "difficulty",
        "Which difficulty to guess in",
        default=tiers.DEFAULT_TIER,
        choices=[
            lightbulb.Choice(name=tiers.get(name).pick_label, value=name)
            for name in tiers.playable_names()
        ],
    )
    level = lightbulb.string("level", "Restrict to one level, e.g. 9 or 10+", default="")
    side = lightbulb.string(
        "side",
        "Restrict to one side",
        default="",
        choices=[
            lightbulb.Choice(name=member.value.title(), value=member.value)
            for member in Side
        ],
    )
    attempts = lightbulb.integer(
        "attempts",
        "Size of the shared attempt pool",
        default=tiers.FREE_ATTEMPTS,
        min_value=1,
        max_value=tiers.MAX_FREE_ATTEMPTS,
    )
    thread = lightbulb.string(
        "room",
        "Put the board in its own room",
        default=_THREAD_NONE,
        choices=[
            lightbulb.Choice(name="No thread", value=_THREAD_NONE),
            lightbulb.Choice(name="Public thread", value=_THREAD_PUBLIC),
            lightbulb.Choice(name="Private thread", value=_THREAD_PRIVATE),
        ],
    )

    @lightbulb.invoke
    async def invoke(
        self,
        ctx: lightbulb.Context,
        puzzles: PuzzleService,
        sessions: SessionService,
        settings: ConfigService,
        channels: ChardleChannelService,
    ) -> None:
        await ctx.defer(ephemeral=True)
        invoked_channel_id = int(ctx.channel_id)
        guild_id = int(ctx.guild_id) if ctx.guild_id is not None else None
        wants_thread = guild_id is not None and self.thread != _THREAD_NONE

        async with async_session() as db:
            # Threads all hang off the guild's Chardle channel, wherever the
            # command was typed. Without one there is nowhere to put a thread.
            thread_parent = await channels.channel_id(db, guild_id)
            if wants_thread and thread_parent is None:
                await ctx.respond(_embed("No Chardle channel", _NO_THREAD_HOME, ok=False))
                return
            if wants_thread and not _reachable(
                ctx.client.app, thread_parent, ctx.member
            ):
                await ctx.respond(
                    _embed("Out of reach", _CANT_SEE_CHANNEL, ok=False)
                )
                return

            # A thread board gets its own channel id, so it never contends for
            # this channel's one live slot -- only check the slot we will occupy.
            if (
                not wants_thread
                and await sessions.live_in_channel(db, invoked_channel_id) is not None
            ):
                await ctx.respond(_embed("Busy", _ALREADY_LIVE, ok=False))
                return

            try:
                puzzle = await puzzles.free(
                    db,
                    tier_name=self.tier,
                    level=encode_level(self.level) if self.level else None,
                    side=_side_id(self.side),
                    max_attempts=self.attempts,
                    now=datetime.now(UTC),
                    epoch=await _epoch(db, settings),
                )
            except (EmptyPool, ValueError):
                await ctx.respond(_embed("Nope", _EMPTY_POOL, ok=False))
                return

            view = await _view(
                db,
                settings,
                guild_id=guild_id,
                channel_id=invoked_channel_id,
                user_id=int(ctx.user.id),
            )
            board_channel_id = invoked_channel_id
            if wants_thread:
                assert thread_parent is not None  # guarded above
                opened = await transport.open_free_thread(
                    ctx.client.app,
                    thread_parent,
                    ctx.user,
                    private=self.thread == _THREAD_PRIVATE,
                )
                if opened is None:
                    await ctx.respond(
                        _embed("No thread", transport.NO_THREAD, ok=False)
                    )
                    return
                board_channel_id = opened.channel_id

            # Ownership follows the board, not the invocation: the CHECK demands
            # channel_id == board_channel_id on a free-play session.
            draft = ChardleSession(
                puzzle_id=puzzle.id,
                is_daily=False,
                state=ChardleState.PLAYING,
                message_id=0,
                channel_id=board_channel_id,
                board_channel_id=board_channel_id,
            )
            embed, _ = await _render(db, puzzle, draft, view)
            try:
                message = await ctx.client.app.rest.create_message(
                    board_channel_id, embed=embed
                )
            except hikari.HikariError:
                logger.info("chardle: cannot post a board in %s", board_channel_id)
                if wants_thread:
                    await _delete_quietly_channel(ctx.client.app, board_channel_id)
                await ctx.respond(
                    _embed(
                        "Can't post there",
                        transport.NO_THREAD if wants_thread else _NO_BOARD_HOME,
                        ok=False,
                    )
                )
                return
            try:
                await sessions.open_free(
                    db,
                    puzzle,
                    channel_id=board_channel_id,
                    guild_id=guild_id,
                    message_id=int(message.id),
                )
            except IntegrityError:
                await db.rollback()
                await _delete_quietly(ctx.client.app, board_channel_id, int(message.id))
                await ctx.respond(_embed("Busy", _ALREADY_LIVE, ok=False))
                return

        await ctx.respond(
            _embed(
                "Board up",
                _board_up(guild_id, board_channel_id, int(message.id))
                if board_channel_id != invoked_channel_id
                else "Reply to the board message with a song name, or use "
                "`/chardle guess`.",
            )
        )


def _board_up(guild_id: int | None, channel_id: int, message_id: int) -> str:
    """The board is not where the command was typed, so ``/chardle guess`` here
    would find nothing -- say where to go rather than widen the lookup."""
    return (
        f"Go to your [Board](<{_link(guild_id, channel_id, message_id)}>). "
        "Reply to it with a song name, or use `/chardle guess` there."
    )


_SIDE_IDS: dict[str, int] = {
    Side.from_id(side_id).value: side_id for side_id in range(len(Side))
}


def _side_id(value: str) -> int | None:
    return _SIDE_IDS.get(value)


# --- /chardle guess ---------------------------------------------------------


async def _ac_song(ctx: lightbulb.AutocompleteContext[str]) -> None:
    typed = str(ctx.focused.value or "")
    if not typed:
        await ctx.respond([])
        return
    interaction = ctx.interaction
    async with async_session() as db:
        classes = await _live_tier_classes(
            db, int(interaction.channel_id), int(interaction.user.id)
        )
        rows = await SearchService().candidate_songs(
            db, typed, limit=_MAX_CHOICES, classes=classes
        )
    await ctx.respond([(f"{name} — {artist}"[:100], name[:100]) for _, name, artist, _ in rows])


async def _live_tier_classes(
    db, channel_id: int, user_id: int
) -> tuple[DifficultyClass, ...] | None:
    """The difficulties the live board plays, so a clue filter like ``level>10``
    reads the puzzle's own chart. No live board -> unscoped.

    Constructed inline rather than injected: lightbulb hands autocomplete
    callbacks no DI container, which is why ``SearchService`` is built here too.
    """
    session = await SessionService().live_in_channel(db, channel_id)
    if session is None:
        session = await _live_daily(db, user_id)
    if session is None:
        return None
    puzzle = await _puzzle_of(db, session)
    return tuple(tiers.get(puzzle.tier).classes)


@loader.command
@chardle_group.register
class Guess(
    lightbulb.SlashCommand, name="guess", description="Guess a song on the live board"
):
    song = lightbulb.string("song", "The song you're guessing", autocomplete=_ac_song)

    @lightbulb.invoke
    async def invoke(
        self,
        ctx: lightbulb.Context,
        sessions: SessionService,
        guesses: GuessService,
        settings: ConfigService,
        channels: ChardleChannelService,
    ) -> None:
        await ctx.defer(ephemeral=True)
        channel_id = int(ctx.channel_id)
        user_id = int(ctx.user.id)

        async with async_session() as db:
            session = await sessions.live_in_channel(db, channel_id)
            if session is None:
                session = await _live_daily(db, user_id)
            if session is None:
                await ctx.respond(_embed("Nothing to guess at", _NO_BOARD, ok=False))
                return
            if session.is_daily and session.discord_id != user_id:
                await ctx.respond(_embed("Not yours", _NOT_YOUR_DAILY, ok=False))
                return

            async with sessions.lock(session.id):
                outcome, embed = await _apply_guess(
                    db, ctx.client.app, session, guesses, settings, self.song, user_id
                )
            await _sticky_after(
                ctx.client.app, db, channels, settings, session, outcome
            )

        await ctx.respond(embed)


async def _live_daily(db, discord_id: int) -> ChardleSession | None:
    return await db.scalar(
        select(ChardleSession).where(
            ChardleSession.discord_id == discord_id,
            ChardleSession.state == ChardleState.PLAYING,
            _unexpired(),
        )
    )


def _unexpired():
    """Only ``/chardle daily`` closes stale dailies on invocation, so every other
    entry point has to refuse a rolled-over board itself rather than wait for the
    half-hourly sweep."""
    return (ChardleSession.expires_at.is_(None)) | (
        ChardleSession.expires_at > datetime.now(UTC)
    )


async def _apply_guess(
    db,
    app: hikari.RESTAware,
    session: ChardleSession,
    guesses: GuessService,
    settings: ConfigService,
    typed: str,
    discord_id: int,
) -> tuple[object, hikari.Embed]:
    """Submit one guess and re-render the board. Caller holds the session lock."""
    await db.refresh(session)
    puzzle = await _puzzle_of(db, session)
    if session.state is not ChardleState.PLAYING:
        return None, _embed("Finished", _FINISHED, ok=False)

    outcome = await guesses.submit(
        db,
        puzzle,
        session,
        tiers.get(puzzle.tier),
        typed,
        discord_id=discord_id,
    )
    view = await _view(
        db,
        settings,
        guild_id=session.guild_id,
        channel_id=session.board_channel_id,
        user_id=discord_id,
    )

    match outcome:
        case Invalid(reason=reason):
            return outcome, _embed("Invalid guess", reason, ok=False)
        case Duplicate():
            return outcome, _embed(
                "Already guessed", "That chart is already on the board.", ok=False
            )
        case Searched():
            return outcome, _embed("Search", outcome.describe(), ok=False)
        case Accepted(state=state):
            await _refresh(app, db, puzzle, session, view)
            if state is ChardleState.WON:
                sessions_note = "Solved it."
            elif state is ChardleState.LOST:
                sessions_note = "That was the last attempt."
            else:
                sessions_note = "Guess recorded."
            return outcome, _embed("Guessed", sessions_note)
        case _:
            return outcome, _embed("Guessed", "Guess recorded.")


async def _sticky_after(
    app: hikari.RESTAware,
    db,
    channels: ChardleChannelService,
    settings: ConfigService,
    session: ChardleSession,
    outcome: object,
) -> None:
    """Update the guild scoreboard once a daily finishes.

    Called **outside** the per-board lock: it costs a REST edit plus a query per
    player on the board, and holding a player's lock across that would stall
    their next guess for no ordering benefit. Unlike the poster's per-destination
    lock, nothing here depends on send order.
    """
    if not isinstance(outcome, Accepted) or outcome.state is ChardleState.PLAYING:
        return
    if not session.is_daily or session.guild_id is None:
        return
    await sticky.refresh(
        app,
        db,
        channels,
        settings,
        guild_id=session.guild_id,
        puzzle=await _puzzle_of(db, session),
    )


# --- /chardle end -----------------------------------------------------------


@loader.command
@chardle_group.register
class End(
    lightbulb.SlashCommand,
    name="end",
    description="End this channel's free-play board",
):
    @lightbulb.invoke
    async def invoke(
        self, ctx: lightbulb.Context, sessions: SessionService, settings: ConfigService
    ) -> None:
        await ctx.defer(ephemeral=True)
        channel_id = int(ctx.channel_id)
        async with async_session() as db:
            session = await sessions.live_in_channel(db, channel_id)
            if session is None:
                await ctx.respond(_embed("Nothing to end", _NO_BOARD, ok=False))
                return
            if not await _may_end(db, ctx, session):
                await ctx.respond(
                    _embed(
                        "Nope",
                        "Only someone who has played on this board, or someone "
                        "with **Manage Messages**, can end it yet. Anyone can "
                        f"end it {_PUBLIC_END_AFTER.seconds // 60} minutes "
                        "after it started.",
                        ok=False,
                    )
                )
                return
            # Held across the close so a guess waiting on this lock wakes to an
            # already-ended board and refuses, rather than editing the message
            # after the final render.
            async with sessions.lock(session.id):
                puzzle = await _puzzle_of(db, session)
                await sessions.end(db, session)
                view = await _view(
                    db,
                    settings,
                    guild_id=session.guild_id,
                    channel_id=channel_id,
                    user_id=int(ctx.user.id),
                )
                await _refresh(ctx.client.app, db, puzzle, session, view)
            sessions.release(session.id)

        await ctx.respond(_embed("Ended", "Board closed."))


async def _may_end(db, ctx: lightbulb.Context, session: ChardleSession) -> bool:
    """A shared board is not the property of whoever typed first, and it is not
    free for a passer-by to delete either.

    Free play stores no starter -- the CHECK forces ``discord_id IS NULL`` on a
    channel-owned session -- so "played on this board" stands in for "started
    it", plus anyone holding Manage Messages.
    """
    member = ctx.member
    if member is None:
        return True
    if member.permissions & hikari.Permissions.MANAGE_MESSAGES:
        return True
    # No real board runs this long, so past the window the board is abandoned
    # and anyone may free the channel's one live slot. The abandon sweep is the
    # backstop for when nobody is around to ask.
    if datetime.now(UTC) - session.started_at >= _PUBLIC_END_AFTER:
        return True
    players = (
        await db.execute(
            select(ChardleGuess.discord_id).where(
                ChardleGuess.session_id == session.id
            )
        )
    ).scalars().all()
    return not players or int(ctx.user.id) in {int(p) for p in players}


# --- /chardle channel -------------------------------------------------------


@loader.command
@chardle_group.register
class Channel(
    lightbulb.SlashCommand,
    name="channel",
    description="Set the channel Chardle lives in (admin)",
):
    # The native picker is right here: any text channel is a valid choice, and
    # there is no allowlist to check membership against.
    # default=None, not hikari.UNDEFINED: lightbulb builds an UNDEFINED default
    # as a *required* option, which would make "leave it off" unreachable.
    channel = lightbulb.channel(
        "channel",
        "Channel to host Chardle in — leave off to see the current one",
        channel_types=[hikari.ChannelType.GUILD_TEXT],
        default=None,
    )

    @lightbulb.invoke
    async def invoke(
        self, ctx: lightbulb.Context, channels: ChardleChannelService
    ) -> None:
        if ctx.guild_id is None:
            await ctx.respond(
                _embed("Not here", "Use this in a server.", ok=False), ephemeral=True
            )
            return
        if not _is_admin(ctx):
            await ctx.respond(
                _embed("Nope", "You need **Manage Channels** to do that.", ok=False),
                ephemeral=True,
            )
            return

        guild_id = int(ctx.guild_id)
        if self.channel is None:
            await self._show(ctx, channels, guild_id)
            return

        channel_id = int(self.channel.id)
        if not _can_post(ctx, channel_id):
            await ctx.respond(
                _embed(
                    "Can't post there",
                    f"You don't have permission to send messages in "
                    f"<#{channel_id}>.",
                    ok=False,
                ),
                ephemeral=True,
            )
            return

        async with async_session() as db:
            await channels.set_channel(db, guild_id, channel_id, int(ctx.user.id))
        await ctx.respond(
            _embed(
                "Chardle channel set",
                _CHANNEL_SET.format(channel=channel_id)
                + _restricted_note(ctx.client.app, channel_id),
            ),
            ephemeral=True,
        )

    async def _show(
        self, ctx: lightbulb.Context, channels: ChardleChannelService, guild_id: int
    ) -> None:
        async with async_session() as db:
            current = await channels.get(db, guild_id)
        if current is None:
            await ctx.respond(
                _embed("No Chardle channel", _CHANNEL_UNSET), ephemeral=True
            )
            return
        menu = _clear_channel_menu(channels, guild_id, int(ctx.user.id))
        await ctx.respond(
            # Re-checked on every show, not just on set: a channel's permissions
            # can be locked down long after Chardle was pointed at it.
            _embed(
                "Chardle channel",
                f"Chardle threads live in <#{current.channel_id}>."
                + _restricted_note(ctx.client.app, current.channel_id),
            ),
            components=menu,
            ephemeral=True,
        )
        menu.attach_persistent(ctx.client, timeout=60)


_CHANNEL_SET = (
    "Chardle threads now live in <#{channel}>. "
    "I need **Create Public Threads**, **Create Private Threads** and "
    "**Send Messages in Threads** there."
)
# Appended to _CHANNEL_SET, so it opens mid-message.
_CHANNEL_RESTRICTED = (
    "\n\n⚠️ **@everyone can't see <#{channel}>.** Members who can't reach it get "
    "their daily in DMs and can't start a threaded boards. If that is intended "
    "it's fine, otherwise pick a channel your players can see."
)
_CHANNEL_UNSET = (
    "Chardle boards go wherever they're started, and threads are off: dailies "
    "land in DMs and `/chardle play` can't open one. Set a channel to gather "
    "every thread in one place and get a daily scoreboard."
)


def _clear_channel_menu(
    channels: ChardleChannelService, guild_id: int, caller_id: int
) -> lightbulb.components.Menu:
    menu = lightbulb.components.Menu()

    async def on_clear(mctx: lightbulb.components.MenuContext) -> None:
        if mctx.user.id != caller_id:
            await mctx.respond("This button isn't for you.", ephemeral=True)
            return
        async with async_session() as db:
            await channels.clear(db, guild_id)
        await mctx.respond(
            _embed("Cleared", _CHANNEL_UNSET), edit=True, components=[]
        )
        mctx.stop_interacting()

    menu.add_interactive_button(
        hikari.ButtonStyle.DANGER, on_clear, label="Clear the channel"
    )
    return menu


def _is_admin(ctx: lightbulb.Context) -> bool:
    """Manage Channels, checked inline -- the house pattern for gating."""
    return ctx.member is not None and bool(
        ctx.member.permissions & hikari.Permissions.MANAGE_CHANNELS
    )


def _restricted_note(app: hikari.RESTAware, channel_id: int) -> str:
    """Warn, don't refuse: `@everyone` denied plus a role allowed is an ordinary
    server, and this check can't see that the role covers every player. Silent on
    a cache miss rather than crying wolf."""
    if not isinstance(app, hikari.CacheAware):
        return ""
    if everyone_can_view(app, channel_id) is not False:
        return ""
    return _CHANNEL_RESTRICTED.format(channel=channel_id)


def _can_post(ctx: lightbulb.Context, channel_id: int) -> bool:
    """Only False rejects: a cache miss returns None and is allowed through,
    since refusing on a cold cache would block a legitimate choice and posting
    re-checks anyway."""
    app = ctx.client.app
    if ctx.member is None or not isinstance(app, hikari.CacheAware):
        return True
    return can_send_in(app, channel_id, ctx.member) is not False


# --- /chardle stats ---------------------------------------------------------


@loader.command
@chardle_group.register
class Stats(
    lightbulb.SlashCommand, name="stats", description="Your Chardle daily record"
):
    @lightbulb.invoke
    async def invoke(
        self, ctx: lightbulb.Context, stats: StatsService, settings: ConfigService
    ) -> None:
        user_id = int(ctx.user.id)
        guild_id = int(ctx.guild_id) if ctx.guild_id is not None else None
        async with async_session() as db:
            epoch = await _epoch(db, settings)
            tz = await effective_zone(
                db,
                settings,
                guild_id=guild_id,
                channel_id=int(ctx.channel_id),
                user_id=user_id,
            )
            record = await stats.player(
                db,
                user_id,
                current_number=schedule.puzzle_number(epoch, tz, datetime.now(UTC)),
            )
            leaders = (
                await stats.leaderboard(db, int(ctx.guild_id))
                if ctx.guild_id is not None
                else []
            )

        lines = [
            f"**{record.played}** played · **{record.solved}** solved · "
            f"**{record.win_rate:.0%}** win rate",
            f"Streak **{record.current_streak}** (best **{record.longest_streak}**)",
            "",
            "**Guess distribution**",
            *_histogram(record.distribution),
        ]
        if leaders:
            lines.extend(["", "**This server**"])
            lines.extend(
                f"{index}. <@{user}> — {count}"
                for index, (user, count) in enumerate(leaders, start=1)
            )
        await ctx.respond(_embed("Chardle", "\n".join(lines)), ephemeral=True)


def _histogram(distribution: dict[int, int]) -> list[str]:
    if not distribution:
        return ["-# Nothing solved yet."]
    peak = max(distribution.values())
    return [
        f"`{n}` {'█' * max(1, round(distribution.get(n, 0) / peak * 12))} "
        f"{distribution.get(n, 0)}"
        for n in range(1, max(distribution) + 1)
    ]


# --- /chardle help ----------------------------------------------------------


@loader.command
@chardle_group.register
class Help(
    lightbulb.SlashCommand, name="help", description="How to read a Chardle board"
):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context, settings: ConfigService) -> None:
        async with async_session() as db:
            view = await _view(
                db,
                settings,
                guild_id=int(ctx.guild_id) if ctx.guild_id is not None else None,
                channel_id=int(ctx.channel_id),
                user_id=int(ctx.user.id),
            )
        text = _help_text(bpm_window=view.windows.bpm, note_window=view.windows.note)
        await ctx.respond(_embed("Chardle", text), ephemeral=True)


def _help_text(*, bpm_window: int, note_window: int) -> str:
    return "\n".join(
        [
            "Guess an Arcaea chart based on clues",
            "Help text placeholder"
        ]
    )


# --- reply path -------------------------------------------------------------


@loader.listener(hikari.MessageCreateEvent)
async def _on_reply(
    event: hikari.MessageCreateEvent,
    sessions: SessionService,
    guesses: GuessService,
    settings: ConfigService,
    channels: ChardleChannelService,
) -> None:
    """A reply to the board message is a guess.

    A table lookup rather than ``wait_for``: game state lives in Postgres, so a
    restart never kills a board.
    """
    message = event.message
    if event.is_bot or not message.content:
        return
    reference = message.message_reference
    if reference is None or reference.id is None:
        return

    async with async_session() as db:
        session = await sessions.by_message(
            db, int(message.channel_id), int(reference.id)
        )
        if session is None or session.state is not ChardleState.PLAYING:
            return
        if session.expires_at is not None and session.expires_at <= datetime.now(UTC):
            return
        # A message id identifies a board, not a player: no constraint can stop a
        # moderator who joined the private thread guessing into someone's daily.
        if session.is_daily and session.discord_id != int(message.author.id):
            return

        async with sessions.lock(session.id):
            outcome, _ = await _apply_guess(
                db,
                event.app,
                session,
                guesses,
                settings,
                message.content,
                int(message.author.id),
            )
        await _sticky_after(event.app, db, channels, settings, session, outcome)

    # ❌ reads as "rejected"; a search was understood, it just was not a guess.
    reaction = "🔍" if isinstance(outcome, Searched) else "❌"
    if isinstance(outcome, (Invalid, Duplicate, Searched)):
        try:
            await message.add_reaction(reaction)
        except hikari.HikariError:
            logger.debug("chardle: could not mark a free guess")


# --- scoreboard button ------------------------------------------------------


@loader.listener(hikari.InteractionCreateEvent)
async def _on_scoreboard_button(
    event: hikari.InteractionCreateEvent,
    puzzles: PuzzleService,
    sessions: SessionService,
    settings: ConfigService,
    channels: ChardleChannelService,
) -> None:
    """The scoreboard's Play button.

    A raw custom_id rather than a lightbulb Menu: the scoreboard outlives
    restarts, and a Menu's handler dies with its timeout.
    """
    interaction = event.interaction
    if not isinstance(interaction, hikari.ComponentInteraction):
        return
    if interaction.custom_id != sticky.PLAY_BUTTON_ID:
        return

    await interaction.create_initial_response(
        hikari.ResponseType.DEFERRED_MESSAGE_CREATE, flags=hikari.MessageFlag.EPHEMERAL
    )
    embed = await start_daily(
        event.app,
        user=interaction.user,
        member=interaction.member,
        guild_id=int(interaction.guild_id) if interaction.guild_id else None,
        invoked_channel_id=int(interaction.channel_id),
        puzzles=puzzles,
        sessions=sessions,
        settings=settings,
        channels=channels,
    )
    await interaction.edit_initial_response(embed=embed)


# --- sweep ------------------------------------------------------------------


@loader.task(lightbulb.uniformtrigger(minutes=30))
async def _sweep(
    client: lightbulb.Client,
    settings: ConfigService,
    sessions: SessionService,
    puzzles: PuzzleService,
    channels: ChardleChannelService,
) -> None:
    """Expired dailies and abandoned free-play boards. The abandoned ones matter
    because a live board holds its channel's only slot."""
    async with async_session() as db:
        hours = int(
            await settings.resolve(
                db,
                "chardle_abandon_hours",
                guild_id=None,
                channel_id=0,
                user_id=0,
                is_dm=True,
            )
        )
        stale = await sessions.sweep(db, hours)
        await _close_boards(client.app, db, settings, stale)
        await _roll_scoreboards(client.app, db, settings, puzzles, channels)
    if stale:
        logger.info("chardle: closed %s stale board(s)", len(stale))


async def _close_boards(
    app: hikari.RESTAware, db, settings: ConfigService, stale: list[ChardleSession]
) -> None:
    """Re-render every board the sweep just lost, so none is left reading
    "**3** of 6 attempts left" on a game that is over."""
    # Each build re-reads the shared-name set the scoreboard hoists out of its
    # loop. Left alone: a sweep closes a handful of boards every half hour, and
    # threading it through _refresh/_render would put a batching parameter on the
    # two paths every single guess goes down.
    for session in stale:
        view = await _view(
            db,
            settings,
            guild_id=session.guild_id,
            channel_id=session.board_channel_id,
            user_id=session.discord_id or 0,
        )
        await _refresh(app, db, await _puzzle_of(db, session), session, view)


async def _roll_scoreboards(
    app: hikari.RESTAware,
    db,
    settings: ConfigService,
    puzzles: PuzzleService,
    channels: ChardleChannelService,
) -> None:
    """Put every configured guild's scoreboard on its current puzzle.

    This is what posts a fresh board after rollover in a guild where nobody has
    played yet, and it re-syncs any refresh a failed edit dropped.
    """
    epoch = await _epoch(db, settings)
    for guild_id in await channels.configured_guilds(db):
        tz = await effective_zone(db, settings, guild_id=guild_id, channel_id=0, user_id=0)
        number = schedule.puzzle_number(epoch, tz, datetime.now(UTC))
        try:
            puzzle = await puzzles.daily(db, epoch, number)
        except EmptyPool:
            continue
        await sticky.refresh(
            app, db, channels, settings, guild_id=guild_id, puzzle=puzzle
        )


loader.command(chardle_group)
