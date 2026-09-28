"""Submitted string -> the value a config key actually stores.

Every write path goes through here. ``set_value`` writes ``{"v": value}`` into
JSON verbatim, so an uncoerced ``"20"`` for an int key comes back out of
``resolve`` as a string and diverges from the registry default weeks later.
"""

from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from coda.settings.types import ConfigKey

_TRUE = frozenset({"on", "true", "yes", "1"})
_FALSE = frozenset({"off", "false", "no", "0"})


def parse_value(defn: ConfigKey, raw: str) -> Any:
    """Coerce and validate ``raw`` against the key's declared type.

    Raises ``ValueError`` whose message is meant for the person who typed it --
    every caller is a command surface handing over free text.
    """
    if isinstance(defn.type, tuple):
        if raw not in defn.type:
            valid = ", ".join(f"`{option}`" for option in defn.type)
            raise ValueError(f"Not a valid option for **{defn.name}**. Choose from: {valid}")
        return raw

    if defn.type == "int":
        try:
            value = int(raw)
        except ValueError:
            raise ValueError(f"**{defn.name}** takes a whole number, not `{raw}`.") from None
        if defn.min_value is not None and value < defn.min_value:
            raise ValueError(f"**{defn.name}** must be at least `{defn.min_value}`.")
        return value

    if defn.type == "bool":
        lowered = raw.lower()
        if lowered in _TRUE:
            return True
        if lowered in _FALSE:
            return False
        raise ValueError(f"**{defn.name}** takes on or off, not `{raw}`.")

    if defn.type == "timezone":
        try:
            ZoneInfo(raw)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(
                f"`{raw}` is not an IANA timezone name (e.g. `Asia/Bangkok`)."
            ) from None
        return raw

    return raw
