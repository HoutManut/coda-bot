"""/liveupdates -- where a user's live score updates go, and which channels allow them.

Server admins allowlist channels; users pick from that allowlist. DM is the
default and always available.

Two different pickers, deliberately:

* ``allow``/``disallow`` (admin) use Discord's **native** channel picker -- any
  text channel is a legitimate choice there, so the built-in is exactly right.
* ``channel`` (user) uses **autocomplete over the allowlist** instead. Discord's
  picker validates a channel's *type*, not its membership of our allowlist, so
  using it would let a user pick a disallowed channel and force us to reject it
  after the fact. Building the list ourselves makes the invalid choice
  unrepresentable rather than merely refused.
"""

from __future__ import annotations

import logging

import hikari
import lightbulb

from coda.db.models import LiveUpdatePref
from coda.db.session import async_session
from coda.players.live import LiveUpdateService
from coda.scores.filters import ChannelFloor
from coda.utils.encoding import decode_level, encode_level
from coda.utils.permissions import can_send_in
from coda.utils.scoring import Grade

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()
live_group = lightbulb.Group("liveupdates", "Where your live score updates go")

_COLOR_OK = 0x57F287
_COLOR_ERR = 0xED4245

_DM_CHOICE = "dm"
_MAX_CHOICES = 25  # Discord's hard cap on autocomplete results.

_OFF_CHOICE = "off"

# The bot sees only the LATEST play per account per poll, so no filter can be
# described as complete. Every surface that lists filters carries this.
_SAMPLING_CAVEAT = (
    "-# I check every few minutes and only ever see your latest play, so some "
    "plays are never seen."
)

# Only the grades worth a milestone. Lower ones fire on almost every play.
_D_GRADE_CHOICE = lightbulb.Choice(name="D", value="D")
_GRADE_CHOICES = [
    lightbulb.Choice(name="off", value=_OFF_CHOICE),
    _D_GRADE_CHOICE,
    lightbulb.Choice(name="C", value="C"),
    lightbulb.Choice(name="B", value="B"),
    lightbulb.Choice(name="A", value="A"),
    lightbulb.Choice(name="AA", value="AA"),
    lightbulb.Choice(name="EX", value="EX"),
    lightbulb.Choice(name="EX+", value="EX_PLUS"),
]

_GRADE_NAMES = {
    Grade.D: "D",
    Grade.C: "C",
    Grade.B: "B",
    Grade.A: "A",
    Grade.AA: "AA",
    Grade.EX: "EX",
    Grade.EX_PLUS: "EX+"}

_LEVELS = ("8", "8+", "9", "9+", "10", "10+", "11", "11+", "12")
_LEVEL_CHOICES = [lightbulb.Choice(name="off", value=_OFF_CHOICE)] + [
    lightbulb.Choice(name=f"{level} and above", value=level) for level in _LEVELS
]


def _parse_grade(value: str) -> int | None:
    """A grade choice as a stored ``Grade`` ordinal. ``off`` -> None."""
    return None if value == _OFF_CHOICE else int(Grade[value])


def _parse_level(value: str) -> int | None:
    """A level choice as a stored ENCODED level. ``off`` -> None."""
    return None if value == _OFF_CHOICE else encode_level(value)


def _grade_label(ordinal: int | None) -> str:
    return "off" if ordinal is None else _GRADE_NAMES.get(Grade(ordinal), "off")


def _level_label(encoded: int | None) -> str:
    return "off" if encoded is None else f"{decode_level(encoded)} and above"


def _embed(title: str, description: str, *, ok: bool = True) -> hikari.Embed:
    return hikari.Embed(
        title=title, description=description, color=_COLOR_OK if ok else _COLOR_ERR
    )


async def _ac_channel(ctx: lightbulb.AutocompleteContext[str]) -> None:
    """Offer DM plus whichever channels this guild allows.

    Filtered to channels the member can actually post in, so the list only ever
    contains real choices -- the point of not using Discord's native picker.
    """
    choices: list[tuple[str, str]] = [("Direct Messages", _DM_CHOICE)]
    guild_id = ctx.interaction.guild_id
    app = ctx.client.app
    if guild_id is not None and isinstance(app, hikari.CacheAware):
        async with async_session() as db:
            allowed = await LiveUpdateService().allowed_channels(db, int(guild_id))
        member = ctx.interaction.member
        for channel_id in allowed:
            if member is not None and can_send_in(app, channel_id, member) is False:
                continue
            channel = app.cache.get_guild_channel(channel_id)
            name = f"#{channel.name}" if channel is not None else f"#{channel_id}"
            choices.append((name, str(channel_id)))

    typed = str(ctx.focused.value or "").lower()
    matches = [c for c in choices if typed in c[0].lower()]
    await ctx.respond(matches[:_MAX_CHOICES])


async def _ac_allowed(ctx: lightbulb.AutocompleteContext[str]) -> None:
    """This guild's allowlisted channels. No DM entry -- a floor is guild-only."""
    guild_id = ctx.interaction.guild_id
    if guild_id is None:
        await ctx.respond([])
        return
    async with async_session() as db:
        allowed = await LiveUpdateService().allowed_channels(db, int(guild_id))

    app = ctx.client.app
    choices: list[tuple[str, str]] = []
    for channel_id in allowed:
        channel = (
            app.cache.get_guild_channel(channel_id)
            if isinstance(app, hikari.CacheAware)
            else None
        )
        name = f"#{channel.name}" if channel is not None else f"#{channel_id}"
        choices.append((name, str(channel_id)))

    typed = str(ctx.focused.value or "").lower()
    await ctx.respond([c for c in choices if typed in c[0].lower()][:_MAX_CHOICES])


def _is_admin(ctx: lightbulb.Context) -> bool:
    """Manage Channels, checked inline -- the house pattern for gating."""
    return (
        ctx.member is not None
        and bool(ctx.member.permissions & hikari.Permissions.MANAGE_CHANNELS)
    )


@loader.command
@live_group.register
class Allow(
    lightbulb.SlashCommand,
    name="allow",
    description="Allow live score updates in a channel (admin)",
):
    # The native picker is right here: any text channel is a valid choice.
    channel = lightbulb.channel(
        "channel",
        "Channel to allow score updates in",
        channel_types=[hikari.ChannelType.GUILD_TEXT],
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context, svc: LiveUpdateService) -> None:
        if ctx.guild_id is None:
            await ctx.respond(_embed("Not here", "Use this in a server.", ok=False), ephemeral=True)
            return
        if not _is_admin(ctx):
            await ctx.respond(
                _embed("Nope", "You need **Manage Channels** to do that.", ok=False),
                ephemeral=True,
            )
            return

        async with async_session() as db:
            added = await svc.allow(
                db, int(ctx.guild_id), int(self.channel.id), int(ctx.user.id)
            )

        await ctx.respond(
            _embed(
                "Channel allowed" if added else "Already allowed",
                f"<#{self.channel.id}> "
                + (
                    "now accepts live score updates. Members can point their "
                    "updates at it with `/liveupdates channel`."
                    if added
                    else "was already on the list."
                ),
            ),
            ephemeral=True,
        )


@loader.command
@live_group.register
class Disallow(
    lightbulb.SlashCommand,
    name="disallow",
    description="Stop allowing live score updates in a channel (admin)",
):
    channel = lightbulb.channel(
        "channel",
        "Channel to stop allowing",
        channel_types=[hikari.ChannelType.GUILD_TEXT],
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context, svc: LiveUpdateService) -> None:
        if ctx.guild_id is None:
            await ctx.respond(_embed("Not here", "Use this in a server.", ok=False), ephemeral=True)
            return
        if not _is_admin(ctx):
            await ctx.respond(
                _embed("Nope", "You need **Manage Channels** to do that.", ok=False),
                ephemeral=True,
            )
            return

        async with async_session() as db:
            removed = await svc.disallow(db, int(ctx.guild_id), int(self.channel.id))

        await ctx.respond(
            _embed(
                "Channel removed" if removed else "Not on the list",
                f"<#{self.channel.id}> "
                + (
                    "no longer accepts live updates. Anyone pointed at it falls "
                    "back to DMs automatically."
                    if removed
                    else "wasn't allowing live updates anyway."
                ),
            ),
            ephemeral=True,
        )


@loader.command
@live_group.register
class Channel(
    lightbulb.SlashCommand,
    name="channel",
    description="Choose where your live score updates go",
):
    where = lightbulb.string(
        "where",
        "Direct Messages, or a channel this server allows",
        autocomplete=_ac_channel,
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context, svc: LiveUpdateService) -> None:
        if self.where == _DM_CHOICE:
            async with async_session() as db:
                await svc.set_destination(db, int(ctx.user.id), None)
            await ctx.respond(
                _embed("Updates moved",
                       "Your live updates will arrive in your **DMs**."),
                ephemeral=True,
            )
            return

        try:
            channel_id = int(self.where)
        except ValueError:
            await ctx.respond(
                _embed("Unknown channel", "Pick one from the list.", ok=False),
                ephemeral=True,
            )
            return

        async with async_session() as db:
            # Re-check rather than trust the value: autocomplete is a
            # suggestion, and Discord will submit anything the user typed.
            if not await svc.is_allowed(db, channel_id):
                await ctx.respond(
                    _embed(
                        "Not allowed there",
                        f"<#{channel_id}> isn't set up for live score updates. "
                        "An admin can allow it with `/liveupdates allow`.",
                        ok=False,
                    ),
                    ephemeral=True,
                )
                return
            if not await self._can_post(ctx, channel_id):
                await ctx.respond(
                    _embed(
                        "You can't post there",
                        f"You need to be able to send messages in <#{channel_id}> "
                        "to send your updates to it.",
                        ok=False,
                    ),
                    ephemeral=True,
                )
                return
            await svc.set_destination(db, int(ctx.user.id), channel_id)

        await ctx.respond(
            _embed("Updates moved",
                   f"Your live updates will now post in <#{channel_id}>."),
            ephemeral=True,
        )

    async def _can_post(self, ctx: lightbulb.Context, channel_id: int) -> bool:
        """Whether the caller may send messages in the target channel.

        The allowlist is guild-wide, but a channel on it can still be one this
        particular member cannot post in. Only False rejects: a cache miss
        returns None and is allowed through, since refusing on a cold cache
        would block legitimate choices, and posting re-checks anyway.
        """
        if ctx.member is None:
            return False
        app = ctx.client.app
        if not isinstance(app, hikari.CacheAware):
            # Can't check without a cache; posting re-checks anyway.
            return True
        return can_send_in(app, channel_id, ctx.member) is not False


@loader.command
@live_group.register
class Off(
    lightbulb.SlashCommand, name="off", description="Stop live score updates"
):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context, svc: LiveUpdateService) -> None:
        async with async_session() as db:
            await svc.set_enabled(db, int(ctx.user.id), False)
        await ctx.respond(
            _embed(
                "Live updates off",
                "I'll stop posting your plays. `/liveupdates on` turns them back "
                "on — your chosen channel is remembered.",
            ),
            ephemeral=True,
        )


@loader.command
@live_group.register
class On(
    lightbulb.SlashCommand, name="on", description="Start live score updates"
):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context, svc: LiveUpdateService) -> None:
        async with async_session() as db:
            await svc.set_enabled(db, int(ctx.user.id), True)
            _, channel_id = await svc.resolve_destination(db, int(ctx.user.id))
        where = f"<#{channel_id}>" if channel_id else "your **DMs**"
        await ctx.respond(
            _embed("Live updates on", f"Your plays will post in {where}."),
            ephemeral=True,
        )


@loader.command
@live_group.register
class Filters(
    lightbulb.SlashCommand,
    name="filters",
    description="Choose which of your plays get posted",
):

    pb = lightbulb.boolean(
        "pb", "Personal bests", default=hikari.UNDEFINED
    )
    pm = lightbulb.boolean(
        "pm", "Pure Memory", default=hikari.UNDEFINED
    )
    # Said here rather than discovered as silence: the friend payload has no
    # lost_count, so this can never fire without an own login.
    fr = lightbulb.boolean(
        "fr", "Full Recall (needs an own-login account)", default=hikari.UNDEFINED
    )
    grade_up = lightbulb.string(
        "grade_up",
        "First time you reach this grade on a chart",
        default=_OFF_CHOICE,
        choices=_GRADE_CHOICES,
    )
    best_of = lightbulb.integer(
        "best_of",
        "Plays that land in your top X. 0 turns it off",
        default=0,
        min_value=0,
        max_value=100,
    )
    min_level = lightbulb.string(
        "min_level",
        "Only charts at this level or higher",
        default=_OFF_CHOICE,
        choices=_LEVEL_CHOICES,
    )
    all = lightbulb.boolean(
        "all", "Every play", default=False
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context, svc: LiveUpdateService) -> None:
        updates = self._updates()
        async with async_session() as db:
            if not updates:
                pref = await svc.get_pref(db, int(ctx.user.id))
                await ctx.respond(_filters_embed(pref), ephemeral=True)
                return
            pref = await svc.set_filters(db, int(ctx.user.id), updates)
        await ctx.respond(_filters_embed(pref), ephemeral=True)

    def _updates(self) -> dict[str, bool | int | None]:
        """Only the filters the user actually named. Omitted stays as it was."""
        updates: dict[str, bool | int | None] = {}
        for option, column in (
            (self.all, "post_all"),
            (self.pb, "post_pb"),
            (self.pm, "post_pm"),
            (self.fr, "post_fr"),
        ):
            if option is not hikari.UNDEFINED:
                updates[column] = option
        if self.grade_up is not hikari.UNDEFINED:
            updates["min_grade"] = _parse_grade(self.grade_up)
        if self.best_of is not hikari.UNDEFINED:
            updates["best_of"] = self.best_of or None
        if self.min_level is not hikari.UNDEFINED:
            updates["min_level"] = _parse_level(self.min_level)
        return updates


def _filters_embed(pref: LiveUpdatePref | None) -> hikari.Embed:
    """What is currently being posted, and what is gating it."""
    if pref is None:
        triggers = ["Your personal best"]
        gates: list[str] = []
    else:
        triggers = _trigger_lines(pref)
        gates = _gate_lines(pref)

    body = "**Posting**\n" + (
        "\n".join(f"- {line}" for line in triggers)
        if triggers
        else "- Nothing. Turn something on and I'll post it."
    )
    if gates:
        body += "\n\n**Only when**\n" + \
            "\n".join(f"- {line}" for line in gates)
    # body += f"\n\n{_SAMPLING_CAVEAT}"
    return _embed("Live update filters", body)


def _trigger_lines(pref: LiveUpdatePref) -> list[str]:
    lines: list[str] = []
    if pref.post_all:
        lines.append("Every play I see")
    if pref.post_pb:
        lines.append("Your personal best")
    if pref.post_pm:
        lines.append("Pure Memory")
    if pref.post_fr:
        lines.append("Full Recall (own-login accounts only)")
    if pref.min_grade is not None:
        lines.append(
            f"First time reaching **{_grade_label(pref.min_grade)}** or better on a chart"
        )
    if pref.best_of:
        lines.append(f"Plays landing in your top **{pref.best_of}**")
    return lines


def _gate_lines(pref: LiveUpdatePref) -> list[str]:
    return (
        []
        if pref.min_level is None
        else [f"The chart is level **{_level_label(pref.min_level)}**"]
    )


def _status_triggers(pref: LiveUpdatePref | None) -> list[str]:
    return ["Your personal best"] if pref is None else _trigger_lines(pref)


def _status_gates(
    pref: LiveUpdatePref | None, floor: ChannelFloor | None, channel_id: int | None
) -> list[str]:
    """The user's own gates, plus whichever the destination channel adds.

    A guild floor is shown, never silent: a bar someone else set must always be
    explicable, or an absent post looks like a bug.
    """
    gates = [] if pref is None else _gate_lines(pref)
    if floor is None:
        return gates
    if floor.min_level is not None:
        gates.append(
            f"The chart is level **{decode_level(floor.min_level)} and above** "
            f"-- <#{channel_id}>'s rule"
        )
    if floor.min_grade is not None:
        gates.append(
            f"The play is **{_grade_label(int(floor.min_grade))}** or better "
            f"-- <#{channel_id}>'s rule"
        )
    return gates


@loader.command
@live_group.register
class Floor(
    lightbulb.SlashCommand,
    name="floor",
    description="Raise the bar for live updates in a channel (admin)",
):
    channel = lightbulb.string(
        "channel", "An allowed channel in this server", autocomplete=_ac_allowed
    )
    min_level = lightbulb.string(
        "min_level",
        "Only charts at this level or higher",
        default=_OFF_CHOICE,
        choices=_LEVEL_CHOICES,
    )
    min_grade = lightbulb.string(
        "min_grade",
        "Only plays at this grade or better",
        default=_D_GRADE_CHOICE,
        choices=[_D_GRADE_CHOICE] + _GRADE_CHOICES,
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context, svc: LiveUpdateService) -> None:
        if ctx.guild_id is None:
            await ctx.respond(_embed("Not here", "Use this in a server.", ok=False), ephemeral=True)
            return
        if not _is_admin(ctx):
            await ctx.respond(
                _embed("Nope", "You need **Manage Channels** to do that.", ok=False),
                ephemeral=True,
            )
            return
        try:
            channel_id = int(self.channel)
        except ValueError:
            await ctx.respond(
                _embed("Unknown channel", "Pick one from the list.", ok=False),
                ephemeral=True,
            )
            return

        level = _parse_level(self.min_level)
        grade = _parse_grade(self.min_grade if isinstance(self.min_grade, str) else self.min_grade.value)
        async with async_session() as db:
            applied = await svc.set_floor(
                db,
                int(ctx.guild_id),
                channel_id,
                min_level=level,
                min_grade=grade,
            )
        if not applied:
            await ctx.respond(
                _embed(
                    "Not allowed there",
                    f"<#{channel_id}> isn't set up for live score updates yet. "
                    "Allow it with `/liveupdates allow` first.",
                    ok=False,
                ),
                ephemeral=True,
            )
            return

        bars: list[str] = []
        if level is not None:
            bars.append(f"level **{decode_level(level)}** or higher")
        if grade is not None:
            bars.append(f"grade **{_grade_label(grade)}** or better")
        if not bars:
            body = f"<#{channel_id}> now takes whatever each member asked for."
        else:
            body = (
                f"<#{channel_id}> now only takes plays on a chart of "
                + " and at ".join(bars)
                + "."
            )
        await ctx.respond(_embed("Channel floor set", body), ephemeral=True)


@loader.command
@live_group.register
class Status(
    lightbulb.SlashCommand,
    name="status",
    description="Show where your live updates currently go",
):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context, svc: LiveUpdateService) -> None:
        async with async_session() as db:
            enabled, channel_id = await svc.resolve_destination(db, int(ctx.user.id))
            pref = await svc.get_pref(db, int(ctx.user.id))
            floor = None if channel_id is None else await svc.floor_for(db, channel_id)
            allowed = (
                await svc.allowed_channels(db, int(ctx.guild_id))
                if ctx.guild_id is not None
                else []
            )

        if not enabled:
            body = "**Off.** `/liveupdates on` starts them again."
        else:
            body = f"**On**, posting to {f'<#{channel_id}>' if channel_id else 'your **DMs**'}."
            # Explain the fallback rather than silently showing DM: the user
            # chose a channel and deserves to know why it is not being used.
            if pref is not None and pref.channel_id and channel_id is None:
                body += (
                    f"\n\nYou'd picked <#{pref.channel_id}>, but it no longer "
                    "allows live updates, so they're going to your DMs instead."
                )
            # body += f"\n\n{_SAMPLING_CAVEAT}"

        embed = _embed("Live updates", body)
        if enabled:
            embed.add_field(
                name="Posting",
                value="\n".join(f"- {line}" for line in _status_triggers(pref))
                or "- Nothing. `/liveupdates filters` turns something on.",
                inline=False,
            )
            gates = _status_gates(pref, floor, channel_id)
            if gates:
                embed.add_field(
                    name="Only when", value="\n".join(f"- {g}" for g in gates), inline=False
                )
        if allowed:
            embed.add_field(
                name="Allowed in this server",
                value="\n".join(f"<#{c}>" for c in allowed[:10]),
                inline=False,
            )
        await ctx.respond(embed, ephemeral=True)


loader.command(live_group)
