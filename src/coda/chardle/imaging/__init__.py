"""Composited Chardle board images.

Pure and synchronous: give it a :class:`~coda.chardle.render.Board`, get PNG-free
WebP bytes back. Callers run it off the event loop -- a full board is a
megapixel-scale composite plus a jacket decode, on every guess.
"""

from __future__ import annotations

from coda.chardle.imaging.compose import board_image
from coda.chardle.imaging.encode import encode
from coda.chardle.views import Board

__all__ = ["render_board"]


def render_board(board: Board, *, final: bool) -> bytes:
    """The board as an image. ``final`` renders it full-size for a finished game."""
    return encode(board_image(board), final=final)
