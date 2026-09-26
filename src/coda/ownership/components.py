"""The ``/owned`` custom-id contract, in one place so build and parse never drift.

Format: ``own:{discord_id}:{action}[:{index}]``. The owner is in the id because
these components live on an ephemeral message that can still be interacted with
by whoever the interaction claims to be -- the listener refuses a mismatch.
"""

from __future__ import annotations

from dataclasses import dataclass

import hikari
from hikari.impl import MessageActionRowBuilder

from coda.ownership.picker import Option

PREFIX = "own"

PACK_MENU = "p"
BEYOND_MENU = "b"
SELECT_ALL = "all"
CLEAR = "clr"
CLEAR_CONFIRM = "clry"
BEYOND_PAGE = "byd"
PACK_PAGE = "pack"
BEYOND_ALL = "ball"
BEYOND_NONE = "bnone"
DONE = "done"


@dataclass(frozen=True)
class Click:
    """A parsed interaction on one of our components."""

    action: str
    discord_id: int
    index: int


def parse(custom_id: str) -> Click | None:
    """The click this id encodes, or ``None`` when it is not ours."""
    parts = custom_id.split(":")
    if len(parts) < 3 or parts[0] != PREFIX:
        return None
    try:
        discord_id = int(parts[1])
        index = int(parts[3]) if len(parts) > 3 else 0
    except ValueError:
        return None
    return Click(action=parts[2], discord_id=discord_id, index=index)


def _id(discord_id: int, action: str, index: int | None = None) -> str:
    tail = "" if index is None else f":{index}"
    return f"{PREFIX}:{discord_id}:{action}{tail}"


def menu_row(
    discord_id: int, action: str, index: int, chunk: list[Option], placeholder: str
) -> MessageActionRowBuilder:
    """One multi-select over a chunk, current state shown as its defaults.

    ``min_values=0`` is what makes clearing the last tick in a menu a real
    answer rather than an impossible one.
    """
    row = MessageActionRowBuilder()
    menu = row.add_text_menu(
        _id(discord_id, action, index),
        placeholder=placeholder[:150],
        min_values=0,
        max_values=len(chunk),
    )
    for option in chunk:
        note = option.description
        menu.add_option(
            option.label[:100],
            option.value,
            description=note[:100] if note else hikari.UNDEFINED,
            is_default=option.checked,
        )
    return row


def pack_buttons(
    discord_id: int, *, beyonds: tuple[int, int] | None, confirming_clear: bool
) -> MessageActionRowBuilder:
    """Bulk actions for the pack page, plus the way through to Beyonds."""
    row = MessageActionRowBuilder()
    row.add_interactive_button(
        hikari.ButtonStyle.SECONDARY, _id(discord_id, SELECT_ALL), label="Select all"
    )
    row.add_interactive_button(
        hikari.ButtonStyle.DANGER if confirming_clear else hikari.ButtonStyle.SECONDARY,
        _id(discord_id, CLEAR_CONFIRM if confirming_clear else CLEAR),
        label="Clear all — sure?" if confirming_clear else "Clear all",
    )
    if beyonds is not None:
        owned, total = beyonds
        row.add_interactive_button(
            hikari.ButtonStyle.PRIMARY,
            _id(discord_id, BEYOND_PAGE),
            label=f"Beyonds ({owned}/{total})",
        )
    row.add_interactive_button(
        hikari.ButtonStyle.SUCCESS, _id(discord_id, DONE), label="Done"
    )
    return row


def beyond_buttons(discord_id: int) -> MessageActionRowBuilder:
    """Bulk actions for the Beyond page, plus the way back."""
    row = MessageActionRowBuilder()
    row.add_interactive_button(
        hikari.ButtonStyle.SECONDARY, _id(discord_id, PACK_PAGE), label="← Packs"
    )
    row.add_interactive_button(
        hikari.ButtonStyle.SECONDARY, _id(discord_id, BEYOND_ALL), label="All"
    )
    row.add_interactive_button(
        hikari.ButtonStyle.SECONDARY, _id(discord_id, BEYOND_NONE), label="None"
    )
    row.add_interactive_button(
        hikari.ButtonStyle.SUCCESS, _id(discord_id, DONE), label="Done"
    )
    return row
