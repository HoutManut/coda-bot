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
    # tuple of strings = enum; "str"/"bool"/"int" = freeform primitive
    type: Literal["str", "bool", "int"] | tuple[str, ...]
    guild_chain: tuple[Scope, ...]
    dm_chain: tuple[Scope, ...]
    description: str = field(default="")

    @property
    def settable_scopes(self) -> set[Scope]:
        return set(self.guild_chain) | set(self.dm_chain)

    @property
    def choices(self) -> list[str] | None:
        if isinstance(self.type, tuple):
            return list(self.type)
        return None
