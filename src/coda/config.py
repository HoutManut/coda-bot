"""Application settings loaded from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _snowflakes(name: str) -> tuple[int, ...]:
    """Parse a comma- or space-separated ID list, preserving order."""
    raw = os.environ.get(name, "")
    return tuple(int(part) for part in raw.replace(",", " ").split())


_YOUTUBE_HOSTS = frozenset({"www.youtube.com", "youtube.com", "youtu.be"})


def _youtube_urls(name: str) -> tuple[str, ...]:
    """Comma-separated URL list, rejecting anything not hosted on YouTube."""
    raw = os.environ.get(name, "")
    urls = tuple(part.strip() for part in raw.split(",") if part.strip())
    for url in urls:
        host = urlsplit(url).hostname
        if host not in _YOUTUBE_HOSTS:
            raise RuntimeError(f"{name} entry is not a youtube.com/youtu.be URL: {url!r}")
    return urls


@dataclass(frozen=True, slots=True)
class Config:
    """Immutable runtime configuration."""

    bot_token: str
    dev_guild_ids: tuple[int, ...]
    # Async SQLAlchemy URL, e.g. postgresql+asyncpg://user:pass@host/db.
    database_url: str
    # Discord user IDs allowed to set global config and to register reserved
    # codes. A set: for a permission check, order carries no meaning.
    owner_ids: frozenset[int]
    # Guilds /run is created in. Nothing else limits where the owner terminal
    # is reachable, so an empty tuple means it exists nowhere -- never None,
    # which lightbulb reads as "fall back to default_enabled_guilds".
    owner_guild_ids: tuple[int, ...]
    # The first of OWNER_IDS -- the human to contact when something needs one
    # (an ambiguous friend diff, a stale claim). None if OWNER_IDS is unset.
    main_owner_id: int | None
    # Fernet key for stored Arcaea credentials. No rotation path: changing it
    # orphans every encrypted row.
    fernet_key: str
    # The owner's own Arcaea friend code. Reserved: only OWNER_IDS members may
    # register it (anyone else is impersonating). None disables that guard.
    owner_friend_code: str | None
    # Base seconds between two polls OF ONE ACCOUNT -- independent of how many
    # accounts exist. The poller jitters heavily around it, so it is an average,
    # not a schedule.
    poll_interval: float
    # A max score gets a link, chosen at random from this list -- the easter
    # egg's whole point is not knowing which one lands. youtube.com/youtu.be
    # only, enforced at parse time so nothing downstream has to check. Empty
    # tuple disables the link (score still renders, just plain).
    max_score_urls: tuple[str, ...]
    # Logging. All optional with defaults so importing config (alembic, admin)
    # never needs them. Per-handler thresholds are static for the process.
    log_level: str
    log_dir: str | None
    log_file_level: str
    log_discord_channel_id: int | None
    log_discord_level: str

    @classmethod
    def from_env(cls) -> Config:
        owner_ids = _snowflakes("OWNER_IDS")
        dev_guild_ids = _snowflakes("DEV_GUILD_IDS")
        discord_log_channel = os.environ.get("LOG_DISCORD_CHANNEL_ID")
        return cls(
            bot_token=_require("BOT_TOKEN"),
            dev_guild_ids=dev_guild_ids,
            database_url=_require("DATABASE_URL"),
            owner_ids=frozenset(owner_ids),
            owner_guild_ids=_snowflakes("OWNER_GUILD_IDS") or dev_guild_ids,
            main_owner_id=owner_ids[0] if owner_ids else None,
            fernet_key=_require("FERNET_KEY"),
            owner_friend_code=os.environ.get("OWNER_FRIEND_CODE") or None,
            poll_interval=float(os.environ.get("POLL_INTERVAL") or 90.0),
            max_score_urls=_youtube_urls("MAX_SCORE_URLS"),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
            log_dir=os.environ.get("LOG_DIR") or None,
            log_file_level=os.environ.get("LOG_FILE_LEVEL", "DEBUG"),
            log_discord_channel_id=int(discord_log_channel) if discord_log_channel else None,
            log_discord_level=os.environ.get("LOG_DISCORD_LEVEL", "WARNING"),
        )



config = Config.from_env()
