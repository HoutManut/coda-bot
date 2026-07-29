"""Difficulty/side tints for the admin, derived from :mod:`coda.catalog.colors`.

``colors.py`` is the source of truth for **hue only**. Its values are tuned for
Discord embed strips on dark chrome, so dropping them onto the admin's light page
is inconsistent -- ``COLORLESS`` vanishes into the background while ``BYD``
dominates a row it only means to label. Instead each colour is converted to OKLCH
once, the hue angle kept and lightness/chroma discarded; CSS composes every role
from that angle at fixed L/C, so all tints carry equal visual weight and a
scanning eye reads position and label rather than "the red one is louder".

Near-neutral sources have no meaningful hue (``COLORLESS`` and ``LEPHON`` measure
chroma 0.012), so :func:`hue_of` returns ``None`` and the caller emits the
``neutral`` class instead of a hue variable.
"""

from __future__ import annotations

from math import atan2, degrees, sqrt

from coda.catalog.colors import CLASS_COLORS, SIDE_COLORS
from coda.db.enums import DifficultyClass, Side

# Below this OKLCH chroma a colour carries no usable hue: forcing the role chroma
# onto its angle would invent a colour (the Colorless side would render mustard).
_NEUTRAL_C = 0.02


def _linearize(channel: int) -> float:
    c = channel / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _oklab(color: int) -> tuple[float, float]:
    """Packed RGB int -> the OKLab ``(a, b)`` chromatic pair."""
    red = _linearize((color >> 16) & 0xFF)
    green = _linearize((color >> 8) & 0xFF)
    blue = _linearize(color & 0xFF)

    long_ = 0.4122214708 * red + 0.5363325363 * green + 0.0514459929 * blue
    medium = 0.2119034982 * red + 0.6806995451 * green + 0.1073969566 * blue
    short = 0.0883024619 * red + 0.2817188376 * green + 0.6299787005 * blue

    long_, medium, short = (v ** (1 / 3) for v in (long_, medium, short))
    return (
        1.9779984951 * long_ - 2.4285922050 * medium + 0.4505937099 * short,
        0.0259040371 * long_ + 0.7827717662 * medium - 0.8086757660 * short,
    )


def hue_of(color: int) -> float | None:
    """OKLCH hue angle in degrees for a packed RGB int.

    ``None`` when the source is effectively neutral (chroma below
    :data:`_NEUTRAL_C`) -- there is no hue to derive roles from.
    """
    a, b = _oklab(color)
    if sqrt(a * a + b * b) < _NEUTRAL_C:
        return None
    return degrees(atan2(b, a)) % 360


def _dashed_classes() -> frozenset[DifficultyClass]:
    """Classes that share a hue with an earlier one in display order.

    ``colors.py`` deliberately maps ``BYD_2`` onto ``BYD`` and ``ERR`` onto
    ``FTR``; it is not amended, because Discord and the admin must not disagree.
    The duplicate is instead marked on a non-colour channel (a dashed border,
    which also survives colourblindness). Only the *later* class of a colliding
    pair is dashed, so the original keeps the plain treatment.
    """
    from coda.admin.presenters import DIFFICULTY_ORDER

    seen: set[int] = set()
    dashed: set[DifficultyClass] = set()
    for cls in DIFFICULTY_ORDER:
        color = CLASS_COLORS[cls]
        if color in seen:
            dashed.add(cls)
        seen.add(color)
    return frozenset(dashed)


DASHED_CLASSES = _dashed_classes()

# Short chip labels. Deliberately not `presenters.difficulty_label`, which maps
# BYD_2 to plain "Beyond" -- a chip must distinguish what the full name merges.
CHIP_LABELS: dict[DifficultyClass, str] = {
    DifficultyClass.PST: "PST",
    DifficultyClass.PRS: "PRS",
    DifficultyClass.FTR: "FTR",
    DifficultyClass.ETR: "ETR",
    DifficultyClass.BYD: "BYD",
    DifficultyClass.BYD_2: "BYD²",
    DifficultyClass.ERR: "ERR",
}


# Templates compose these into their own ``class``/``style`` attributes, so the
# two halves are returned separately rather than as one attribute blob.

def _classes(hue: float | None, dashed: bool = False) -> str:
    names = ["tinted"]
    if dashed:
        names.append("dashed")
    if hue is None:
        names.append("neutral")
    return " ".join(names)


def _style(hue: float | None) -> str:
    return "" if hue is None else f"--h:{hue:.1f}"


def difficulty_tint_class(diff: DifficultyClass) -> str:
    """Tint classes for a difficulty chip or chart accordion."""
    return _classes(hue_of(CLASS_COLORS[diff]), diff in DASHED_CLASSES)


def difficulty_tint_style(diff: DifficultyClass) -> str:
    """Hue custom property for a difficulty chip or chart accordion."""
    return _style(hue_of(CLASS_COLORS[diff]))


def side_tint_class(side: int) -> str:
    """Tint classes for a song row's side edge."""
    return _classes(hue_of(SIDE_COLORS[Side.from_id(side)]))


def side_tint_style(side: int) -> str:
    """Hue custom property for a song row's side edge."""
    return _style(hue_of(SIDE_COLORS[Side.from_id(side)]))


def chip_label(diff: DifficultyClass) -> str:
    """Short uppercase label for a difficulty chip."""
    return CHIP_LABELS[diff]
