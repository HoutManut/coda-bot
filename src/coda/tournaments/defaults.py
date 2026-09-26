"""Resolving `/tournament quick`'s unset options, in one place.

An omitted option is ``None`` and resolves here, not in a branch per option at
the command. Only the guild defaults reach ``/config``; the rest resolve to a
constant, because a *default* and a *setting* are different things and only the
second earns a registry entry.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from coda.db.enums import DifficultyClass, ThreadVisibility
from coda.settings import ConfigService
from coda.tournaments.levels import LevelRange, parse_level_range
from coda.tournaments.match import MatchOptions


@dataclass(frozen=True)
class Chosen:
    """What the user typed. ``None`` means they left it off."""

    difficulty_class: DifficultyClass | None
    song_mode: bool
    level: str | None = None
    best_of: str | None = None
    bans: bool | None = None
    open_join: bool = False
    visibility: str | None = None


async def resolve(
    db: AsyncSession,
    settings: ConfigService,
    chosen: Chosen,
    *,
    guild_id: int,
    channel_id: int,
    user_id: int,
) -> MatchOptions:
    """Fill every gap from the guild's defaults. Raises ``ValueError`` on a
    level band neither the user nor the guild wrote correctly."""
    return MatchOptions(
        levels=await _levels(
            db, settings, chosen.level,
            guild_id=guild_id, channel_id=channel_id, user_id=user_id),
        # Song mode is the user's explicit `any`, never a guild default: it
        # decides whether the match is competitive or casual, so it is typed
        # every time.
        difficulty_class=None if chosen.song_mode else chosen.difficulty_class,
        best_of=int(
            chosen.best_of
            or await _get(db, settings, "tournament_default_best_of",
                          guild_id, channel_id, user_id)
        ),
        pick_ban=(
            chosen.bans
            if chosen.bans is not None
            else bool(await _get(db, settings, "tournament_default_bans",
                                 guild_id, channel_id, user_id))
        ),
        # No guild default, for the reason song mode has none: an open room and
        # a closed one are different matches, not the same match configured
        # differently, so it is typed every time it is wanted.
        open_join=chosen.open_join,
        visibility=ThreadVisibility(
            chosen.visibility
            or await _get(db, settings, "tournament_default_visibility",
                          guild_id, channel_id, user_id)
        ),
    )


async def _levels(
    db: AsyncSession,
    settings: ConfigService,
    typed: str | None,
    *,
    guild_id: int,
    channel_id: int,
    user_id: int,
) -> LevelRange:
    """The typed band, else the guild's, else any.

    Unset means ANY rather than a refusal: "any level" is a choice an organizer
    is allowed to make, and it is printed on the board like every other filter.
    """
    if typed is not None:
        return parse_level_range(typed)
    stored = await _get(
        db, settings, "tournament_default_level", guild_id, channel_id, user_id)
    try:
        return parse_level_range(str(stored))
    except ValueError:
        # resolve() hands back whatever is stored without re-checking it
        # against the registry, so a band written before a validation change
        # can still come back malformed. Any level beats refusing every match.
        return LevelRange()


async def _get(
    db: AsyncSession,
    settings: ConfigService,
    key: str,
    guild_id: int,
    channel_id: int,
    user_id: int,
):
    return await settings.resolve(
        db, key,
        guild_id=guild_id, channel_id=channel_id, user_id=user_id, is_dm=False,
    )
