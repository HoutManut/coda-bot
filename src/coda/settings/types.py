from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Literal


class Scope(str, enum.Enum):
    GLOBAL = "global"
    GUILD = "guild"
    CHANNEL = "channel"
    USER = "user"


@dataclass(frozen=True)
class ConfigKey:
    name: str
    default: Any
    # tuple of strings = enum; the rest are freeform primitives validated by
    # coda.settings.parse -- "timezone" is a str that must name an IANA zone.
    type: Literal["str", "bool", "int", "timezone"] | tuple[str, ...]
    guild_chain: tuple[Scope, ...]
    dm_chain: tuple[Scope, ...]
    description: str = field(default="")
    # Who may see the key exists. Visibility only -- settable_scopes still
    # decides where it can be written. Defaults to "user": forgetting to think
    # about it leaves a noisy picker, never a silent gate.
    audience: Literal["user", "owner"] = "user"
    # Smallest value an "int" key accepts; None = unbounded. Enforced at parse
    # time so a value that would break its consumer can never be stored.
    min_value: int | None = None

    @property
    def settable_scopes(self) -> set[Scope]:
        return set(self.guild_chain) | set(self.dm_chain)

    @property
    def choices(self) -> list[str] | None:
        if isinstance(self.type, tuple):
            return list(self.type)
        return None
