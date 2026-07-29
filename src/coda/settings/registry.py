from __future__ import annotations

from coda.settings.types import ConfigKey, Scope

REGISTRY: dict[str, ConfigKey] = {
    "locale": ConfigKey(
        name="locale",
        default="en",
        type=("en", "ja"),
        guild_chain=(Scope.CHANNEL, Scope.GUILD, Scope.GLOBAL),
        dm_chain=(Scope.USER, Scope.GLOBAL),
        description="Display language",
    ),
    # Bot-wide only: no guild or user has any business pausing the poller, so
    # GLOBAL is the whole chain and /config global is the only way in. Off stops
    # the PERIODIC sweep; an on-demand refresh (/recent) still polls the one
    # account it needs. The poller re-reads this every tick, so it takes effect
    # without a restart.
    "polling": ConfigKey(
        name="polling",
        default="on",
        type=("on", "off"),
        guild_chain=(Scope.GLOBAL,),
        dm_chain=(Scope.GLOBAL,),
        description="Periodic score polling (bot-wide)",
    ),
}
