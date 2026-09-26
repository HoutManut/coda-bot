"""The embed -> Components V2 converter, which is what makes a spoiler blur.

Worth pinning because the failure is silent in two directions: a dropped jacket
still sends (just without art), and a builder handed a single component instead
of a sequence raises only on the code path that actually has an image.
"""

from __future__ import annotations

from datetime import UTC, datetime

import hikari
from hikari.impl import MessageActionRowBuilder

from coda.utils.container import as_container

TEXT_DISPLAY = 10
THUMBNAIL = 11
MEDIA_GALLERY = 12
ACTION_ROW = 1
SECTION = 9
CONTAINER = 17


def _row(custom_id: str = "song:c:1") -> MessageActionRowBuilder:
    row = MessageActionRowBuilder()
    row.add_interactive_button(hikari.ButtonStyle.SECONDARY, custom_id, label="FTR")
    return row


def _build(embed, rows=(), *, spoiler=True):
    return as_container(embed, list(rows), spoiler=spoiler).build()


def test_spoiler_flag_and_accent_come_from_the_embed():
    payload, _ = _build(hikari.Embed(title="t", color=0x8B2FBE))
    assert payload["type"] == CONTAINER
    assert payload["spoiler"] is True
    assert payload["accent_color"] == 0x8B2FBE


def test_not_spoilered_round_trips_a_plain_embed():
    payload, attachments = _build(
        hikari.Embed(title="No results", description="Nothing matched."), spoiler=False
    )
    assert payload["spoiler"] is False
    assert attachments == []
    assert [c["content"] for c in payload["components"]] == [
        "## No results",
        "Nothing matched.",
    ]


def test_thumbnail_becomes_a_section_accessory_and_is_attached():
    embed = hikari.Embed(title="Testify", description="9,912,345")
    embed.set_thumbnail(hikari.File("pyproject.toml"))
    payload, attachments = _build(embed)

    section = payload["components"][0]
    assert section["type"] == SECTION
    assert section["accessory"]["type"] == THUMBNAIL
    # The jacket must ride along, or the blurred post shows no art at all.
    assert [f.filename for f in attachments] == ["pyproject.toml"]


def test_image_becomes_a_media_gallery_and_is_attached():
    embed = hikari.Embed(title="Testify")
    embed.set_image(hikari.File("pyproject.toml"))
    payload, attachments = _build(embed)

    kinds = [c["type"] for c in payload["components"]]
    assert MEDIA_GALLERY in kinds
    assert [f.filename for f in attachments] == ["pyproject.toml"]


def test_fields_collapse_into_one_text_display():
    embed = hikari.Embed(title="Testify")
    embed.add_field("Version", "6.8", inline=True)
    embed.add_field("BPM", "220", inline=True)
    payload, _ = _build(embed)

    texts = [c["content"] for c in payload["components"] if c["type"] == TEXT_DISPLAY]
    assert "**Version**\n6.8\n**BPM**\n220" in texts


def test_action_rows_survive_inside_the_container():
    """The whole point of a container: the buttons blur with the body."""
    payload, _ = _build(hikari.Embed(title="Testify"), [_row("song:c:42")])

    rows = [c for c in payload["components"] if c["type"] == ACTION_ROW]
    assert len(rows) == 1
    assert rows[0]["components"][0]["custom_id"] == "song:c:42"


def test_author_footer_and_timestamp_collapse_into_one_small_line():
    stamp = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)
    embed = hikari.Embed(title="Testify", timestamp=stamp)
    embed.set_author(name="marut")
    embed.set_footer("Live")
    payload, _ = _build(embed)

    texts = [c["content"] for c in payload["components"] if c["type"] == TEXT_DISPLAY]
    assert f"-# marut · Live · <t:{int(stamp.timestamp())}:R>" in texts


def test_embed_with_no_optional_parts_still_builds():
    payload, attachments = _build(hikari.Embed(description="just a body"))
    assert payload["components"][0]["content"] == "just a body"
    assert attachments == []
