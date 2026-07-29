"""The font chain, and which font draws which character.

Routing reads each font's own cmap rather than guessing from character class.
The catalog carries Greek, Cyrillic, IPA, subscripts, math arrows, currency
signs and CJK in song titles and artist credits, and any hand-written
"is this Latin" test gets some of them wrong.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import ImageFont

FONTS_DIR = Path("assets/fonts")

# Ordered: the first file whose cmap covers a character draws it. Latin leads so
# the JP font's full-width Latin forms never win a character both can draw.
CHAIN: tuple[str, ...] = (
    "NotoSans-Medium.ttf",
    "NotoSansJP-Medium.ttf",
    "NotoSansMath-Regular.ttf",
)


@dataclass(frozen=True)
class Run:
    """A slice of a string that one font can draw."""

    text: str
    font: ImageFont.FreeTypeFont


@lru_cache(maxsize=None)
def coverage(file: str) -> frozenset[int]:
    """Every codepoint one font file can draw."""
    return frozenset(TTFont(FONTS_DIR / file, lazy=True).getBestCmap() or {})


@lru_cache(maxsize=None)
def load(file: str, size: int) -> ImageFont.FreeTypeFont:
    """One sized face, cached -- a board reloads the same handful constantly."""
    return ImageFont.truetype(FONTS_DIR / file, size)


def file_for(char: str) -> str | None:
    """The first font in the chain covering ``char``, or ``None`` for tofu."""
    point = ord(char)
    for file in CHAIN:
        if point in coverage(file):
            return file
    return None


def split_runs(text: str, size: int) -> list[Run]:
    """``text`` cut into the longest slices a single font can draw.

    A combining mark stays with the character it modifies -- its font is the
    base's, never its own -- and is dropped when that font cannot draw it.
    Both halves matter for the song ``ii`` (``Ⅱ`` plus five marks, the only
    place in the catalog this arises). Splitting the base off its marks scatters
    them across separate pen positions, while keeping a mark the base's font
    lacks draws .notdef, and .notdef carries an advance where a real mark
    carries none -- that is the box-and-gap the prototype papered over with an
    image of the title.
    """
    runs: list[tuple[str, list[str]]] = []
    for char in unicodedata.normalize("NFC", text):
        if runs and unicodedata.combining(char):
            if ord(char) in coverage(runs[-1][0]):
                runs[-1][1].append(char)
            continue
        file = file_for(char) or CHAIN[0]
        if runs and runs[-1][0] == file:
            runs[-1][1].append(char)
        else:
            runs.append((file, [char]))
    return [Run("".join(chars), load(file, size)) for file, chars in runs]
