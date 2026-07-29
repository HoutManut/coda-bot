"""Chardle — Wordle over the Arcaea catalog.

A pure catalog consumer: it imports ``catalog/``, ``db/`` and ``settings/`` and
**never** ``arcaea/`` or ``sessions/``. Every fact it compares is catalog data,
so the whole minigame plays fine with lowiro unreachable.
"""

from __future__ import annotations

from coda.chardle.channels import ChardleChannelService
from coda.chardle.guess import GuessService
from coda.chardle.puzzle import PuzzleService
from coda.chardle.session import SessionService
from coda.chardle.stats import StatsService

__all__ = [
    "PuzzleService",
    "GuessService",
    "SessionService",
    "StatsService",
    "ChardleChannelService",
]
