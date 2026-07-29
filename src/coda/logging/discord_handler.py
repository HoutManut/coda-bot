"""A logging handler that posts each record to a Discord channel as an embed.

``emit`` is synchronous and must never block the event loop or do network I/O,
so posting is decoupled through an ``asyncio.Queue`` drained by a background task:

    emit(record)  -->  build embed  -->  enqueue  (drop if full, never block)
    consumer task -->  await app.rest.create_message(...)  (one embed per record)

The handler is built before the gateway is up, so records emitted during startup
buffer in a plain deque until ``start`` hands over a running loop and REST app.

Failures inside the consumer are written to stderr only -- never re-logged, which
would cascade back through this same handler.
"""

from __future__ import annotations

import asyncio
import collections
import logging
import sys
import traceback

import hikari

from coda.config import config
from coda.logging.formatters import build_embed

_QUEUE_MAXSIZE = 1000


class DiscordChannelHandler(logging.Handler):
    """Posts records to one channel, one embed each, off the event loop's hot path."""

    def __init__(self, channel_id: int, level: int) -> None:
        super().__init__(level=level)
        self._channel_id = channel_id
        self._queue: asyncio.Queue[tuple[hikari.Embed, bool]] = asyncio.Queue(
            maxsize=_QUEUE_MAXSIZE
        )
        self._prestart: collections.deque[tuple[hikari.Embed, bool]] = collections.deque(
            maxlen=_QUEUE_MAXSIZE
        )
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task[None] | None = None
        self._dropped = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            embed = build_embed(record)
        except Exception:  # noqa: BLE001 -- a bad format must never crash logging
            self.handleError(record)
            return
        ping = getattr(record, "ping", False) is True
        if self._loop is None:
            self._prestart.append((embed, ping))
        else:
            self._loop.call_soon_threadsafe(self._enqueue, embed, ping)

    def _enqueue(self, embed: hikari.Embed, ping: bool) -> None:
        try:
            self._queue.put_nowait((embed, ping))
        except asyncio.QueueFull:
            self._dropped += 1
            print(
                f"[coda.logging] discord log queue full; dropped {self._dropped} record(s)",
                file=sys.stderr,
            )

    def start(self, app: hikari.RESTAware, loop: asyncio.AbstractEventLoop) -> None:
        """Bind the live REST app + loop, flush buffered records, spawn the consumer."""
        self._loop = loop
        while self._prestart:
            self._enqueue(*self._prestart.popleft())
        self._task = loop.create_task(self._consume(app))

    async def _consume(self, app: hikari.RESTAware) -> None:
        while True:
            embed, ping = await self._queue.get()
            owner_id = config.main_owner_id
            content = f"<@{owner_id}>" if ping and owner_id else None
            try:
                await app.rest.create_message(
                    self._channel_id,
                    content=content,
                    embed=embed,
                    user_mentions=[owner_id] if content else False,
                )
            except Exception:  # noqa: BLE001 -- never re-log; that would feed back into here
                traceback.print_exc(file=sys.stderr)
            finally:
                self._queue.task_done()

    async def stop(self) -> None:
        """Best-effort drain of pending records, then stop the consumer."""
        if self._task is None:
            return
        await asyncio.sleep(0)  # let a just-emitted record's call_soon enqueue run first
        try:
            await asyncio.wait_for(self._queue.join(), timeout=5.0)
        except (TimeoutError, asyncio.CancelledError):
            pass
        self._task.cancel()
        self._task = None
