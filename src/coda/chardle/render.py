"""The board and scoreboard embeds, and the share string.

The live board itself is an image (:mod:`coda.chardle.imaging`); this module
writes the embed around it. Emoji squares stay for the two places text is the
point: the share string, which has to survive a copy-paste, and the daily
scoreboard, which shows everyone's grid at once.
"""

from __future__ import annotations

import hikari

from coda.catalog.labels import CLASS_FULL, format_cc
from coda.chardle.columns import LABELS, Clue
from coda.chardle.facts import ChartFacts
from coda.chardle.feedback import Arrow, Cell, Color
from coda.chardle.imaging import render_board
from coda.chardle.views import (
    Board,
    BoardRow,
    DailyScoreboard,
    ScoreboardEntry,
)
from coda.db.enums import ChardleState, DifficultyClass, Side
from coda.utils.encoding import decode_level

_SQUARES: dict[Color, str] = {
    Color.GREEN: "🟩",
    Color.YELLOW: "🟨",
    Color.RED: "🟥",
    Color.UNKNOWN: "⬛",
}

_ARROWS: dict[Arrow, str] = {Arrow.NONE: "", Arrow.UP: "🔼", Arrow.DOWN: "🔽"}

_COLOR_NEUTRAL = 0x5865F2
_COLOR_WON = 0x57F287
_COLOR_LOST = 0xED4245

# Only tiers that state their class up front may colour the strip -- extras is
# absent on purpose, see _color().
_TIER_COLORS: dict[str, int] = {
    "pst": 0x2EA2C0,
    "prs": 0x94B05C,
    "ftr": 0x812C64,
    "byd": 0x8C2D3C,
    "etr": 0x6E4E9E,
}


IMAGE_NAME = "chardle-{revision}.webp"


def board_embed(
    board: Board, *, debug: bool = False, revision: int = 0
) -> tuple[hikari.Embed, hikari.Bytes | None]:
    """The live board, edited in place for as long as the game runs.

    ``revision`` distinguishes one render of a board from the next: Discord
    serves a cached attachment when an edit reuses a filename, which shows up as
    a board that stops updating.

    ``debug`` spells every column out as text and **reveals the answer** — a
    testing view, not a playable one.
    """
    if debug:
        return _debug_embed(board), None
    finished = board.state is not ChardleState.PLAYING
    lines = [_status(board)]
    # if finished:
    #     # Fenced so it copies out of Discord in one tap, which is the whole
    #     # point of a share grid.
    #     lines.extend(["", f"```\n{share_string(board)}\n```"])
    name = IMAGE_NAME.format(revision=revision)
    image = hikari.Bytes(render_board(board, final=finished), name)
    embed = hikari.Embed(
        title=_title(board), description="\n".join(lines), color=_color(board)
    )
    embed.set_image(image)
    return embed, image


_DESCRIPTION_BUDGET = 3800


def _debug_embed(board: Board) -> hikari.Embed:
    header = [
        f"-# DEBUG · tier `{board.tier}` · columns "
        + " ".join(f"`{clue}`" for clue in board.columns),
        f"**ANSWER: {board.answer.name}** · {_chart_label(board.answer)} "
        f"· chart `{board.answer.difficulty_id}`",
        _answer_values(board),
        "",
    ]
    blocks = [_debug_row(index, row, board)
              for index, row in enumerate(board.rows, 1)]
    if not blocks:
        blocks = ["-# No guesses yet."]
    footer = ["", _status(board)]

    # Oldest rows go first when a long unbounded board would blow the 4096-char
    # description limit; the recent ones are what a tester is reading.
    trimmed = False
    while len(blocks) > 1 and _length(header, blocks, footer) > _DESCRIPTION_BUDGET:
        blocks.pop(0)
        trimmed = True
    if trimmed:
        blocks.insert(0, "-# …older guesses trimmed.")
    return hikari.Embed(
        title=_title(board),
        description="\n".join([*header, *blocks, *footer]),
        color=_color(board),
    )


def _length(header: list[str], blocks: list[str], footer: list[str]) -> int:
    return len("\n".join([*header, *blocks, *footer]))


def _answer_values(board: Board) -> str:
    return " · ".join(
        f"{LABELS[clue]} `{_value_text(clue, board.answer)}`" for clue in board.columns
    )


def _debug_row(index: int, row: BoardRow, board: Board) -> str:
    label = f" · *{row.label}*" if row.label else ""
    lines = [f"**{index}. {row.name}**{label}"]
    for clue, cell in zip(board.columns, row.cells, strict=True):
        guessed = _value_text(clue, row.facts)
        wanted = _value_text(clue, board.answer)
        square = _SQUARES[cell.color] + _ARROWS[cell.arrow]
        target = "" if cell.color is Color.GREEN else f" → `{wanted}`"
        lines.append(f"> {square} {LABELS[clue]}: `{guessed}`{target}")
    return "\n".join(lines)


def _value_text(clue: Clue, facts: ChartFacts) -> str:
    """The raw comparable value, decoded for a human. Debug view only."""
    match clue:
        case Clue.TITLE:
            return facts.song_id
        case Clue.ARTIST:
            return ", ".join(sorted(facts.artists)) or "—"
        case Clue.CHARTER:
            return ", ".join(sorted(facts.charters)) or "—"
        case Clue.LEVEL:
            return decode_level(facts.level)
        case Clue.RATING:
            return format_cc(facts.rating) or "?"
        case Clue.PACK:
            return facts.pack_name
        case Clue.VERSION:
            return facts.version
        case Clue.SIDE:
            return Side.from_id(facts.side).value
        case Clue.BPM:
            base = f"{facts.bpm:g}"
            if facts.bpm_display == base:
                return base
            return f"{facts.bpm_display} (base {base})"
        case Clue.NOTE:
            return str(facts.note)


def share_string(board: Board) -> str:
    """Spoiler-safe grid. Arrows leak nothing — the reader cannot see the guess
    an arrow points *from*."""
    header = _share_header(board)
    grid = "\n".join(cells(row.cells) for row in board.rows)
    return f"{header}\n{grid}"


def scoreboard(view: DailyScoreboard) -> tuple[hikari.Embed, hikari.File | None]:
    """The guild's daily standings, edited in place until the puzzle rolls over.

    Returns ``(embed, file)`` like every other renderer here, so replacing this
    text board with a composited one changes nothing outside this module.
    """
    blocks = [
        _scoreboard_block(place, entry, view)
        for place, entry in enumerate(view.entries)
    ]
    if not blocks:
        blocks = ["-# Nobody has played today's Chardle here yet."]
    footer = (
        [f"-# Resets <t:{int(view.resets_at.timestamp())}:R>"]
        if view.resets_at is not None
        else []
    )
    embed = hikari.Embed(
        title=f"Chardle #{view.puzzle_number} · {view.tier_label}",
        description="\n".join([*_fit(blocks, footer), "", *footer]),
        color=_COLOR_NEUTRAL,
    )
    return embed, None


_MEDALS = ("🥇", "🥈", "🥉")
_NO_MEDAL = "　"


def _fit(blocks: list[str], footer: list[str]) -> list[str]:
    """Drop from the bottom until the description fits. A busy guild loses the
    tail of the standings rather than the whole scoreboard."""
    budget = _DESCRIPTION_BUDGET - sum(len(line) + 1 for line in footer)
    kept: list[str] = []
    used = 0
    for block in blocks:
        if used + len(block) + 1 > budget:
            kept.append(f"-# …and {len(blocks) - len(kept)} more")
            break
        kept.append(block)
        used += len(block) + 1
    return kept


def _scoreboard_block(
    place: int, entry: ScoreboardEntry, view: DailyScoreboard
) -> str:
    medal = (
        _MEDALS[place]
        if entry.state is ChardleState.WON and place < len(_MEDALS)
        else _NO_MEDAL
    )
    head = f"{medal} <@{entry.discord_id}> {_entry_score(entry, view)}"
    if entry.grid is None:
        return f"{head} · {entry.taken} so far"
    return "\n".join([head, *entry.grid])


def _entry_score(entry: ScoreboardEntry, view: DailyScoreboard) -> str:
    if entry.state is ChardleState.PLAYING:
        return "**playing**"
    if entry.state is ChardleState.LOST:
        return f"**X/{view.max_attempts}**" if view.max_attempts else "**X**"
    if view.max_attempts:
        return f"**{entry.taken}/{view.max_attempts}**"
    return f"**{entry.taken}**"


def _title(board: Board) -> str:
    if board.puzzle_number is not None:
        return f"Chardle #{board.puzzle_number} · {board.tier_label}"
    return f"Chardle · {board.tier_label}"


def _share_header(board: Board) -> str:
    score = _score(board)
    if board.puzzle_number is not None:
        return f"Chardle #{board.puzzle_number} {score}"
    # No puzzle number means no shared legend to decode the grid against, so the
    # string has to describe itself.
    return f"Chardle · {board.tier_label} · {score}"


def _score(board: Board) -> str:
    played = len(board.rows)
    if board.state is ChardleState.LOST:
        return f"X/{board.max_attempts}" if board.max_attempts else "X"
    if board.max_attempts is not None:
        return f"{played}/{board.max_attempts}"
    return f"{played} guesses"


def _color(board: Board) -> int:
    if board.state is ChardleState.WON:
        return _COLOR_WON
    if board.state is ChardleState.LOST:
        return _COLOR_LOST
    # A tier that hides its class must not leak it back through the embed strip.
    return _TIER_COLORS.get(board.tier, _COLOR_NEUTRAL)


def cells(row_cells: list[Cell]) -> str:
    """One guess as squares and arrows. The scoreboard reuses this so a shared
    grid and a player's own share string can never drift apart."""
    # return "".join(_SQUARES[cell.color] + _ARROWS[cell.arrow] for cell in row_cells)
    
    # only render arrow if presents, render both make rows mis-aligned
    return "".join(_ARROWS[cell.arrow] or _SQUARES[cell.color] for cell in row_cells)


def _status(board: Board) -> str:
    if board.state is ChardleState.WON:
        return f"Solved in **{len(board.rows)}** — {_reveal(board.answer)}"
    if board.state is ChardleState.LOST:
        return f"Out of guesses — it was {_reveal(board.answer)}"

    played = len(board.rows)
    if board.max_attempts is None:
        line = f"**{played}** guess{'' if played == 1 else 'es'} so far."
    else:
        line = f"**{board.max_attempts - played}** of {board.max_attempts} attempts left."
    if board.filters_note:
        line = f"{line}\n-# {board.filters_note}"
    return line


def _reveal(answer: ChartFacts) -> str:
    return f"**{answer.name}** · {_chart_label(answer)}"


def _chart_label(answer: ChartFacts) -> str:
    label = CLASS_FULL[answer.difficulty_class]
    if answer.difficulty_class is DifficultyClass.ERR:
        return label
    cc = format_cc(answer.rating)
    level = decode_level(answer.level)
    return f"{label} {level}" if cc is None else f"{label} {level} ({cc})"
