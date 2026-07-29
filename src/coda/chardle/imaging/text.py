"""Fitting a string into a fixed-width cell, and drawing it there.

Everything is measured in pixels off the real fonts. The prototype wrapped at a
character count, which put a 12-character CJK title and a 12-character Latin one
in boxes three times apart in width, and had no answer at all for a token wider
than its column.
"""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw

from coda.chardle.imaging.fonts import Run, split_runs

SIZES: tuple[int, ...] = (24, 22, 20, 18)
MAX_LINES = 3
LINE_SPACING = 4
ELLIPSIS = "…"

_MEASURE = ImageDraw.Draw(Image.new("L", (1, 1)))


@dataclass(frozen=True)
class Line:
    runs: list[Run]
    width: float


@dataclass(frozen=True)
class Block:
    """A string laid out for one cell: final size, wrapped lines, extent."""

    lines: list[Line]
    size: int

    @property
    def width(self) -> float:
        return max((line.width for line in self.lines), default=0.0)

    @property
    def height(self) -> int:
        return len(self.lines) * self.size + (len(self.lines) - 1) * LINE_SPACING


def measure(text: str, size: int) -> float:
    """Width of one unwrapped line, summed across its font runs.

    A catalog string can carry a literal newline (some official titles do);
    PIL's ``textlength`` throws on multiline text, so it's flattened to a
    space here -- the one place every caller (``fit`` and every wrapping
    helper below) funnels through before measuring.
    """
    text = " ".join(text.split())
    return sum(_MEASURE.textlength(run.text, run.font) for run in split_runs(text, size))


def fit(text: str, width: float) -> Block:
    """Lay ``text`` out to fit ``width``, shrinking then truncating as needed."""
    text = " ".join(text.split())
    for size in SIZES:
        lines = _wrap(text, width, size)
        if len(lines) <= MAX_LINES:
            return _block(lines, size)
    size = SIZES[-1]
    lines = _wrap(text, width, size)[:MAX_LINES]
    lines[-1] = _truncate(lines[-1], width, size)
    return _block(lines, size)


def fit_at(text: str, width: float, size: int) -> Block:
    """Like :func:`fit`, but at a caller-chosen size rather than the largest
    that fits -- for a line that must read as visually subordinate to another
    one in the same cell, not just as small as it needs to be to fit."""
    text = " ".join(text.split())
    lines = _wrap(text, width, size)[:MAX_LINES]
    lines[-1] = _truncate(lines[-1], width, size)
    return _block(lines, size)


def draw(canvas: Image.Image, block: Block, box: tuple[int, int, int, int], fill) -> None:
    """Draw a fitted block centred in ``box`` (left, top, right, bottom)."""
    pen = ImageDraw.Draw(canvas)
    left, top, right, bottom = box
    # Baseline-anchored so a JP run and a Latin run on the same line sit level;
    # the prototype nudged CJK up three pixels to fake this.
    baseline = (top + bottom - block.height) / 2 + block.size
    for line in block.lines:
        x = (left + right - line.width) / 2
        for run in line.runs:
            pen.text((x, baseline), run.text, fill, run.font, anchor="ls")
            x += _MEASURE.textlength(run.text, run.font)
        baseline += block.size + LINE_SPACING


def _block(lines: list[str], size: int) -> Block:
    return Block(
        [Line(split_runs(line, size), measure(line, size)) for line in lines], size
    )


def _wrap(text: str, width: float, size: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in _words(text):
        candidate = f"{current}{word}"
        if current and measure(candidate.strip(), size) > width:
            lines.append(current.strip())
            current = word.lstrip()
        else:
            current = candidate
    if current.strip() or not lines:
        lines.append(current.strip())
    return _split_overlong(lines, width, size)


def _words(text: str) -> list[str]:
    """Break candidates, each carrying its leading space.

    CJK has no spaces, so every ideograph and kana is its own candidate --
    otherwise a Japanese title is one unbreakable token.
    """
    words: list[str] = []
    for char in text:
        if not words or char == " " or _breaks_before(char) or _breaks_before(words[-1][-1]):
            words.append(char)
        else:
            words[-1] += char
    return words


def _breaks_before(char: str) -> bool:
    return "぀" <= char <= "ヿ" or "㐀" <= char <= "鿿"


def _split_overlong(lines: list[str], width: float, size: int) -> list[str]:
    """Hard-break any line still wider than the cell, e.g. ``world.executeMe();``."""
    out: list[str] = []
    for line in lines:
        while measure(line, size) > width and len(line) > 1:
            cut = _longest_prefix(line, width, size)
            out.append(line[:cut])
            line = line[cut:]
        out.append(line)
    return out


def _longest_prefix(text: str, width: float, size: int) -> int:
    cut = 1
    while cut < len(text) and measure(text[: cut + 1], size) <= width:
        cut += 1
    return cut


def _truncate(line: str, width: float, size: int) -> str:
    if measure(line, size) <= width:
        return line
    while line and measure(line + ELLIPSIS, size) > width:
        line = line[:-1]
    return line.rstrip() + ELLIPSIS
