"""ORM models. Importing this package registers every table on ``Base.metadata``
(Alembic autogenerate and the seed both rely on that side effect)."""

from __future__ import annotations

from coda.db.models.alias import (
    ArtistAlias,
    CharterAlias,
    DifficultyAlias,
    SongAlias,
)
from coda.db.models.arcaea_account import (
    ArcaeaAccount,
    PlayerCredential,
    PlayerLink,
)
from coda.db.models.artist import (
    Artist,
    ArtistMember,
    DifficultyArtist,
    SongArtist,
)
from coda.db.models.bot_account import BotAccount
from coda.db.models.charter import Charter, DifficultyCharter, SongCharter
from coda.db.models.difficulty import SongDifficulty
from coda.db.models.live_update import LiveUpdateChannel, LiveUpdatePref
from coda.db.models.pack import Pack
from coda.db.models.pending_request import PendingRequest
from coda.db.models.play_score import PlayScore
from coda.db.models.search_config import DifficultySearchConfig
from coda.db.models.song import Song
from coda.db.models.tag import DifficultyTag, SongTag, Tag, TagCategory

__all__ = [
    "Pack",
    "Song",
    "SongDifficulty",
    "Artist",
    "ArtistMember",
    "SongArtist",
    "DifficultyArtist",
    "Charter",
    "SongCharter",
    "DifficultyCharter",
    "SongAlias",
    "DifficultyAlias",
    "ArtistAlias",
    "CharterAlias",
    "TagCategory",
    "Tag",
    "SongTag",
    "DifficultyTag",
    "BotAccount",
    "ArcaeaAccount",
    "PlayerLink",
    "PlayerCredential",
    "LiveUpdateChannel",
    "LiveUpdatePref",
    "PlayScore",
    "PendingRequest",
    "DifficultySearchConfig",
]
