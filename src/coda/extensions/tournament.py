"""``/tournament`` -- quick matches, their room, and the guild's home channel.

The only lightbulb-aware file in the module. Everything below it is DB-only or
Discord-only, never both.

Components use a stateless ``tourney:`` custom-id contract dispatched by the
persistent listener below, not a lightbulb ``Menu``: a match outlives any menu
timeout and outlives restarts, so the turn is read from the DB on every click
and never from the id.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone

import hikari
import lightbulb
from hikari.impl import MessageActionRowBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from coda.catalog.labels import CLASS_OPTIONS
from coda.db.enums import (
    MatchState,
    PoolEntryState,
    ThreadVisibility,
)
from coda.db.models import ArcaeaAccount, PlayerLink, TournamentMatch
from coda.db.session import async_session
from coda.settings import ConfigService
from coda.tournaments import (
    announce,
    defaults,
    match as match_ops,
    pool,
    service,
    transport,
    viewbuild,
)
from coda.tournaments import options as tournament_options
from coda.tournaments.board import BoardService
from coda.tournaments.constants import TICK_SECONDS
from coda.tournaments.pickban import turn_at
from coda.tournaments.threads import TournamentChannelService
from coda.utils.render import notice

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()
tournament_group = lightbulb.Group("tournament", "Play a match against someone")

ANY_CLASS = "any"
CUSTOM_ID_PREFIX = "tourney"
HOME_ID = CUSTOM_ID_PREFIX + ":home:{channel_id}"

# A home channel has threads hanging off it, so it cannot itself be one.
HOME_TYPES = (hikari.ChannelType.GUILD_TEXT, hikari.ChannelType.GUILD_NEWS)

_NOT_REGISTERED = (
    "{who} hasn't registered an Arcaea account with me yet. `/register` first."
)
_NOT_TRACKED = (
    "{who} has score tracking switched off, so nothing they play would be "
    "recorded. Turn it on with `/tracking` first."
)
_NO_SELF = "You can't play a match against yourself."
_SHARED_ACCOUNT = (
    "You're both registered to the same Arcaea account, so both sides would "
    "score the same play. One side per account."
)
_OPEN_NOTE = " Anyone else who can see it can `/tournament join`."
_JOINED = (
    "You're in the match. Everyone's **Ready** was cleared, so all of you "
    "have to hit it again before the match starts."
)
_NOT_OPEN = "This match isn't open. Only the people it was started with are playing."
_NOT_IN_MATCH = "This isn't your match to act in."
_NOT_YOUR_TURN = "It isn't your turn."
_NOTHING_TO_READY = "There's nothing to be ready for right now."
_NOT_ADMIN = "You need **Manage Channels** to do that."
_NO_CHANNEL_SET = (
    "None set yet. Matches can't be started until one is."
)
_HOME_IS_THREAD = (
    "None set yet. Run this in the text channel you want matches to hang off. "
    "The home channel can't be a thread."
)

# A chat line that stands in for the Ready button, so skipping a break costs
# nobody a trip to a component. Matched whole, never as a substring: "ready in
# a sec" is the opposite of ready, and "gg" is a thing people actually type at
# exactly the moment a break begins.
_READY_WORDS = frozenset(
    {
        "r", "rdy", "ready", "go", "ok", "okay", "y", "yes", "yep", "yeah",
        "next", "done", "lets go", "let's go",
    }
)
_READY_STRIP = " \t\n.!?~,"


def reads_as_ready(content: str) -> bool:
    """Whether a chat line means what the Ready button means.

    Matched WHOLE, never as a substring: "ready in a sec" is the opposite of
    ready, and "gg ez" is a conversation rather than a signal. Trailing
    punctuation and case are the only latitude, because everything past that
    starts guessing at intent.
    """
    return content.strip().strip(_READY_STRIP).lower() in _READY_WORDS


def _choices(table: dict[str, str]) -> list[lightbulb.Choice]:
    """A picker over one of the shared option tables, in the table's order."""
    return [
        lightbulb.Choice(name=label, value=value)
        for value, label in table.items()
    ]


def home_row(channel_id: int) -> MessageActionRowBuilder:
    """One-click "use where I'm standing", for the common case.

    Stateless like every other component here: the channel is in the id, and
    the permission is re-checked on click. A button is an offer, never proof
    that the clicker may act.
    """
    row = MessageActionRowBuilder()
    row.add_interactive_button(
        hikari.ButtonStyle.PRIMARY,
        HOME_ID.format(channel_id=channel_id),
        label="Use this channel",
    )
    return row


# --- /tournament quick ------------------------------------------------------


@loader.command
@tournament_group.register
class Quick(
    lightbulb.SlashCommand,
    name="quick",
    description="Start a match against someone",
):
    opponent = lightbulb.user("with", "Who you're playing")
    # Required, and the one choice that decides what KIND of match this is:
    # a class is competitive, `any` is casual and hands the difficulty choice
    # to the player. Never a guild default for that reason.
    difficulty = lightbulb.string(
        "difficulty",
        "Difficulty to play, or Any for a casual match",
        choices=[
            lightbulb.Choice(name="Any", value=ANY_CLASS),
            *(
                lightbulb.Choice(name=key.upper(), value=key)
                for key in CLASS_OPTIONS
            ),
        ],
    )
    level = lightbulb.string(
        "level", "Level band, e.g. 9 or 9-10+ or any", default=None)
    best_of = lightbulb.string(
        "bo",
        "How many rounds, or how many charts are on the table with 3+ players",
        choices=_choices(tournament_options.BEST_OF),
        default=None,
    )
    bans = lightbulb.boolean("bans", "Pick and ban charts", default=None)
    # A room property, not a format one, and deliberately not `visibility`:
    # visibility decides who may READ the thread, this decides who may play.
    # Off by default -- a quick match is an invitation to one person, and a
    # third player arriving unasked changes the match those two agreed to.
    open_join = lightbulb.boolean(
        "open", "Let anyone who can see the thread join", default=False)
    visibility = lightbulb.string(
        "visibility",
        "Who can view the match thread",
        choices=_choices(tournament_options.VISIBILITY),
        default=None,
    )

    @lightbulb.invoke
    async def invoke(
        self,
        ctx: lightbulb.Context,
        settings: ConfigService,
        channels: TournamentChannelService,
        boards: BoardService,
    ) -> None:
        await ctx.defer(ephemeral=True)
        if ctx.guild_id is None:
            await _say(ctx, "Not here", "Matches run in a server, not a DM.")
            return
        if int(self.opponent.id) == int(ctx.user.id):
            await _say(ctx, "Nope", _NO_SELF)
            return

        async with async_session() as db:
            home = await channels.channel_id(db, ctx.guild_id)
            if home is None:
                await _say(ctx, "No channel", transport.NO_CHANNEL)
                return

            roster = []
            names: dict[int, str | None] = {}
            for user in (ctx.user, self.opponent):
                account, problem = await _playable(db, user)
                if problem is not None:
                    await _say(ctx, "Can't start", problem)
                    return
                # Two Discord users may link ONE Arcaea account, and a side is
                # ranked by that account's scores -- rostering it twice would
                # give both sides the same score every round.
                if account.id in names:
                    await _say(ctx, "Same account", _SHARED_ACCOUNT)
                    return
                roster.append(account)
                # The one moment the real user object is in hand. The members
                # intent is off, so the member cache cannot be asked later.
                names[account.id] = user.display_name

            try:
                options = await defaults.resolve(
                    db,
                    settings,
                    defaults.Chosen(
                        difficulty_class=CLASS_OPTIONS.get(self.difficulty),
                        song_mode=self.difficulty == ANY_CLASS,
                        level=self.level,
                        best_of=self.best_of,
                        bans=self.bans,
                        open_join=self.open_join,
                        visibility=self.visibility,
                    ),
                    guild_id=ctx.guild_id,
                    channel_id=ctx.channel_id,
                    user_id=int(ctx.user.id),
                )
            except ValueError as bad_level:
                await _say(ctx, "Bad level", str(bad_level))
                return

            account_ids = [account.id for account in roster]
            # Before the thread: a band that cannot fill a pool refuses the
            # same way at start, and finding that out THEN costs a thread, two
            # pings and a board nobody can do anything with.
            thin = await _thin_pool(db, options, account_ids)
            if thin is not None:
                await _say(ctx, "Not enough charts", thin)
                return
            remembered = await channels.crew_thread(
                db, ctx.guild_id, account_ids, options.visibility)
            resolved = await transport.resolve(
                ctx.client.app,
                parent_channel_id=home,
                name=transport.thread_name(
                    [
                        names.get(account.id) or account.display_name or "player"
                        for account in roster
                    ]
                ),
                private=options.visibility == ThreadVisibility.PRIVATE,
                member_ids=[int(ctx.user.id), int(self.opponent.id)],
                reuse_thread_id=remembered,
            )
            if resolved is None:
                if remembered is not None:
                    await channels.forget_thread(db, remembered)
                await _say(ctx, "No thread", transport.NO_THREAD)
                return

            thread_id, _ = resolved
            match = await match_ops.create(
                db,
                guild_id=ctx.guild_id,
                home_channel_id=home,
                thread_id=thread_id,
                creator_discord_id=int(ctx.user.id),
                roster=account_ids,
                options=options,
                names=names,
            )
            await db.commit()
            await boards.post(ctx.client.app, db, match)
            await db.commit()
            # The board arrives with its Ready button; this adds the line that
            # pings everyone it is waiting on.
            await boards.refresh(ctx.client.app, db, match)

        await _say(
            ctx,
            "Room open",
            f"<#{thread_id}>. Press **Ready** in there to start."
            + (_OPEN_NOTE if self.open_join else ""),
        )


# --- /tournament join, leave, start, cancel, board --------------------------


@loader.command
@tournament_group.register
class Join(
    lightbulb.SlashCommand, name="join", description="Join the match in this thread"
):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context, boards: BoardService) -> None:
        await ctx.defer(ephemeral=True)
        async with async_session() as db:
            match = await _match_here(db, ctx)
            if match is None:
                await _say(ctx, "No match", "There's no match in this thread.")
                return
            if match.state != MatchState.DRAFT:
                await _say(ctx, "Too late", "This match has already started.")
                return
            # Seeing a thread is not being invited into the match inside it.
            if not match.open_join:
                await _say(ctx, "Not open", _NOT_OPEN)
                return
            account, problem = await _playable(db, ctx.user)
            if problem is not None:
                await _say(ctx, "Can't join", problem)
                return
            if not await match_ops.join(
                db, match, account.id, ctx.user.display_name
            ):
                await _say(ctx, "Already in", "You're in the match already.")
                return
            await db.commit()
            await _roster_beat(ctx, boards, match, announce.joined)
            await boards.refresh(ctx.client.app, db, match)
        await _say(ctx, "Joined", _JOINED)


@loader.command
@tournament_group.register
class Leave(
    lightbulb.SlashCommand, name="leave", description="Leave the match in this thread"
):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context, boards: BoardService) -> None:
        await ctx.defer(ephemeral=True)
        async with async_session() as db:
            match = await _match_here(db, ctx)
            if match is None or match.state != MatchState.DRAFT:
                await _say(ctx, "Can't leave", "Only a match that hasn't started.")
                return
            account, problem = await _playable(db, ctx.user)
            if problem is not None or not await match_ops.leave(
                db, match, account.id
            ):
                await _say(ctx, "Not in", "You weren't on the match.")
                return
            await db.commit()
            await _roster_beat(ctx, boards, match, announce.left)
            await boards.refresh(ctx.client.app, db, match)
        await _say(ctx, "Left", "You're off the match.")


@loader.command
@tournament_group.register
class Start(
    lightbulb.SlashCommand,
    name="start",
    description="Start the match in this thread, once everyone is ready",
):
    @lightbulb.invoke
    async def invoke(
        self,
        ctx: lightbulb.Context,
        channels: TournamentChannelService,
        boards: BoardService,
    ) -> None:
        await ctx.defer(ephemeral=True)
        async with async_session() as db:
            match = await _match_here(db, ctx)
            if match is None or match.state != MatchState.DRAFT:
                await _say(ctx, "Can't start", "No match here is waiting to start.")
                return
            if not _may_run(ctx, match):
                await _say(ctx, "Nope", "Only the organizer can start it.")
                return

            refusal = await _begin(db, match, channels)
            if refusal is not None:
                await _say(ctx, "Can't start", refusal)
                return
            await db.commit()
            await boards.refresh(ctx.client.app, db, match)
        await _say(ctx, "Started", "Good luck.")


@loader.command
@tournament_group.register
class Cancel(
    lightbulb.SlashCommand, name="cancel", description="Cancel the match in this thread"
):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context, boards: BoardService) -> None:
        await ctx.defer(ephemeral=True)
        async with async_session() as db:
            match = await _match_here(db, ctx)
            if match is None or match.state in (
                MatchState.CLOSED, MatchState.CANCELLED
            ):
                await _say(ctx, "Nothing to cancel", "No live match in this thread.")
                return
            if not _may_run(ctx, match):
                await _say(ctx, "Nope", "Only the organizer can cancel it.")
                return
            await service.cancel(db, match)
            await db.commit()
            await boards.refresh(ctx.client.app, db, match)
            boards.release(match.id)
        await _say(ctx, "Cancelled", "The thread stays for the record.")


@loader.command
@tournament_group.register
class Board(
    lightbulb.SlashCommand, name="board", description="Re-post this match's board"
):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context, boards: BoardService) -> None:
        await ctx.defer(ephemeral=True)
        async with async_session() as db:
            match = await _match_here(db, ctx)
            if match is None:
                await _say(ctx, "No match", "There's no match in this thread.")
                return
            # The board carries the controls, so re-posting it is the whole
            # recovery. The prompt line is cleared with it, since a board that
            # just arrived is worth naming who it is waiting on again.
            match.board_message_id = None
            match.prompt_key = None
            posted = await boards.post(ctx.client.app, db, match)
            await db.commit()
            await boards.refresh(ctx.client.app, db, match)
        await _say(
            ctx,
            "Board" if posted else "Couldn't post",
            "Posted." if posted else "I can't post in this thread.",
        )


# --- /tournament channel ----------------------------------------------------


@loader.command
@tournament_group.register
class Channel(
    lightbulb.SlashCommand,
    name="channel",
    description="Set the channel tournament threads hang off (admin)",
):
    # default=None, not hikari.UNDEFINED: lightbulb builds an UNDEFINED default
    # as a *required* option, which would make "leave it off" unreachable.
    channel = lightbulb.channel(
        "channel",
        "Channel to host matches in. Leave off to see the current one",
        channel_types=[hikari.ChannelType.GUILD_TEXT],
        default=None,
    )
    clear = lightbulb.boolean("clear", "Unset the channel instead", default=False)

    @lightbulb.invoke
    async def invoke(
        self, ctx: lightbulb.Context, channels: TournamentChannelService
    ) -> None:
        if ctx.guild_id is None:
            await _say(ctx, "Not here", "Use this in a server.")
            return
        if (self.channel is not None or self.clear) and not _is_admin(ctx):
            await _say(ctx, "Nope", "You need **Manage Channels** to do that.")
            return

        async with async_session() as db:
            if self.clear:
                await channels.clear(db, ctx.guild_id)
                await _say(
                    ctx, "Cleared", "Matches can't be started until one is set."
                )
                return
            if self.channel is None:
                current = await channels.channel_id(db, ctx.guild_id)
                if current is not None:
                    await _say(ctx, "Tournament channel", f"<#{current}>")
                    return
                await _say(ctx, "Tournament channel", *_offer_home(ctx))
                return
            await channels.set_channel(
                db, ctx.guild_id, int(self.channel.id), int(ctx.user.id)
            )
        await _say(ctx, "Set", f"Matches will run in threads off <#{self.channel.id}>.")


# --- components -------------------------------------------------------------


@loader.listener(hikari.InteractionCreateEvent)
async def _on_component(
    event: hikari.InteractionCreateEvent,
    boards: BoardService,
    channels: TournamentChannelService,
) -> None:
    interaction = event.interaction
    if not isinstance(interaction, hikari.ComponentInteraction):
        return
    parsed = parse_custom_id(interaction.custom_id)
    if parsed is None:
        # Not ours: lightbulb's own Menu/Modal handling owns it.
        return
    action, target_id = parsed

    # Acknowledge first: the handler edits a message and may run several
    # queries, which would otherwise blow the 3 s interaction budget.
    await interaction.create_initial_response(
        hikari.ResponseType.DEFERRED_MESSAGE_UPDATE)

    if action == "home":
        await _handle_home(interaction, channels, target_id)
        return

    async with async_session() as db:
        match = await db.get(TournamentMatch, target_id)
        if match is None:
            return
        refused = await (
            _handle_act(db, interaction, match)
            if action == "act"
            else _handle_ready(db, interaction, match, channels, boards)
        )
        # Committed even on a refusal: both paths refuse before they mutate, so
        # a refusal has nothing to roll back -- and the ready path may have
        # recorded a click on its way to one, which must not be lost.
        await db.commit()
        await boards.refresh(interaction.app, db, match)
        if refused is not None:
            await interaction.execute(refused, flags=hikari.MessageFlag.EPHEMERAL)


def parse_custom_id(custom_id: str) -> tuple[str, int] | None:
    """``(action, id)`` for one of our components, else ``None``.

    The id is whatever the action is about -- a match for ``act``/``ready``, a
    channel for ``home``.
    """
    parts = custom_id.split(":")
    if len(parts) != 3 or parts[0] != CUSTOM_ID_PREFIX:
        return None
    if parts[1] not in ("act", "ready", "home"):
        return None
    try:
        return parts[1], int(parts[2])
    except ValueError:
        return None


async def _handle_home(
    interaction: hikari.ComponentInteraction,
    channels: TournamentChannelService,
    channel_id: int,
) -> None:
    """Set the guild's home channel from the offer button.

    Re-checks the permission rather than trusting that the button was rendered:
    an ephemeral message is only ephemeral to Discord, and the id is guessable
    besides.
    """
    member = interaction.member
    allowed = member is not None and bool(
        member.permissions & hikari.Permissions.MANAGE_CHANNELS
    )
    if interaction.guild_id is None or not allowed:
        await interaction.execute(_NOT_ADMIN, flags=hikari.MessageFlag.EPHEMERAL)
        return

    async with async_session() as db:
        # Someone else may have set one between the render and the click.
        current = await channels.channel_id(db, interaction.guild_id)
        if current is not None:
            await _replace(interaction, "Already set", f"<#{current}>")
            return
        await channels.set_channel(
            db, interaction.guild_id, channel_id, int(interaction.user.id)
        )
    await _replace(
        interaction, "Set", f"Matches will run in threads off <#{channel_id}>."
    )


async def _replace(
    interaction: hikari.ComponentInteraction, title: str, body: str
) -> None:
    """Swap the offer for its outcome, dropping the button with it."""
    await interaction.edit_initial_response(
        components=[notice(title, body).build()]
    )


async def _handle_act(
    db: AsyncSession, interaction: hikari.ComponentInteraction, match: TournamentMatch
) -> str | None:
    """Apply one pick or ban. Returns a refusal, or None on success.

    Location narrows the audience; this check enforces it. MANAGE_THREADS lets
    a moderator read a private thread uninvited, so the clicker is verified
    against the roster rather than trusted for being here.
    """
    if match.state != MatchState.PICKBAN:
        return "That match isn't picking or banning."
    side = await _side_of(db, match, int(interaction.user.id))
    if side is None:
        return _NOT_IN_MATCH
    turn = turn_at(match.turn_index, match.best_of)
    if turn is None or turn.side_index != side:
        return _NOT_YOUR_TURN

    entry_id = int(interaction.values[0])
    entry = next(
        (
            e
            for e in await match_ops.entries(
                db, match.id, state=PoolEntryState.AVAILABLE)
            if e.id == entry_id
        ),
        None,
    )
    if entry is None:
        return "That chart is already gone."
    await match_ops.act(db, match, entry, auto=False)
    return None


async def _handle_ready(
    db: AsyncSession,
    interaction: hikari.ComponentInteraction,
    match: TournamentMatch,
    channels: TournamentChannelService,
    boards: BoardService,
) -> str | None:
    """One primitive, cleared whenever a new wait begins -- it confirms a match
    into existence and skips a break, and the button says the same word both
    times because it means the same thing both times."""
    if not await _waiting_on_ready(db, match):
        return _NOTHING_TO_READY
    if not await _mark_ready(db, match, int(interaction.user.id)):
        return _NOT_IN_MATCH
    await _start_if_confirmed(db, match, channels, boards, interaction.app)
    return None


async def _waiting_on_ready(db: AsyncSession, match: TournamentMatch) -> bool:
    """Whether Ready means anything to this match right now.

    Re-checked against the clock rather than trusted from the prompt: a retired
    prompt does not recall a click already in flight, and a flag set mid-window
    would survive into the next break and skip a rest nobody asked to skip.

    A match holding a turn is never waiting on Ready. The rest is spent by the
    time a pick is served, so the only answer that match wants is the pick.
    """
    if match.state == MatchState.DRAFT:
        return True
    if match.state != MatchState.PLAYING:
        return False
    phase, _, _ = service.phase_of(
        await service.rounds(db, match.id),
        match_ops.now_ms(),
        turn_owed=await match_ops.turn_owed(db, match),
    )
    return phase == "break"


async def _start_if_confirmed(
    db: AsyncSession,
    match: TournamentMatch,
    channels: TournamentChannelService,
    boards: BoardService,
    app: hikari.RESTAware,
) -> None:
    """Start a drafting match the moment the last person confirms.

    Silent while anyone is still missing -- the prompt already ticks them off,
    and telling a player who just answered that somebody else has not is noise.
    A real failure (too few players, a pool the filters cannot fill) goes into
    the THREAD rather than back to whoever clicked last: the draft prompt keeps
    saying "hit Ready" either way, so a refusal only that one player sees --
    or, from the chat-word path, that nobody sees -- leaves the whole match
    looking hung with everybody marked ready.
    """
    if match.state != MatchState.DRAFT:
        return
    if any(p.ready_at is None for p in await match_ops.roster(db, match.id)):
        return
    refusal = await _begin(db, match, channels)
    if refusal is None:
        return
    # The confirmations were spent on a start that did not happen, and a board
    # showing everyone ready under a prompt still asking for Ready is the whole
    # of what "it just hangs" looks like. Clearing them puts the ask back --
    # and stops one repost per curious click.
    await match_ops.clear_ready(db, match.id)
    await boards.say(app, match.thread_id, refusal, [])


async def _mark_ready(
    db: AsyncSession, match: TournamentMatch, discord_id: int
) -> bool:
    """Record one side as ready. False if that user is not in the match."""
    side = await _side_of(db, match, discord_id)
    if side is None:
        return False
    for participant in await match_ops.roster(db, match.id):
        if participant.side_index == side:
            participant.ready_at = datetime.now(timezone.utc)
    await db.flush()
    return True


@loader.listener(hikari.GuildMessageCreateEvent)
async def _on_message(
    event: hikari.GuildMessageCreateEvent,
    boards: BoardService,
    channels: TournamentChannelService,
) -> None:
    """Let a word in the thread do what the Ready button does.

    Ordered cheapest-first on purpose: this sees every message in every guild
    the bot is in, so the content test runs before any query and discards
    almost all of them without touching the database.

    Only while a match is drafting or between rounds. Outside those there is
    nothing to be ready FOR, and accepting "gg" mid-window would set a flag
    that survives into the break and silently skip the rest a player had not
    been offered yet.
    """
    if event.is_bot or not event.content:
        return
    if not reads_as_ready(event.content):
        return
    async with async_session() as db:
        match = await db.scalar(
            select(TournamentMatch).where(
                TournamentMatch.thread_id == int(event.channel_id),
                TournamentMatch.state.in_(
                    (MatchState.DRAFT, MatchState.PLAYING)),
            )
        )
        if match is None:
            return
        if not await _waiting_on_ready(db, match):
            return
        if not await _mark_ready(db, match, int(event.author_id)):
            return
        await _start_if_confirmed(db, match, channels, boards, event.app)
        await db.commit()
        await boards.refresh(event.app, db, match)


# --- the sweep --------------------------------------------------------------


# max_failures=-1: lightbulb cancels a task PERMANENTLY on its first failure,
# and this tick is the only thing that opens windows, closes them, auto-acts an
# expired turn and redraws a board. One transient error must not end every
# tournament for the life of the process -- log it and take the next tick.
@loader.task(lightbulb.uniformtrigger(seconds=TICK_SECONDS), max_failures=-1)
async def _sweep(client: lightbulb.Client, boards: BoardService) -> None:
    """Advance every live match, then redraw the boards that changed.

    This is also the board's debounce: however many scores land in a tick, the
    message is edited at most once -- and unlike a real debounce, a tick cannot
    drop the final frame.
    """
    async with async_session() as db:
        changed = await service.tick(db)
        await db.commit()
        # Beats BEFORE boards, because a beat is the thing that just happened
        # and a prompt is what happens next: reversed, a break would invite the
        # next round in the message above the one saying who won the last.
        for match_id, beats in changed.beats.items():
            try:
                await _say_beats(client.app, db, boards, match_id, beats)
            except Exception:
                logger.exception(
                    "tournaments: cannot announce match %s", match_id)
        for match_id in changed.touched:
            match = await db.get(TournamentMatch, match_id)
            if match is None:
                continue
            # The DB work is already committed; a board that will not draw must
            # not cost the other boards their redraw.
            try:
                await boards.refresh(client.app, db, match)
            except Exception:
                logger.exception(
                    "tournaments: cannot redraw board for match %s", match_id)


async def _say_beats(
    app: hikari.RESTAware,
    db: AsyncSession,
    boards: BoardService,
    match_id: int,
    beats: list[announce.Beat],
) -> None:
    """Post a match's owed beats and stamp the ones that landed.

    Stamped only on success, and committed per beat: an unstamped beat is
    simply owed again next tick, whereas stamping first would trade a duplicate
    message for a silence -- and silence is the failure this whole path exists
    to fix.
    """
    match = await db.get(TournamentMatch, match_id)
    if match is None:
        return
    view = await viewbuild.build(db, match)
    rounds = {r.ordinal: r for r in await service.rounds(db, match.id)}
    for beat in beats:
        text = announce.line(view, beat)
        round_ = rounds.get(beat.ordinal)
        if text is None or round_ is None:
            continue
        if await boards.say(
            app, match.thread_id, text, announce.mention_ids(view)
        ):
            announce.stamp(round_, beat)
            await db.commit()


# --- helpers ----------------------------------------------------------------


async def _begin(
    db: AsyncSession, match: TournamentMatch, channels: TournamentChannelService
) -> str | None:
    """Freeze the roster, draw the pool, leave draft. A refusal, or None.

    The gate is unanimous consent, not the organizer's word: a quick match
    opens a thread at someone who never asked for it, and starting before they
    have answered is how a match becomes a forfeit nobody agreed to. The
    organizer's ``/tournament start`` runs the same check -- it is the way to
    retry a start that failed, never a way around the roster.
    """
    members = await match_ops.roster(db, match.id)
    if len(members) < 2:
        return "A match needs at least two players."
    waiting = [p for p in members if p.ready_at is None]
    if waiting:
        names = ", ".join(p.display_name or "a player" for p in waiting)
        return f"Still waiting on **{names}** to hit Ready."

    shortfall = await match_ops.start(db, match)
    if shortfall is not None:
        return _pool_line(match.best_of, shortfall, opened=True)
    # The crew is bound to the thread at FREEZE, not at creation: the roster
    # can grow while drafting, and the key must name the crew that played.
    await channels.remember_crew(
        db,
        match.guild_id,
        [p.arcaea_account_id for p in members],
        match.visibility,
        match.thread_id,
    )
    return None


async def _thin_pool(
    db: AsyncSession, options: match_ops.MatchOptions, account_ids: list[int]
) -> str | None:
    """Why these filters cannot fill a pool, or None if they can.

    Checked against the roster the command was typed with. Joining only ever
    relaxes it -- above two players there is no pick/ban, so the pool stops
    needing the two entries the bans spend.
    """
    spec = match_ops.spec_for(options, len(account_ids))
    offered = await pool.candidates(db, spec, account_ids)
    if len(offered) >= spec.size:
        return None
    return _pool_line(
        options.best_of,
        pool.Shortfall(found=len(offered), needed=spec.size),
        opened=False,
    )


def _pool_line(best_of: int, shortfall: pool.Shortfall, *, opened: bool) -> str:
    """Why the pool could not be drawn, and what to do about it.

    Says where the extra entries go, because "a Bo3 needs 5" reads like a bug
    until you know two of them are there to be banned -- read off the number
    itself, since a pool only carries them when this match actually bans.
    ``opened`` is what changes the advice: filters are fixed at creation, so a
    match that already exists has to be cancelled rather than re-run.
    """
    banning = shortfall.needed > best_of
    spent = " -- two to ban, one decider" if banning else ""
    knobs = (
        "a wider level band, fewer rounds, or bans off"
        if banning
        else "a wider level band or fewer rounds"
    )
    fix = (
        f"Try {knobs}."
        if not opened
        else (
            "A match can't be re-filtered once it's open: `/tournament cancel`,"
            f" then run `/tournament quick` again with {knobs}."
        )
    )
    return (
        f"Those filters only match **{shortfall.found}** chart(s), and a "
        f"Bo{best_of} needs **{shortfall.needed}**{spent}. {fix}"
    )


async def _roster_beat(
    ctx: lightbulb.Context,
    boards: BoardService,
    match: TournamentMatch,
    line: Callable[[str], str],
) -> None:
    """Write a roster change into the thread's log.

    Unstamped, unlike a round's beats: this reports a command that just ran
    rather than a transition the sweep discovered, so there is nothing to
    re-derive and nothing owed if it fails. Posted BEFORE the refresh that
    follows it, for the same reason the sweep posts beats first -- this is what
    happened, and the prompt that refresh puts up is what happens next.
    """
    await boards.say(
        ctx.client.app, match.thread_id, line(ctx.user.display_name), [])


async def _playable(
    db: AsyncSession, user: hikari.User
) -> tuple[ArcaeaAccount | None, str | None]:
    """The account that may be rostered, or why it may not be.

    Tracking is checked HERE rather than discovered at the end: ingest silently
    drops plays for an untracked account, so such a player would post scores
    all match and rank as "no score".
    """
    account = await db.scalar(
        select(ArcaeaAccount)
        .join(PlayerLink, PlayerLink.arcaea_account_id == ArcaeaAccount.id)
        .where(PlayerLink.discord_id == int(user.id))
    )
    who = user.mention
    if account is None:
        return None, _NOT_REGISTERED.format(who=who)
    if not account.tracking_enabled:
        return None, _NOT_TRACKED.format(who=who)
    return account, None


async def _match_here(
    db: AsyncSession, ctx: lightbulb.Context
) -> TournamentMatch | None:
    """The newest match living in this thread."""
    return await db.scalar(
        select(TournamentMatch)
        .where(TournamentMatch.thread_id == int(ctx.channel_id))
        .order_by(TournamentMatch.id.desc())
        .limit(1)
    )


async def _side_of(
    db: AsyncSession, match: TournamentMatch, discord_id: int
) -> int | None:
    account_id = await db.scalar(
        select(PlayerLink.arcaea_account_id).where(
            PlayerLink.discord_id == discord_id)
    )
    if account_id is None:
        return None
    for participant in await match_ops.roster(db, match.id):
        if participant.arcaea_account_id == account_id:
            return participant.side_index
    return None


def _offer_home(
    ctx: lightbulb.Context,
) -> tuple[str, list[MessageActionRowBuilder] | None]:
    """The "none set" reply, with a one-click fix when one would work here.

    Offered only to someone who could actually use it: a button that answers
    "you need Manage Channels" is worse than no button.
    """
    here = ctx.interaction.channel
    if here is not None and here.type not in HOME_TYPES:
        return _HOME_IS_THREAD, None
    if not _is_admin(ctx):
        return _NO_CHANNEL_SET, None
    return _NO_CHANNEL_SET, [home_row(int(ctx.channel_id))]


def _may_run(ctx: lightbulb.Context, match: TournamentMatch) -> bool:
    if match.admin_gated:
        return _is_admin(ctx)
    return int(ctx.user.id) == match.creator_discord_id or _is_admin(ctx)


def _is_admin(ctx: lightbulb.Context) -> bool:
    """Manage Channels, checked inline -- the house pattern for gating."""
    return ctx.member is not None and bool(
        ctx.member.permissions & hikari.Permissions.MANAGE_CHANNELS
    )


async def _say(
    ctx: lightbulb.Context,
    title: str,
    body: str,
    rows: list[MessageActionRowBuilder] | None = None,
) -> None:
    """Every reply here is an acknowledgement; the board is the public surface.

    Passed explicitly rather than relying on a prior ephemeral defer -- not
    every command defers, and a public "you need Manage Channels" is noise in
    the one channel the whole server watches.
    """
    rendered = notice(title, body)
    rendered.rows = rows or []
    await ctx.respond(components=[rendered.build()], ephemeral=True)


loader.command(tournament_group)
