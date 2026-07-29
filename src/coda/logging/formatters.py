"""Formatters: console mimics hikari's coloured style; file is plain; discord is an embed.

The console format string is hikari's own default (`hikari.internal.ux`), so our
records line up with any hikari output rather than clashing with it.
"""

from __future__ import annotations

import logging

import colorlog
import hikari

_CONSOLE_FORMAT = (
    "%(log_color)s%(bold)s%(levelname)-1.1s%(thin)s "
    "%(asctime)23.23s "
    "%(bold)s%(name)s: "
    "%(thin)s%(message)s%(reset)s"
)
_PLAIN_FORMAT = "%(levelname)-1.1s %(asctime)23.23s %(name)s: %(message)s"

_EMBED_COLORS = {
    logging.DEBUG: 0x95A5A6,
    logging.INFO: 0x3498DB,
    logging.WARNING: 0xE67E22,
    logging.ERROR: 0xE74C3C,
    logging.CRITICAL: 0x992D22,
}
_DESCRIPTION_LIMIT = 4096
_FIELD_LIMIT = 1024


def console_formatter() -> logging.Formatter:
    """hikari-style coloured console formatter."""
    return colorlog.formatter.ColoredFormatter(_CONSOLE_FORMAT)


def file_formatter() -> logging.Formatter:
    """Plain (no colour codes) formatter for the rotating file."""
    return logging.Formatter(_PLAIN_FORMAT)


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def build_embed(record: logging.LogRecord) -> hikari.Embed:
    """One embed per log record: level as title/colour, message as body."""
    color = _EMBED_COLORS.get(record.levelno, _EMBED_COLORS[logging.CRITICAL])
    embed = hikari.Embed(
        title=record.levelname,
        description=_truncate(record.getMessage(), _DESCRIPTION_LIMIT),
        color=color,
    )
    embed.set_footer(text=record.name)
    if record.exc_info:
        trace = logging.Formatter().formatException(record.exc_info)
        embed.add_field("Traceback", f"```{_truncate(trace, _FIELD_LIMIT - 8)}```")
    return embed
