"""The messages a match keeps: its board, its prompt, and its beats.

Two things write the board -- a pick/ban click and the sweep -- so writes take
a per-match lock. ``asyncio.Lock`` releases its waiters FIFO, so ordering is
free while different matches proceed in parallel; same shape as the
per-destination lock in ``scores/poster.py``.

There is no separate debounce. The sweep is the only thing that reacts to
ingest and it runs on a fixed tick, so the board cannot be edited faster than
that no matter how many scores land -- and unlike a debounce, a tick cannot
drop the last frame.

The other two exist because Discord does not notify on an edit, so a board that
starts waiting on somebody has to say so out loud:

* a **prompt** is one line naming who is owed and what for (``prompts.py``).
  Posted at most once per wait: ``refresh`` compares the wait's key against the
  one on the match and says nothing at all while it is unchanged, which is what
  makes it safe to call on every tick and after every click. When the wait
  ends the message is never just left there: it is rewritten into what happened
  where there is something to report, and deleted where there is not.
* a **beat** is a moment worth a message -- a chart revealed, a round decided.
  ``say`` takes no lock (an append races with nothing) and reports whether the
  message landed, because the caller only stamps the beat as said once it did.
"""

from __future__ import annotations

import asyncio
import logging

import hikari
from hikari.impl import MessageActionRowBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from coda.db.models import TournamentMatch
from coda.tournaments import prompts, render, viewbuild
from coda.tournaments.views import MatchView

logger = logging.getLogger(__name__)


class BoardService:
    """Holds the per-match FIFO locks, so it must be a single instance."""

    def __init__(self) -> None:
        self._locks: dict[int, asyncio.Lock] = {}

    def lock(self, match_id: int) -> asyncio.Lock:
        return self._locks.setdefault(match_id, asyncio.Lock())

    def release(self, match_id: int) -> None:
        self._locks.pop(match_id, None)

    async def refresh(
        self, app: hikari.RESTAware, db: AsyncSession, match: TournamentMatch
    ) -> None:
        """Bring the thread up to date: redraw the board, reconcile the prompt.

        One call for both because they are one moment -- the board says what
        the match now looks like and the prompt asks for whatever it now needs,
        and a caller that could do one without the other would eventually do
        exactly that.

        The view is built once and handed to both. Two builds would run every
        query twice and, worse, could disagree: the second sees a clock that
        has moved.
        """
        view = await viewbuild.build(db, match)
        await self._draw(app, match, view)
        await self._reprompt(app, db, match, view)

    async def post(
        self, app: hikari.RESTAware, db: AsyncSession, match: TournamentMatch
    ) -> int | None:
        """Put a fresh board in the thread and remember it. Returns its id."""
        rendered = render.board(await viewbuild.build(db, match))
        async with self.lock(match.id):
            try:
                message = await app.rest.create_message(
                    match.thread_id, components=[rendered.build()]
                )
            except hikari.HikariError:
                logger.info(
                    "tournaments: cannot post a board in %s", match.thread_id)
                return None
        match.board_message_id = int(message.id)
        await db.flush()
        return match.board_message_id

    async def _draw(
        self, app: hikari.RESTAware, match: TournamentMatch, view: MatchView
    ) -> None:
        """Redraw the board where it already is. Silent if the message is gone.

        A lost message is recovered by ``/tournament board``, never by an
        automatic repost: a repost loop would fight the conversation the thread
        exists to host.
        """
        if match.board_message_id is None:
            return
        rendered = render.board(view)
        async with self.lock(match.id):
            try:
                await app.rest.edit_message(
                    match.thread_id,
                    match.board_message_id,
                    components=[rendered.build()],
                )
            except hikari.HikariError:
                logger.info(
                    "tournaments: cannot edit board for match %s", match.id)

    async def _reprompt(
        self,
        app: hikari.RESTAware,
        db: AsyncSession,
        match: TournamentMatch,
        view: MatchView,
    ) -> None:
        """Say the line the current wait owes, if it has not been said.

        Keyed, so this is idempotent: called on every tick and after every
        click, it does nothing at all while the wait is unchanged. That is what
        makes it safe to hang off ``refresh`` rather than off having witnessed
        a transition, and it is why a restart mid-match says nothing twice.

        Committed here rather than left to the caller, for the reason a beat's
        stamp is: this records that a message was SENT. Rolling that back would
        say it again, and every caller already commits before it refreshes.
        """
        wanted = prompts.current(view)
        key = wanted.key if wanted is not None else None
        if key == match.prompt_key:
            return
        await self._retire(app, match, view)
        posted = (
            None if wanted is None
            else await self._send(app, match.thread_id, wanted)
        )
        if wanted is not None and posted is None:
            # Unsaid, so the next pass simply tries again.
            return
        match.prompt_key = key
        match.prompt_message_id = posted
        await db.commit()

    async def _send(
        self, app: hikari.RESTAware, thread_id: int, prompt: prompts.Prompt
    ) -> int | None:
        try:
            message = await app.rest.create_message(
                thread_id,
                prompt.text,
                components=prompt.rows,
                user_mentions=prompt.mentions or False,
            )
        except hikari.HikariError:
            logger.info("tournaments: cannot post a prompt in %s", thread_id)
            return None
        return int(message.id)

    async def _retire(
        self, app: hikari.RESTAware, match: TournamentMatch, view: MatchView
    ) -> None:
        """Settle the message the finished wait left behind.

        Rewritten into its outcome where there is one ("your ban" becomes
        "Smol-Don banned Grievous Lady"), which keeps the thread reading as a
        log rather than as a column of questions nobody answered. Deleted where
        there is not: what a start or break line carried was a button and a
        countdown, and neither has a true form once the wait is over.

        Components go either way. A button that no longer works is worse than
        no button, and the line it sat on is now a statement.

        Best-effort. A message that cannot be settled is forgotten anyway; the
        alternative is a match that will not advance because one old message
        will not tidy up.
        """
        if match.prompt_message_id is None:
            return
        outcome = prompts.resolved(view, match.prompt_key)
        try:
            if outcome is None:
                await app.rest.delete_message(
                    match.thread_id, match.prompt_message_id)
            else:
                await app.rest.edit_message(
                    match.thread_id,
                    match.prompt_message_id,
                    outcome,
                    components=[],
                    user_mentions=False,
                )
        except hikari.HikariError:
            logger.info(
                "tournaments: cannot retire the prompt in %s", match.thread_id)
        match.prompt_message_id = None

    async def say(
        self,
        app: hikari.RESTAware,
        thread_id: int,
        text: str,
        mentions: list[int],
        rows: list[MessageActionRowBuilder] | None = None,
    ) -> bool:
        """Post one beat into the thread. False if it did not land.

        Mentions are passed explicitly rather than left to Discord's parser:
        the roster is the only thing in a match that may ping, and a chart
        title is arbitrary text that must never be able to.
        """
        try:
            await app.rest.create_message(
                thread_id,
                text,
                components=rows or [],
                user_mentions=mentions or False,
            )
        except hikari.HikariError:
            logger.info("tournaments: cannot post a beat in %s", thread_id)
            return False
        return True
