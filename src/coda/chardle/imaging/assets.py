"""Loading the board's PNG furniture, and stretching it to the board's width.

Plates ship at the prototype's fixed 1600px. The grid here is measured from its
content instead, so every plate is 9-sliced to whatever width the board came out
at: the end caps are copied intact and the middle band, a flat horizontal
gradient, is stretched between them.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image

from coda.catalog.jackets import BASE_JACKET, jacket_path
from coda.chardle.feedback import Arrow, Cell, Color

CHARDLE_DIR = Path("assets/chardle")

CAP = 80
JACKET_SIZE = 168

_WASH_NAMES: dict[Color, str] = {
    Color.GREEN: "green",
    Color.YELLOW: "yellow",
    Color.RED: "red",
}
_ARROW_SUFFIX: dict[Arrow, str] = {Arrow.NONE: "", Arrow.UP: "_up", Arrow.DOWN: "_down"}


@lru_cache(maxsize=None)
def load(name: str) -> Image.Image:
    """One furniture PNG, cached. Callers must not draw into the result."""
    return Image.open(CHARDLE_DIR / name).convert("RGBA")


def header(width: int) -> Image.Image:
    return stretch(load("header.png"), width)


def plate(side: int, *, beyond: bool) -> Image.Image:
    """The row backing for one side. Lephon (side 3) has no art of its own and
    Colorless has no Beyond variant, so ``3.png``/``2_BYD.png``/``3_BYD.png``
    are copies of the plain Colorless plate."""
    return load(f"{side}{'_BYD' if beyond else ''}.png")


def stand() -> Image.Image:
    return load("stand.png")


def frame(side: int) -> Image.Image:
    return load(f"back/{side}.png")


def pill(side: int) -> Image.Image:
    return load(f"shadow_{side}.png")


def wash(cell: Cell, width: int) -> Image.Image | None:
    """The feedback gradient for one cell, or ``None`` when it says nothing."""
    name = _WASH_NAMES.get(cell.color)
    if name is None:
        return None
    return stretch(load(f"hint/{name}{_ARROW_SUFFIX[cell.arrow]}.png"), width)


def jacket(song_id: str, stem: str) -> Image.Image:
    """The chart's cover art at board size.

    No JP or night variant: a board is edited from background tasks and has no
    viewer locale to resolve them against. Files are WebP, 512-768px square.
    """
    path = jacket_path(song_id, stem, jp=False, night=False) or BASE_JACKET
    art = Image.open(path).convert("RGBA")
    return art.resize((JACKET_SIZE, JACKET_SIZE), Image.LANCZOS) # type: ignore


def stretch(source: Image.Image, width: int) -> Image.Image:
    """``source`` widened to ``width``, keeping its end caps unscaled."""
    if width <= source.width:
        return source.resize((width, source.height), Image.LANCZOS) # type: ignore
    out = Image.new("RGBA", (width, source.height), (0, 0, 0, 0))
    middle = source.crop((CAP, 0, source.width - CAP, source.height))
    out.paste(middle.resize((width - 2 * CAP, source.height), Image.LANCZOS), (CAP, 0)) # type: ignore
    out.paste(source.crop((0, 0, CAP, source.height)), (0, 0))
    out.paste(source.crop((source.width - CAP, 0, source.width, source.height)),
              (width - CAP, 0))
    return out
