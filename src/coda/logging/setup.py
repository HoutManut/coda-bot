"""Central logging configuration: build handlers, set levels, wire the discord path.

Called once from an entrypoint (``bot.build``); has no import-time side effects so
alembic and the admin app can import ``coda.config`` without touching logging.

Level strategy: the ``coda`` logger sits at DEBUG (its records are always created,
so a below-threshold record can still be force-routed by a per-record flag), while
the root logger sits at WARNING (third-party libraries stay quiet without per-library
config). Every handler is itself at DEBUG; the real per-handler threshold lives in a
``RouteFilter`` so a record can be steered past it -- see ``routing.py``.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import hikari

from coda.config import config
from coda.logging import routing
from coda.logging.discord_handler import DiscordChannelHandler
from coda.logging.formatters import console_formatter, file_formatter
from coda.logging.routing import RouteFilter

_FILE_MAX_BYTES = 10 * 1024 * 1024
_FILE_BACKUPS = 5

_discord_handler: DiscordChannelHandler | None = None


def _level(name: str) -> int:
    return logging.getLevelNamesMapping().get(name.upper(), logging.INFO)


def _run_log_path(directory: str) -> Path:
    """Path for this run's log file: ``<dir>/coda_<date>_<time>.log``.

    One file per process start, so a crash is read without slicing a shared log
    by timestamp. Size rotation still applies within a run (``.1``, ``.2``, ...).
    """
    folder = Path(directory).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return folder / f"coda_{stamp}.log"


def _own(handler: logging.Handler, key: str, threshold: int) -> logging.Handler:
    handler.setLevel(logging.DEBUG)
    handler.addFilter(RouteFilter(key, threshold))
    handler._coda_owned = True  # type: ignore[attr-defined]
    return handler


def configure_logging() -> None:
    """Attach the console/file/discord handlers to the root logger.

    Call this *before* constructing the bot so records emitted during
    ``GatewayBot.__init__`` (e.g. hikari's optimization-level warning) land on our
    handlers instead of logging's raw last-resort. Idempotent: a second call
    replaces the handlers this module installed rather than stacking duplicates.
    The discord handler is built whenever a channel is configured; its consumer
    binds the live app and starts later via :func:`start_discord`.
    """
    global _discord_handler

    root = logging.getLogger()
    for existing in [h for h in root.handlers if getattr(h, "_coda_owned", False)]:
        root.removeHandler(existing)
    _discord_handler = None

    console = logging.StreamHandler()
    console.setFormatter(console_formatter())
    console_level = _level(config.log_level)
    root.addHandler(_own(console, routing.CONSOLE, console_level))
    thresholds = [console_level]

    if config.log_dir:
        file_handler = RotatingFileHandler(
            _run_log_path(config.log_dir),
            maxBytes=_FILE_MAX_BYTES,
            backupCount=_FILE_BACKUPS,
        )
        file_handler.setFormatter(file_formatter())
        file_level = _level(config.log_file_level)
        root.addHandler(_own(file_handler, routing.FILE, file_level))
        thresholds.append(file_level)

    if config.log_discord_channel_id is not None:
        _discord_handler = DiscordChannelHandler(
            config.log_discord_channel_id, level=logging.DEBUG
        )
        discord_level = _level(config.log_discord_level)
        root.addHandler(_own(_discord_handler, routing.DISCORD, discord_level))
        thresholds.append(discord_level)

    # Root floor = the most verbose enabled output, so third-party (hikari,
    # lightbulb) records are actually created down to what some handler wants to
    # show. `coda` stays at DEBUG unconditionally so a per-record force-route of a
    # coda debug still works even when every handler's threshold is higher.
    root.setLevel(min(thresholds))
    logging.getLogger("coda").setLevel(logging.DEBUG)

    # Route warnings.warn(...) through logging (as hikari's dropped auto-config
    # did) so they format like everything else instead of printing raw.
    logging.captureWarnings(True)


def start_discord(app: hikari.RESTAware) -> None:
    """Start the discord log consumer once the gateway is up (StartingEvent)."""
    if _discord_handler is not None:
        _discord_handler.start(app, asyncio.get_running_loop())


async def stop_discord() -> None:
    """Flush and stop the discord log consumer on shutdown (StoppingEvent)."""
    if _discord_handler is not None:
        await _discord_handler.stop()
