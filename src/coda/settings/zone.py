"""The local clock that applies in a context.

One key, ``timezone``, decides both when a Chardle daily rolls over and whether
a day/night jacket shows its night art -- they are the same question about the
same viewer, asked by two features.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from coda.settings.service import ConfigService
from coda.utils.zones import parse_zone


async def effective_zone(
    db: AsyncSession,
    settings: ConfigService,
    *,
    guild_id: int | None,
    channel_id: int,
    user_id: int,
) -> ZoneInfo:
    """The configured zone for this context: guild override, else bot default."""
    raw = await settings.resolve(
        db,
        "timezone",
        guild_id=guild_id,
        channel_id=channel_id,
        user_id=user_id,
        is_dm=guild_id is None,
    )
    return parse_zone(str(raw))
