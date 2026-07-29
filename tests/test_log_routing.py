"""RouteFilter: per-handler threshold that a single record can override either way.

High-risk per CODING_STYLE -- the whole point of the logging design is that a
below-threshold record can be forced onto an output and an above-threshold one
held back, and that regresses silently.
"""

from __future__ import annotations

import logging

from coda.logging.routing import RouteFilter


def _record(level: int, name: str = "coda.thing", **extra) -> logging.LogRecord:
    record = logging.LogRecord(name, level, "f.py", 1, "msg", None, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_threshold_admits_at_or_above() -> None:
    filt = RouteFilter("discord", logging.WARNING)
    assert filt.filter(_record(logging.WARNING)) is True
    assert filt.filter(_record(logging.ERROR)) is True


def test_threshold_drops_below() -> None:
    filt = RouteFilter("discord", logging.WARNING)
    assert filt.filter(_record(logging.INFO)) is False


def test_flag_true_forces_below_threshold_record_in() -> None:
    filt = RouteFilter("discord", logging.WARNING)
    assert filt.filter(_record(logging.DEBUG, discord=True)) is True


def test_flag_false_forces_above_threshold_record_out() -> None:
    filt = RouteFilter("discord", logging.WARNING)
    assert filt.filter(_record(logging.ERROR, discord=False)) is False


def test_flag_key_is_per_handler() -> None:
    # A console flag must not steer the discord handler.
    filt = RouteFilter("discord", logging.WARNING)
    assert filt.filter(_record(logging.INFO, console=True)) is False


def test_discord_mutes_noisy_namespaces_by_default() -> None:
    filt = RouteFilter("discord", logging.WARNING)
    assert filt.filter(_record(logging.ERROR, name="hikari.gateway")) is False
    assert filt.filter(_record(logging.ERROR, name="coda.logging.setup")) is False


def test_discord_mute_is_overridable() -> None:
    filt = RouteFilter("discord", logging.WARNING)
    assert filt.filter(_record(logging.ERROR, name="hikari.gateway", discord=True)) is True


def test_non_discord_handler_does_not_mute_namespaces() -> None:
    filt = RouteFilter("file", logging.DEBUG)
    assert filt.filter(_record(logging.ERROR, name="hikari.gateway")) is True
