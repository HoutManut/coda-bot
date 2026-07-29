"""Effective permissions for a member in a channel.

Neither hikari nor lightbulb ships this: ``InteractionMember.permissions`` is
computed by Discord for the channel a command was *invoked* in, which does not
help when asking about some other channel.

Best-effort by design -- it reads the cache, and returns None when the cache
cannot answer. Callers treat None as "don't know" and lean on a check at the
point of actually posting, which is the only one that can't be stale.
"""

from __future__ import annotations

import logging

import hikari

logger = logging.getLogger(__name__)


def permissions_in(
    channel: hikari.PermissibleGuildChannel,
    member: hikari.Member,
    roles: list[hikari.Role],
) -> hikari.Permissions:
    """Resolve ``member``'s permissions in ``channel``.

    Applies Discord's documented order: role baseline, then the @everyone
    overwrite, then role overwrites (all denies before all allows), then the
    member overwrite. Administrator and guild ownership short-circuit to all.
    """
    base = hikari.Permissions.NONE
    for role in roles:
        base |= role.permissions

    if base & hikari.Permissions.ADMINISTRATOR:
        return hikari.Permissions.all_permissions()

    overwrites = channel.permission_overwrites

    # @everyone's overwrite is keyed by the guild id.
    everyone = overwrites.get(channel.guild_id)
    if everyone is not None:
        base &= ~everyone.deny
        base |= everyone.allow

    # Role overwrites accumulate first, so that an allow on one role beats a
    # deny on another -- applying each role's pair in turn would not.
    allow = hikari.Permissions.NONE
    deny = hikari.Permissions.NONE
    for role in roles:
        if role.id == channel.guild_id:
            continue
        overwrite = overwrites.get(role.id)
        if overwrite is not None:
            allow |= overwrite.allow
            deny |= overwrite.deny
    base &= ~deny
    base |= allow

    # The member's own overwrite wins over every role.
    member_overwrite = overwrites.get(member.id)
    if member_overwrite is not None:
        base &= ~member_overwrite.deny
        base |= member_overwrite.allow

    return base


def can_send_in(
    app: hikari.CacheAware,
    channel_id: int,
    member: hikari.Member,
) -> bool | None:
    """Whether ``member`` can send messages in ``channel_id``.

    None means the cache could not answer -- not False. Refusing on a cache miss
    would reject legitimate choices whenever the cache is cold.
    """
    return _has(app, channel_id, member, hikari.Permissions.SEND_MESSAGES)


def can_view(
    app: hikari.CacheAware,
    channel_id: int,
    member: hikari.Member,
) -> bool | None:
    """Whether ``member`` can see ``channel_id`` at all.

    Asked of a *parent* channel before putting something in a thread under it:
    thread access is inherited, so a member who cannot view the parent cannot
    reach the thread either -- being added to a private thread does not grant it.

    None means the cache could not answer, same contract as :func:`can_send_in`.
    """
    return _has(app, channel_id, member, hikari.Permissions.VIEW_CHANNEL)


def everyone_can_view(app: hikari.CacheAware, channel_id: int) -> bool | None:
    """Whether ``channel_id`` is visible to the guild by default.

    Asked of a channel about to become everyone's destination, where the
    per-member :func:`can_view` cannot help: it answers for the caller, and the
    caller is an admin who can see everything.

    False does **not** mean nobody else can see it -- a role overwrite can grant
    VIEW_CHANNEL back to a subset, which is the ordinary "@everyone denied,
    Member allowed" server. It means the channel is not open by default, which
    is worth saying out loud and not worth refusing over. None, as elsewhere, is
    the cache declining to answer.
    """
    channel = app.cache.get_guild_channel(channel_id)
    if channel is None:
        return None

    # The @everyone role's id is the guild's, and so is its overwrite's.
    everyone = app.cache.get_role(channel.guild_id)
    if everyone is None:
        return None

    perms = everyone.permissions
    if perms & hikari.Permissions.ADMINISTRATOR:
        return True

    overwrite = channel.permission_overwrites.get(channel.guild_id)
    if overwrite is not None:
        perms &= ~overwrite.deny
        perms |= overwrite.allow
    return bool(perms & hikari.Permissions.VIEW_CHANNEL)


def _has(
    app: hikari.CacheAware,
    channel_id: int,
    member: hikari.Member,
    permission: hikari.Permissions,
) -> bool | None:
    channel = app.cache.get_guild_channel(channel_id)
    if channel is None:
        return None

    guild = app.cache.get_guild(channel.guild_id)
    if guild is not None and guild.owner_id == member.id:
        return True

    roles = list(member.get_roles())
    if not roles:
        return None

    return bool(permissions_in(channel, member, roles) & permission)
