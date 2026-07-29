"""Send a DM to a user, returning the message or ``None`` if it could not land."""

from __future__ import annotations

import logging
from typing import Any

import hikari

logger = logging.getLogger(__name__)


async def send_dm(
    app: hikari.RESTAware, user_id: int, **kwargs: Any
) -> hikari.Message | None:
    """DM ``user_id``. ``kwargs`` pass straight through to ``channel.send``
    (``embed``, ``components``, ``content``, ...). ``None`` = it did not send."""
    try:
        channel = await app.rest.create_dm_channel(user_id)
        return await channel.send(**kwargs)
    except hikari.ForbiddenError:
        logger.info("DM refused for %s (DMs closed)", user_id)
        return None
    except hikari.HikariError:
        logger.exception("DM failed for %s", user_id)
        return None
