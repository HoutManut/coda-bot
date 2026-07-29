"""Encode/decode the integer storage forms of chart level and rating.

A level is held as ``value * 2`` (plus 1 for a "+" level), and a chart
constant (CC) is held as ``value * 10``. Sentinels: ``0`` = unknown ("?"),
``-1`` = none ("?"), same symbol.
"""

from __future__ import annotations


def encode_level(text: str) -> int:
    """Parse a displayed level ("9", "10+", "?") into its stored integer."""
    if text == "?":
        return -1
    if text.endswith("+"):
        return int(text[:-1]) * 2 + 1
    return int(text) * 2


def decode_level(value: int) -> str:
    """Render a stored level integer back to its displayed string."""
    if value == -1:
        return "?"
    if value == 0:
        return "?"
    if value % 2 == 0:
        return str(value // 2)
    return f"{(value - 1) // 2}+"


def encode_rating(value: float) -> int:
    """Encode a chart constant (e.g. 9.3) to its stored integer (93)."""
    return int(round(value * 10))


def decode_rating(value: int) -> float:
    """Decode a stored rating integer to its chart constant. ``<= 0`` passes through."""
    if value <= 0:
        return float(value)
    return value / 10
