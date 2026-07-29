"""Board geometry: how wide each column is, and where everything sits.

Column widths are measured from the content once per board and shared by the
header and every row. The prototype computed the two grids separately against
different-width plates, so a header label could drift off the cell it named.
"""

from __future__ import annotations

from dataclasses import dataclass

from coda.chardle.columns import LABELS, Clue
from coda.chardle.facts import ChartFacts
from coda.chardle.imaging import text
from coda.chardle.imaging.values import bpm_lines, cell_text
from coda.chardle.views import Board

JACKET_CELL = 220
HEADER_HEIGHT = 113
ROW_HEIGHT = 220
ROW_GAP = 16

MIN_COLUMN = 165
MAX_COLUMN = 280
PADDING = 20

# The band a wash covers inside a row, and how far short of the cell edge it stops.
WASH_TOP = 43
WASH_HEIGHT = 134
WASH_INSET = 14


@dataclass(frozen=True)
class Grid:
    """Per-column widths, in render order, excluding the jacket cell."""

    columns: list[Clue]
    widths: list[int]

    @property
    def width(self) -> int:
        return JACKET_CELL + sum(self.widths)

    def bounds(self, index: int) -> tuple[int, int]:
        """Left and right edge of one clue column."""
        left = JACKET_CELL + sum(self.widths[:index])
        return left, left + self.widths[index]


def build(board: Board) -> Grid:
    return Grid(board.columns, [_column_width(board, clue) for clue in board.columns])


def height(rows: int) -> int:
    """Total canvas height. Every row is preceded by a gap."""
    if not rows:
        return HEADER_HEIGHT
    return HEADER_HEIGHT + rows * (ROW_HEIGHT + ROW_GAP)


def row_top(index: int) -> int:
    return HEADER_HEIGHT + ROW_GAP + index * (ROW_HEIGHT + ROW_GAP)


def _column_width(board: Board, clue: Clue) -> int:
    """Wide enough for the header label and every value already on the board.

    Measured at the largest font size only. A value that has to shrink to fit
    should shrink, rather than widen the column for every other row.
    """
    widest = text.measure(LABELS[clue], text.SIZES[0])
    for row in board.rows:
        widest = max(widest, _widest_value(clue, row.facts))
    return int(min(max(widest + 2 * PADDING, MIN_COLUMN), MAX_COLUMN))


def _widest_value(clue: Clue, facts: ChartFacts) -> float:
    """The BPM cell draws two lines (display string, hidden base) -- the column
    must fit whichever of the two is wider, not just the primary one."""
    if clue is Clue.BPM:
        return max(text.measure(line, text.SIZES[0]) for line in bpm_lines(facts))
    return text.measure(cell_text(clue, facts), text.SIZES[0])
