"""Render an embed as a Components V2 container, optionally spoilered.

Discord has no spoiler flag for rich embeds -- only attachments, ``||text||``
and Components V2 items can blur. A container is the only shape that hides the
body, the jacket *and* the buttons as one unit, because the action rows sit
inside it rather than beside it.

So every embed builder in the codebase keeps building embeds, and this converts
one when it has to be blurred. The mapping is lossy in three known ways, all of
them behind the blur: inline fields stack instead of sitting three across, the
embed's native timestamp becomes ``<t:...>`` markdown, and an author icon is
dropped (the section's one accessory slot holds the jacket).
"""

from __future__ import annotations

import hikari
from hikari.impl import MessageActionRowBuilder
from hikari.impl import special_endpoints as builders


def as_container(
    embed: hikari.Embed,
    rows: list[MessageActionRowBuilder],
    *,
    spoiler: bool,
) -> builders.ContainerComponentBuilder:
    """The same content as ``embed`` plus ``rows``, as one container.

    The jacket is recovered from the embed itself -- ``embed.thumbnail.resource``
    is the very ``hikari.File`` that was passed to ``set_thumbnail`` -- so
    callers never have to hand the file over separately.
    """
    container = builders.ContainerComponentBuilder(
        accent_color=embed.color, spoiler=spoiler
    )

    heading = [text for text in (_title(embed), embed.description) if text]
    thumbnail = embed.thumbnail
    if thumbnail is not None:
        section = builders.SectionComponentBuilder(
            accessory=builders.ThumbnailComponentBuilder(media=thumbnail.resource)
        )
        for text in heading or [""]:
            section.add_text_display(text)
        container.add_component(section)
    else:
        for text in heading:
            container.add_text_display(text)

    if embed.image is not None:
        # Both add_media_gallery and add_action_row take a *sequence* and build
        # the wrapper themselves; handing either a single builder raises.
        container.add_media_gallery(
            [builders.MediaGalleryItemBuilder(media=embed.image.resource)]
        )

    if embed.fields:
        container.add_text_display(
            "\n".join(f"**{field.name}**\n{field.value}" for field in embed.fields)
        )

    caption = _caption(embed)
    if caption:
        container.add_text_display(caption)

    for row in rows:
        # add_component, not add_action_row: the latter builds a *new* row out of
        # loose components and raises TypeError when handed a built one.
        container.add_component(row)

    return container


def _title(embed: hikari.Embed) -> str | None:
    if embed.title is None:
        return None
    return f"## {embed.title}"


def _caption(embed: hikari.Embed) -> str:
    """The author, footer and timestamp collapsed into one small-text line."""
    parts: list[str] = []
    if embed.author is not None and embed.author.name:
        parts.append(embed.author.name)
    if embed.footer is not None and embed.footer.text:
        parts.append(embed.footer.text)
    if embed.timestamp is not None:
        # :R, not :f -- the only embeds carrying a timestamp render a play, and
        # what a reader wants from one is how long ago it happened. Discord
        # keeps the absolute time on hover either way.
        parts.append(f"<t:{int(embed.timestamp.timestamp())}:R>")
    return f"-# {' · '.join(parts)}" if parts else ""
