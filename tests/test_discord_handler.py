"""DiscordChannelHandler: emit never blocks, consumer posts one embed per record.

Covers the failure modes that would either crash logging or take the bot down:
buffering before the loop exists, dropping on a full queue, and swallowing a
failed post (which must never re-raise -- it would cascade back through here).
"""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

import hikari

from coda.logging.discord_handler import DiscordChannelHandler

CHANNEL_ID = 123456789


def _record(level: int = logging.WARNING, msg: str = "boom") -> logging.LogRecord:
    return logging.LogRecord("coda.thing", level, "f.py", 1, msg, None, None)


def _app() -> MagicMock:
    app = MagicMock(spec=hikari.RESTAware)
    app.rest.create_message = AsyncMock()
    return app


def test_emit_before_loop_buffers_without_error() -> None:
    handler = DiscordChannelHandler(CHANNEL_ID, level=logging.DEBUG)
    handler.emit(_record())
    assert len(handler._prestart) == 1
    embed, ping = handler._prestart[0]
    assert isinstance(embed, hikari.Embed)
    assert ping is False  # only a record flagged ping=True mentions the owner


def test_enqueue_drops_on_full_queue_without_blocking() -> None:
    handler = DiscordChannelHandler(CHANNEL_ID, level=logging.DEBUG)
    handler._queue = asyncio.Queue(maxsize=1)
    handler._enqueue(hikari.Embed(), False)
    handler._enqueue(hikari.Embed(), False)  # queue is full -> dropped, no block
    assert handler._dropped == 1


async def test_consumer_posts_buffered_record_as_embed() -> None:
    handler = DiscordChannelHandler(CHANNEL_ID, level=logging.DEBUG)
    handler.emit(_record(msg="hello"))
    app = _app()

    handler.start(app, asyncio.get_running_loop())
    await asyncio.wait_for(handler._queue.join(), timeout=1.0)
    await handler.stop()

    app.rest.create_message.assert_awaited_once()
    args, kwargs = app.rest.create_message.call_args
    assert args[0] == CHANNEL_ID
    assert isinstance(kwargs["embed"], hikari.Embed)


async def test_failed_post_is_swallowed_and_consumer_survives() -> None:
    handler = DiscordChannelHandler(CHANNEL_ID, level=logging.DEBUG)
    app = _app()
    app.rest.create_message.side_effect = [RuntimeError("down"), None]

    handler.start(app, asyncio.get_running_loop())
    handler.emit(_record(msg="first"))
    handler.emit(_record(msg="second"))
    await asyncio.sleep(0)  # let the call_soon_threadsafe enqueues run before join
    await asyncio.wait_for(handler._queue.join(), timeout=1.0)

    assert app.rest.create_message.await_count == 2  # survived the first failure
    assert handler._task is not None
    assert not handler._task.done()
    await handler.stop()
