"""What each clue column prints for one chart."""

from __future__ import annotations

from coda.catalog.labels import format_cc
from coda.chardle.columns import Clue
from coda.chardle.facts import ChartFacts
from coda.db.enums import Side
from coda.utils.encoding import decode_level

UNKNOWN_CC = "?.?"
UNKNOWN = "—"
MAX_CHARTER_NAMES = 3


def cell_text(clue: Clue, facts: ChartFacts) -> str:
    """The string one cell shows. Never the empty string -- a blank cell reads
    as a rendering fault rather than as missing data."""
    match clue:
        case Clue.TITLE:
            return facts.name
        case Clue.ARTIST:
            return facts.artist_text or UNKNOWN
        case Clue.CHARTER:
            return facts.charter_text or UNKNOWN
        case Clue.LEVEL:
            return decode_level(facts.level)
        case Clue.RATING:
            return format_cc(facts.rating) or UNKNOWN_CC
        case Clue.PACK:
            return facts.pack_name or UNKNOWN
        case Clue.VERSION:
            return facts.version or UNKNOWN
        case Clue.SIDE:
            return Side.from_id(facts.side).value.title()
        case Clue.BPM:
            return bpm_lines(facts)[0]
        case Clue.NOTE:
            return str(facts.note) if facts.note > 0 else UNKNOWN


def charter_lines(facts: ChartFacts) -> tuple[str, str]:
    """The charter cell's two lines: the display name/group a player reads,
    and the real linked charters underneath -- can be one alias hiding many
    people, so the subtext caps at a few names plus a ``+n`` overflow."""
    primary = facts.charter_text or UNKNOWN
    names = sorted(facts.charters)
    if not names or names == [facts.charter_text]:
        return primary, ""
    if len(names) <= MAX_CHARTER_NAMES:
        return primary, ", ".join(names)
    shown = names[: MAX_CHARTER_NAMES - 1]
    return primary, ", ".join(shown) + f", +{len(names) - len(shown)}"


def bpm_lines(facts: ChartFacts) -> tuple[str, str]:
    """The BPM cell's two lines: the freeform display string a player reads,
    and the hidden numeric base the arrow/yellow-red math actually compares --
    shown small underneath since it's the thing the clue is grading."""
    if facts.bpm <= 0:
        return UNKNOWN, ""
    base = f"{facts.bpm:g}"
    return facts.bpm_display, "" if facts.bpm_display == base else base
