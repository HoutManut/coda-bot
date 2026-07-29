"""Painting a board: the column header, then one plate per guess."""

from __future__ import annotations

from PIL import Image

from coda.chardle.columns import LABELS, Clue
from coda.chardle.feedback import Cell
from coda.chardle.imaging import assets, layout, text
from coda.chardle.imaging.values import bpm_lines, cell_text
from coda.chardle.views import Board, BoardRow
from coda.db.enums import DifficultyClass

LABEL_FILL = (255, 255, 255)
VALUE_FILL = (72, 72, 72)
VALUE_FILL_SUBTLE = (170, 170, 170)
BPM_BASE_SIZE = 18
BPM_LINE_GAP = 6

FRAME_OFFSET = 14
JACKET_OFFSET = 26
STAND_DROP = 24


def board_image(board: Board) -> Image.Image:
    """The whole board, header plus every guess, on a transparent canvas."""
    grid = layout.build(board)
    canvas = Image.new(
        "RGBA", (grid.width, layout.height(len(board.rows))), (0, 0, 0, 0)
    )
    canvas.alpha_composite(_header(grid))
    for index, row in enumerate(board.rows):
        canvas.alpha_composite(_row(row, grid), (0, layout.row_top(index)))
    return canvas


def _header(grid: layout.Grid) -> Image.Image:
    plate = assets.header(grid.width)
    stand = assets.stand()
    for index, clue in enumerate(grid.columns):
        left, right = grid.bounds(index)
        block = text.fit(LABELS[clue], right - left - 2 * layout.PADDING)
        text.draw(plate, block, (left, 0, right, layout.HEADER_HEIGHT), LABEL_FILL)
        plate.alpha_composite(
            stand,
            (
                (left + right - stand.width) // 2,
                (layout.HEADER_HEIGHT - stand.height) // 2 + STAND_DROP,
            ),
        )
    return plate


def _row(row: BoardRow, grid: layout.Grid) -> Image.Image:
    facts = row.facts
    beyond = facts.visible_class is DifficultyClass.BYD
    plate = assets.stretch(assets.plate(facts.side, beyond=beyond), grid.width)
    _paste_jacket(plate, row)
    for index, (clue, cell) in enumerate(zip(grid.columns, row.cells, strict=True)):
        _paste_cell(plate, grid.bounds(index), clue, cell, row)
    return plate


def _paste_jacket(plate: Image.Image, row: BoardRow) -> None:
    facts = row.facts
    plate.alpha_composite(assets.frame(facts.side), (FRAME_OFFSET, FRAME_OFFSET))
    art = assets.jacket(facts.song_id, facts.jacket_stem)
    plate.alpha_composite(art, (JACKET_OFFSET, JACKET_OFFSET))


def _paste_cell(
    plate: Image.Image,
    bounds: tuple[int, int],
    clue: Clue,
    cell: Cell,
    row: BoardRow,
) -> None:
    left, right = bounds
    wash = assets.wash(cell, right - left - 2 * layout.WASH_INSET)
    if wash is not None:
        plate.alpha_composite(wash, (left + layout.WASH_INSET, layout.WASH_TOP))
    if clue is Clue.SIDE:
        _paste_pill(plate, bounds, row)
    if clue is Clue.BPM:
        _paste_bpm(plate, bounds, row)
        return
    block = text.fit(cell_text(clue, row.facts), right - left - 2 * layout.PADDING)
    text.draw(plate, block, (left, 0, right, layout.ROW_HEIGHT), VALUE_FILL)


def _paste_bpm(plate: Image.Image, bounds: tuple[int, int], row: BoardRow) -> None:
    """The freeform BPM string a player reads, with the hidden numeric base the
    clue actually grades shown small underneath -- the two can read very
    differently (``"180?"`` next to ``179.98``)."""
    left, right = bounds
    width = right - left - 2 * layout.PADDING
    display, base = bpm_lines(row.facts)
    primary = text.fit(display, width)
    if not base:
        text.draw(plate, primary, (left, 0, right, layout.ROW_HEIGHT), VALUE_FILL)
        return
    secondary = text.fit_at(base, width, BPM_BASE_SIZE)
    top = (layout.ROW_HEIGHT - (primary.height + BPM_LINE_GAP + secondary.height)) // 2
    text.draw(plate, primary, (left, top, right, top + primary.height), VALUE_FILL)
    secondary_top = top + primary.height + BPM_LINE_GAP
    text.draw(
        plate,
        secondary,
        (left, secondary_top, right, secondary_top + secondary.height),
        VALUE_FILL_SUBTLE,
    )


def _paste_pill(plate: Image.Image, bounds: tuple[int, int], row: BoardRow) -> None:
    """The side's own colour, drawn under its name whether or not it matched."""
    left, right = bounds
    pill = assets.pill(row.facts.side)
    plate.alpha_composite(
        pill,
        ((left + right - pill.width) // 2, (layout.ROW_HEIGHT - pill.height) // 2),
    )
