"""Edge translation between stored values and what the editor shows/accepts.

The DB stores compact, lossy-looking encodings (level ``×2``, rating ``×10``,
sentinels ``0``/``-1``, numeric side ids, unix-ms dates). The forms speak human
("9+", "11.3", "TBA", "?", "Conflict", a date). Everything that converts between
the two lives here so routers and templates never re-derive an encoding.

The form-parsing direction is the careful one: :func:`encode_level` /
:func:`encode_rating` raise on the sentinel words, so we map ``"TBA"``/``"?"`` to
their sentinel ints *before* calling them.
"""

from __future__ import annotations

import colorsys
import random
import hashlib

from coda.db.enums import DifficultyClass, Side
from coda.utils.encoding import (
    decode_level,
    decode_rating,
    encode_level,
    encode_rating,
)

# Sentinel ints shared by level and rating.
_TBA = 0
_NA = -1


# --- level ----------------------------------------------------------------

def display_level(value: int) -> str:
    """Stored level int -> editable string ("9", "10+", "0" (TBA), "?").

    ``decode_level`` renders both sentinels as ``"?"``, which would silently
    rewrite a TBA level to unknown on save; the two are split here so the form
    round-trips through :func:`parse_level` exactly.
    """
    if value == _TBA:
        return "0"
    if value == _NA:
        return "?"
    return decode_level(value)


def parse_level(text: str) -> int:
    """Display level string -> stored int. Blank/"TBA"/"0" -> 0, "?" -> -1."""
    text = text.strip()
    if text == "" or text.upper() == "TBA" or text == "0":
        return _TBA
    if text == "?":
        return _NA
    return encode_level(text)


# --- rating (chart constant) ----------------------------------------------

def display_rating(value: int) -> str:
    """Stored rating int -> editable string ("11.3", "-8.8", "TBA", "?").

    A delisted chart stores its historical CC negated (``rating < -1``), and the
    sign is kept rather than hidden so the value round-trips through
    :func:`parse_rating` unchanged. ``decode_rating`` is deliberately not used:
    it passes non-positive values through undivided, which would render ``-88``
    as ``-88.0`` and re-encode it as ``-880``.
    """
    if value == _TBA:
        return "0"
    if value == _NA:
        return "?"
    return f"{value / 10:.1f}"


def parse_rating(text: str) -> int:
    """Display rating string -> stored int. Blank/"0"/"TBA" -> 0, "?" -> -1."""
    text = text.strip()
    if text == "" or text == "0" or text.upper() == "TBA":
        return _TBA
    if text == "?":
        return _NA
    return encode_rating(float(text))


# --- list rendering -------------------------------------------------------
#
# The list collapses every non-positive level/CC to one "?" — a table is for
# scanning, and three different unknowns are noise there. The detail form keeps
# the exact value so a save round-trips (see :func:`display_rating`).

def list_level(value: int) -> str:
    """Stored level -> list cell. Any non-positive value renders "?"."""
    return "?" if value <= 0 else decode_level(value)


def list_rating(value: int) -> str:
    """Stored rating -> list cell. Any non-positive value renders "?"."""
    return "?" if value <= 0 else f"{decode_rating(value):.1f}"


def is_sentinel(value: int) -> bool:
    """Whether a level/rating renders as "?" rather than a real value."""
    return value <= 0


# --- side -----------------------------------------------------------------

def side_label(value: int) -> str:
    """Numeric side id (0-3) -> display label ("Light", "Conflict", ...)."""
    return Side.from_id(value).name.replace("_", " ").title()


def side_choices() -> list[tuple[int, str]]:
    """(id, label) pairs for a side dropdown, in id order."""
    return [(i, Side.from_id(i).name.replace("_", " ").title()) for i in range(len(Side))]


# --- difficulty -----------------------------------------------------------

# Display order for difficulty tabs/labels.
DIFFICULTY_ORDER: tuple[DifficultyClass, ...] = (
    DifficultyClass.PST,
    DifficultyClass.PRS,
    DifficultyClass.FTR,
    DifficultyClass.ETR, # Displays before BYD
    DifficultyClass.BYD,
    DifficultyClass.BYD_2,
    DifficultyClass.ERR,
)

_DIFFICULTY_LABELS: dict[DifficultyClass, str] = {
    DifficultyClass.PST: "Past",
    DifficultyClass.PRS: "Present",
    DifficultyClass.FTR: "Future",
    DifficultyClass.BYD: "Beyond",
    DifficultyClass.ETR: "Eternal",
    DifficultyClass.BYD_2: "Beyond",
    DifficultyClass.ERR: "Error",
}

# lowiro's alt appearance for some Beyond charts (SongDifficulty.alt) -- not a
# class of its own, see coda.catalog.labels.
_ALT_DIFFICULTY_LABELS: dict[DifficultyClass, str] = {
    DifficultyClass.BYD: "Inscribed",
    DifficultyClass.BYD_2: "Inscribed",
}

# Classes the "alt" checkbox is offered for.
ALT_ELIGIBLE: frozenset[DifficultyClass] = frozenset(_ALT_DIFFICULTY_LABELS)


def difficulty_label(diff: DifficultyClass, alt: bool = False) -> str:
    if alt and diff in _ALT_DIFFICULTY_LABELS:
        return _ALT_DIFFICULTY_LABELS[diff]
    return _DIFFICULTY_LABELS[diff]


# --- duration -------------------------------------------------------------
#
# Stored as whole seconds. The form accepts either raw seconds ("215") or
# ``m:ss`` ("3:35"); display always uses ``m:ss`` so the value is readable.

def display_time(seconds: int | None) -> str:
    """Seconds -> ``m:ss`` (empty for None)."""
    if seconds is None:
        return ""
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


def parse_time(text: str) -> int:
    """``m:ss`` or raw seconds -> total seconds. Blank -> 0."""
    text = text.strip()
    if not text:
        return 0
    if ":" in text:
        minutes, _, secs = text.partition(":")
        return int(minutes or 0) * 60 + int(secs or 0)
    return int(text)


# --- tag category colors --------------------------------------------------
#
# Each tag category carries a base color. Chips are rendered as a *tint* of
# that base (so a wall of tags stays calm), with the text color derived from
# the tint's measured luminance — never guessed — so it always reads.

_DEFAULT_CATEGORY_COLOR = "#a28fef"  # used only if a row's color is missing



# Generate a random salt string once when the module loads/app starts

def seed_category_color(slug: str) -> str:
    """Generates a random but stable session-based pastel color for a category.
    
    By mixing a random session salt with the slug, the colors change on every 
    app restart, but remain stable across different page views in the same session.
    """
    salt = str(random.randint(0, 1000000))
    # Mix the slug with the random session salt
    salted_slug = f"{slug}-{salt}"
    
    # Generate the hue from the salted string
    hue_hash = int(hashlib.md5(salted_slug.encode()).hexdigest(), 16)
    hue = (hue_hash % 360) / 360.0
    
    # Pastel Tuning: High Lightness (0.85), Soft Saturation (0.65)
    r, g, b = colorsys.hls_to_rgb(hue, 0.85, 0.65)
    
    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _mix(color: tuple[int, int, int], frac: float) -> tuple[int, int, int]:
    """Mix ``frac`` of ``color`` with ``1-frac`` white (frac 0 -> white)."""
    return tuple(round(c * frac + 255 * (1 - frac)) for c in color)  # type: ignore[return-value]


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    def chan(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4
    r, g, b = (chan(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _darken(color: tuple[int, int, int], frac: float) -> tuple[int, int, int]:
    """Scale ``color`` toward black (frac 0 -> black, 1 -> unchanged)."""
    return tuple(round(c * frac) for c in color)  # type: ignore[return-value]


def tag_chip_style(color: str | None) -> str:
    """``style`` attribute body for a tag chip tinted by its category color.

    Emits four custom properties — ``--cbg`` (light tint background),
    ``--cbd`` (stronger tint border), ``--cfg`` (text color picked from the
    *background's* luminance, so contrast holds for any hue) and ``--cink`` (a
    darkened shade of the base hue, used for tinted pill text on the vocab page).
    """
    try:
        base = _hex_to_rgb(color or _DEFAULT_CATEGORY_COLOR)
    except (ValueError, IndexError):
        base = _hex_to_rgb(_DEFAULT_CATEGORY_COLOR)
    bg = _mix(base, 0.16)
    border = _mix(base, 0.45)
    fg = "#15140f" if _relative_luminance(bg) > 0.45 else "#ffffff"
    ink = _darken(base, 0.42)
    hexf = "#{:02x}{:02x}{:02x}".format
    return f"--cbg:{hexf(*bg)};--cbd:{hexf(*border)};--cfg:{fg};--cink:{hexf(*ink)}"
