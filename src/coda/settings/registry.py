from __future__ import annotations

from coda.settings.types import ConfigKey, Scope
from coda.utils.zones import DEFAULT_ZONE

REGISTRY: dict[str, ConfigKey] = {
    "polling": ConfigKey(
        name="polling",
        default="on",
        type=("on", "off"),
        guild_chain=(Scope.GLOBAL,),
        dm_chain=(Scope.GLOBAL,),
        description="Periodic score polling (bot-wide)",
        audience="owner",
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
    "recent_b30_stat": ConfigKey(
        name="recent_b30_stat",
        default="never",
        type=("never", "b30", "b40", "b100", "always"),
        guild_chain=(Scope.USER, Scope.GLOBAL),
        dm_chain=(Scope.USER, Scope.GLOBAL),
        description="How deep in your ranking /recent shows b30 impact",
    ),
}


def user_keys() -> dict[str, ConfigKey]:
    """The registry as users may see it -- the single audience filter.

    Every user-facing choice list, autocomplete and rendered listing goes
    through this. Only the owner surface reads REGISTRY directly.
    """
    return {name: defn for name, defn in REGISTRY.items() if defn.audience == "user"}
