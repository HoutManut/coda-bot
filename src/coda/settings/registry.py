from __future__ import annotations

from coda.settings.types import ConfigKey, Scope
from coda.tournaments import options as tournament_options
from coda.utils.zones import DEFAULT_ZONE

REGISTRY: dict[str, ConfigKey] = {
    "polling": ConfigKey(
        name="polling",
        default="on",
        type=("on", "off"),
        guild_chain=(Scope.GLOBAL,),
        dm_chain=(Scope.GLOBAL,),
        description="Periodic score polling on/off (bot-wide). /recent still refreshes when off",
        audience="owner",
    ),
    # The poller re-reads this every tick, so a change lands without a restart.
    # Floored because the bot accounts are hand-made and unreplaceable; an open
    # tournament round still polls its keys faster (scores/schedule.py).
    "poll_interval": ConfigKey(
        name="poll_interval",
        default=90,
        type="int",
        guild_chain=(Scope.GLOBAL,),
        dm_chain=(Scope.GLOBAL,),
        description="Average seconds between two polls of one account (jittered +/-40%)",
        audience="owner",
        min_value=30,
    ),
    "timezone": ConfigKey(
        name="timezone",
        default=DEFAULT_ZONE,
        type="timezone",
        guild_chain=(Scope.GUILD, Scope.GLOBAL),
        dm_chain=(Scope.GLOBAL,),
        description="IANA zone this server's clock runs on (daily rollover, day/night art)",
    ),
    "chardle_epoch": ConfigKey(
        name="chardle_epoch",
        default="2026-07-27",
        type="str",
        guild_chain=(Scope.GLOBAL,),
        dm_chain=(Scope.GLOBAL,),
        description="Reference date of Chardle #1 (YYYY-MM-DD). Moving it renumbers every puzzle",
        audience="owner",
    ),
    "chardle_debug_board": ConfigKey(
        name="chardle_debug_board",
        default="off",
        type=("on", "off"),
        guild_chain=(Scope.GLOBAL,),
        dm_chain=(Scope.GLOBAL,),
        description="Chardle boards spell out every column AND REVEAL THE ANSWER (testing)",
        audience="owner",
    ),
    "chardle_bpm_window": ConfigKey(
        name="chardle_bpm_window",
        default=20,
        type="int",
        guild_chain=(Scope.GLOBAL,),
        dm_chain=(Scope.GLOBAL,),
        description="How far off a Chardle BPM guess can be and still show yellow",
        audience="owner",
    ),
    "chardle_note_window": ConfigKey(
        name="chardle_note_window",
        default=150,
        type="int",
        guild_chain=(Scope.GLOBAL,),
        dm_chain=(Scope.GLOBAL,),
        description="How far off a Chardle note-count guess can be and still show yellow",
        audience="owner",
    ),
    "chardle_abandon_hours": ConfigKey(
        name="chardle_abandon_hours",
        default=24,
        type="int",
        guild_chain=(Scope.GLOBAL,),
        dm_chain=(Scope.GLOBAL,),
        description="How long an untouched free-play board holds its channel's slot",
        audience="owner",
    ),
    "recent_b50_stat": ConfigKey(
        name="recent_b50_stat",
        default="never",
        type=("never", "b50", "b60", "b100", "always"),
        guild_chain=(Scope.USER, Scope.GLOBAL),
        dm_chain=(Scope.USER, Scope.GLOBAL),
        description="How deep in your ranking /recent and your live updates show potential impact",
    ),
    # Defaults to showing, unlike recent_b50_stat: this one prints a position
    # and never a rating, so it reveals nothing a hidden PTT was hiding.
    "score_rank_depth": ConfigKey(
        name="score_rank_depth",
        default="b50",
        type=("never", "b50", "b60", "b100", "always"),
        guild_chain=(Scope.USER, Scope.GLOBAL),
        dm_chain=(Scope.USER, Scope.GLOBAL),
        description="How deep in your ranking /score shows a chart's position",
    ),
    # The four tournament defaults exist for one reason: to keep
    # `/tournament quick with:@bob class:ftr` short. Every other choice is an
    # option on a surface where the user is already choosing things.
    # None is USER-writable: a match is shared state, and a per-user default
    # would mean two players in one match believe different rules apply while
    # the board can only draw one of them.
    "tournament_default_level": ConfigKey(
        name="tournament_default_level",
        default="",
        type="str",
        guild_chain=(Scope.GUILD, Scope.GLOBAL),
        dm_chain=(Scope.GLOBAL,),
        description="Level band quick matches draw from, e.g. 9-10+. Empty means any",
    ),
    "tournament_default_bans": ConfigKey(
        name="tournament_default_bans",
        default=True,
        type="bool",
        guild_chain=(Scope.GUILD, Scope.GLOBAL),
        dm_chain=(Scope.GLOBAL,),
        description="Whether a quick match opens with pick/ban",
    ),
    "tournament_default_best_of": ConfigKey(
        name="tournament_default_best_of",
        default="3",
        type=tournament_options.values(tournament_options.BEST_OF),
        guild_chain=(Scope.GUILD, Scope.GLOBAL),
        dm_chain=(Scope.GLOBAL,),
        description="How many rounds a quick match plays",
    ),
    "tournament_default_visibility": ConfigKey(
        name="tournament_default_visibility",
        default="public",
        type=tournament_options.values(tournament_options.VISIBILITY),
        guild_chain=(Scope.GUILD, Scope.GLOBAL),
        dm_chain=(Scope.GLOBAL,),
        description="Whether a quick match thread is readable by the whole server",
    ),
}


def user_keys() -> dict[str, ConfigKey]:
    """The registry as users may see it -- the single audience filter.

    Every user-facing choice list, autocomplete and rendered listing goes
    through this. Only the owner surface reads REGISTRY directly.
    """
    return {name: defn for name, defn in REGISTRY.items() if defn.audience == "user"}
