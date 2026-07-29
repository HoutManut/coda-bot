"""The /recent duplicate marker.

Scoped per DESTINATION, not per requester -- getting that wrong either drops a
post nobody has seen or double-posts one everybody has.
"""

from __future__ import annotations

import asyncio

import pytest

from coda.scores import poster
from coda.scores.suppression import PostSuppressor


def test_marked_play_is_suppressed_on_that_destination_only() -> None:
    suppressor = PostSuppressor()
    suppressor.mark(("channel", 100), 7)

    assert suppressor.suppressed(("channel", 100), 7)
    assert not suppressor.suppressed(("channel", 101), 7)
    assert not suppressor.suppressed(("dm", 100), 7)
    assert not suppressor.suppressed(("channel", 100), 8)


def test_a_dm_mark_is_private_to_that_user() -> None:
    """One user running /recent must never suppress another's DM."""
    suppressor = PostSuppressor()
    suppressor.mark(("dm", 1), 7)

    assert suppressor.suppressed(("dm", 1), 7)
    assert not suppressor.suppressed(("dm", 2), 7)


def test_marks_expire(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [0.0]
    monkeypatch.setattr("coda.scores.suppression.monotonic", lambda: clock[0])
    suppressor = PostSuppressor()
    suppressor.mark(("channel", 100), 7)

    clock[0] = 100.0
    assert suppressor.suppressed(("channel", 100), 7)
    clock[0] = 1000.0
    assert not suppressor.suppressed(("channel", 100), 7)


def test_submit_drops_rather_than_blocking_when_full() -> None:
    """A wedged poster must never stall the poll loop."""
    queue: asyncio.Queue[int] = asyncio.Queue(maxsize=2)
    poster.submit(queue, [1, 2, 3, 4])
    assert [queue.get_nowait(), queue.get_nowait()] == [1, 2]
    assert queue.empty()


def test_submit_without_a_poster_is_a_no_op() -> None:
    poster.submit(None, [1, 2, 3])
