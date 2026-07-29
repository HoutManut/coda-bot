"""Per-handler routing: a level threshold that any single record can override.

stdlib gates a record at ``record.levelno >= handler.level`` *before* a
handler's filters run, so a handler-level threshold cannot be lifted upward by a
below-threshold record. We therefore leave every handler at ``DEBUG`` (it sees
everything) and enforce the real threshold here, in a filter that also honours a
per-record boolean override.

Call sites stay plain stdlib -- steering is data on the record, set via ``extra``:

    logger.info("x", extra={"discord": True})     # force onto discord, ignores threshold
    logger.warning("y", extra={"discord": False}) # hold back off discord, ignores threshold
    logger.error("z", extra={"ping": True})        # also @-mention main_owner_id on discord

The three handler keys are ``console``, ``file`` and ``discord``. ``ping`` is a
separate flag read directly by ``DiscordChannelHandler``, not a routing key.
"""

from __future__ import annotations

import logging

CONSOLE = "console"
FILE = "file"
DISCORD = "discord"

# Records from these logger namespaces never reach the discord handler unless
# a call site opts in explicitly (extra={"discord": True}). A failed discord
# post logs through hikari/aiohttp; without this guard that would cascade back
# into more discord posts.
_DISCORD_MUTED_PREFIXES = ("hikari", "aiohttp", "coda.logging", "py.warnings")


class RouteFilter(logging.Filter):
    """Threshold for one handler, overridable per record by a boolean ``extra`` flag."""

    def __init__(self, handler_key: str, threshold: int) -> None:
        super().__init__()
        self.handler_key = handler_key
        self.threshold = threshold

    def filter(self, record: logging.LogRecord) -> bool:
        flag = getattr(record, self.handler_key, None)
        if flag is True:
            return True
        if flag is False:
            return False
        if self.handler_key == DISCORD and record.name.startswith(_DISCORD_MUTED_PREFIXES):
            return False
        return record.levelno >= self.threshold
