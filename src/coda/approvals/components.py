"""The decision-button contract, in one place so build and parse never drift.

Custom id format: ``req:{request_id}:{yes|no}``. The persistent listener in
``extensions/approvals.py`` filters strictly on this prefix -- lightbulb's own
``Menu`` buttons share the same interaction stream, so a loose filter would
double-handle every button in the bot.
"""

from __future__ import annotations

import hikari
from hikari.impl import MessageActionRowBuilder

CUSTOM_ID_PREFIX = "req"


def decision_row(request_id: int) -> MessageActionRowBuilder:
    """Approve/Deny buttons whose ids carry the request they resolve."""
    row = MessageActionRowBuilder()
    row.add_interactive_button(
        hikari.ButtonStyle.SUCCESS,
        f"{CUSTOM_ID_PREFIX}:{request_id}:yes",
        label="Approve",
    )
    row.add_interactive_button(
        hikari.ButtonStyle.DANGER,
        f"{CUSTOM_ID_PREFIX}:{request_id}:no",
        label="Deny",
    )
    return row


def parse_custom_id(custom_id: str) -> tuple[int, bool] | None:
    """``(request_id, approved)`` for one of our buttons, else ``None``."""
    parts = custom_id.split(":")
    if len(parts) != 3 or parts[0] != CUSTOM_ID_PREFIX or parts[2] not in ("yes", "no"):
        return None
    try:
        request_id = int(parts[1])
    except ValueError:
        return None
    return request_id, parts[2] == "yes"
