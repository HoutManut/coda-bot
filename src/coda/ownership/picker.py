"""Turning catalog rows + declared state into the options the picker shows.

Pure presentation: no I/O, so the labelling and chunking rules are testable on
their own. Two option sets come out of here -- packs and Beyonds -- and they are
the same shape, because the write path behind them is the same too.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from coda.catalog.jackets import display_name
from coda.catalog.labels import class_full
from coda.catalog.resolution import effective
from coda.catalog.spoilers import chart_spoilered
from coda.ownership.service import FREE_PACK_IDS, BeyondEntry, PackCount

# Memory Archive is 134 individually-sold songs -- a pack tick would be a lie in
# both directions. ``/owned song`` covers them one at a time.
SINGLES_PACK_ID = "single"

# Off the picker for opposite reasons: nobody needs to be asked about the two
# above, and nobody can answer ``single`` with one tick.
EXCLUDED_PACK_IDS = FREE_PACK_IDS | {SINGLES_PACK_ID}

# Discord's hard cap on options in one select menu. 61 pickable packs is three
# menus today; the layout has room for four before it needs paging.
CHUNK = 25

_APPEND = re.compile(r"_append_(\d+)$")


# Beyond this many characters the locked-pack line stops naming and starts
# counting. It is prose in a message body, not a list anyone reads to the end.
LOCKED_NOTE_BUDGET = 300


@dataclass(frozen=True)
class Option:
    """One tickable row: a pack, or a Beyond chart.

    ``locked`` means the answer is already settled by evidence and cannot be
    argued with -- it never reaches a menu, because a control that refuses to
    change is worse than no control.
    """

    value: str
    label: str
    checked: bool
    description: str | None = None
    locked: bool = False


def pack_options(
    counts: list[PackCount], inferred: frozenset[str] | set[str] = frozenset()
) -> list[Option]:
    """One option per pack, ticked when wholly declared and locked when proven.

    ``inferred`` is the set a player's own scores settle -- those come back
    ``locked`` and belong outside the menus entirely.
    """
    totals: dict[str, int] = defaultdict(int)
    owned: dict[str, int] = defaultdict(int)
    names: dict[str, list[PackCount]] = defaultdict(list)
    for count in counts:
        if count.pack_id in EXCLUDED_PACK_IDS:
            continue
        totals[count.pack_id] += count.total
        owned[count.pack_id] += count.owned
        names[count.pack_id].append(count)

    labels = _pack_labels(
        {
            pack_id: max(rows, key=lambda row: row.total).pack_name
            for pack_id, rows in names.items()
        }
    )
    options = [
        Option(
            value=pack_id,
            label=labels[pack_id],
            checked=owned[pack_id] == totals[pack_id],
            description=_partial_note(owned[pack_id], totals[pack_id]),
            locked=pack_id in inferred,
        )
        for pack_id in totals
    ]
    return sorted(options, key=lambda option: option.label.casefold())


def pickable(options: list[Option]) -> list[Option]:
    """The options a menu may carry -- everything not already settled."""
    return [option for option in options if not option.locked]


def held_count(options: list[Option]) -> int:
    """Packs the player has, whether they ticked them or their scores proved it."""
    return sum(1 for option in options if option.checked or option.locked)


def locked_note(options: list[Option]) -> str | None:
    """The line naming the packs a player's own scores already settled.

    Named rather than merely counted: "3 packs are yours" invites the question
    of which, and the answer is not reachable anywhere else in the view.
    """
    names = [option.label for option in options if option.locked]
    if not names:
        return None
    shown: list[str] = []
    used = 0
    for name in names:
        if shown and used + len(name) > LOCKED_NOTE_BUDGET:
            break
        shown.append(name)
        used += len(name) + 3
    listed = " · ".join(shown)
    if len(shown) < len(names):
        listed += f" +{len(names) - len(shown)} more"
    return f"-# Already yours, from your scores: {listed}"


def _pack_labels(names: dict[str, str]) -> dict[str, str]:
    """Pack display names, disambiguated where an ``_append_N`` split shares one.

    14 names are shared by 33 packs, and the catalog has nothing else to tell
    them apart -- so the suffix is read off the id, which is lowiro's own
    numbering, rather than invented here.
    """
    shared = {name for name, count in Counter(names.values()).items() if count > 1}
    labels: dict[str, str] = {}
    for pack_id, name in names.items():
        append = _APPEND.search(pack_id)
        if name in shared and append is not None:
            labels[pack_id] = f"{name} (Append {append.group(1)})"
        else:
            labels[pack_id] = name
    return labels


def _partial_note(owned: int, total: int) -> str | None:
    """Shown only when a pack is part-declared -- which the picker itself cannot
    produce, so it means the catalog gained charts since the tick."""
    if 0 < owned < total:
        return f"{owned} of {total} charts"
    return None


def beyond_options(entries: list[BeyondEntry], locale: object) -> list[Option]:
    """One option per Beyond the player holds, ticked when it is already theirs.

    A Beyond they have PLAYED comes back locked, for the same reason an inferred
    pack does: the play makes it playable whatever the menu says, so offering it
    as a checkbox offers a choice that cannot be honoured.

    Every displayed value is the chart's EFFECTIVE one: a Beyond routinely
    renames its song (both of Last's do) and 53 of them override ``version``,
    so reading the song row directly would show the wrong name and leak a
    spoilered chart.
    """
    options = [
        Option(
            value=str(entry.chart.id),
            label=display_name(
                effective(entry.song, entry.chart, "name_en"),
                effective(entry.song, entry.chart, "name_jp"),
                locale,
            ),
            checked=entry.owned,
            description=class_full(entry.chart.difficulty, entry.chart.alt),
            locked=entry.proven,
        )
        for entry in entries
        if not chart_spoilered(entry.song, entry.chart)
    ]
    return sorted(options, key=lambda option: option.label.casefold())


def chunked(options: list[Option]) -> list[list[Option]]:
    """Options split into menu-sized runs."""
    return [options[start : start + CHUNK] for start in range(0, len(options), CHUNK)]


def range_label(chunk: list[Option]) -> str:
    """A menu's placeholder: the span it covers, and how much of it is ticked."""
    picked = sum(1 for option in chunk if option.checked)
    span = f"{_short(chunk[0].label)} – {_short(chunk[-1].label)}"
    return f"{span}  ({picked} / {len(chunk)})"


def _short(label: str, limit: int = 28) -> str:
    return label if len(label) <= limit else f"{label[: limit - 1]}…"
