"""Assert the board's font chain can draw every string the catalog holds.

Run after changing ``coda.chardle.imaging.fonts.CHAIN`` or after a catalog
import brings in new songs. Anything reported uncovered renders as tofu on a
Chardle board.

    uv run python scripts/check_font_coverage.py
"""

from __future__ import annotations

import asyncio
import collections
import sys
import unicodedata

from sqlalchemy import select

from coda.chardle.imaging.fonts import CHAIN, file_for
from coda.db.models import Song, SongDifficulty
from coda.db.session import async_session


async def _catalog_strings() -> list[str]:
    async with async_session() as db:
        songs = (
            await db.execute(select(Song.name_en, Song.name_jp, Song.artist))
        ).all()
        charts = (
            await db.execute(
                select(
                    SongDifficulty.name_en,
                    SongDifficulty.artist,
                    SongDifficulty.chart_designer,
                )
            )
        ).all()
    return [value for row in [*songs, *charts] for value in row if value]


def _demand(strings: list[str]) -> collections.Counter[str]:
    counts: collections.Counter[str] = collections.Counter()
    for text in strings:
        for char in unicodedata.normalize("NFC", text):
            if not char.isspace():
                counts[char] += 1
    return counts


def _report(counts: collections.Counter[str]) -> int:
    drawn: collections.Counter[str] = collections.Counter()
    uncovered: list[str] = []
    for char in counts:
        file = file_for(char)
        if file is None:
            uncovered.append(char)
        else:
            drawn[file] += 1

    print(f"{len(counts)} distinct characters across the catalog\n")
    for file in CHAIN:
        print(f"  {file:<32s} {drawn[file]:5d}")
    unused = [file for file in CHAIN if not drawn[file]]
    if unused:
        print(f"\nDrawing nothing, drop from the chain: {', '.join(unused)}")

    if not uncovered:
        print("\nEvery character is covered.")
        return 0
    print(f"\nUNCOVERED ({len(uncovered)}) -- these render as tofu:")
    for char in sorted(uncovered, key=ord):
        name = unicodedata.name(char, "<unnamed>")
        print(f"  U+{ord(char):04X} {name} (x{counts[char]})")
    return 1


async def main() -> int:
    return _report(_demand(await _catalog_strings()))


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
