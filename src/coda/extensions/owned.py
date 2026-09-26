"""/owned -- declare which songs you can actually play.

Two pages on one ephemeral message: packs, then the Beyonds of the songs those
packs gave you. Beyond gets its own page because owning a pack says nothing
about it -- 66 of 67 Beyonds need a world map or story progression first.

Components use the raw ``own:`` custom-id contract in ``ownership/components``
dispatched by the persistent listener below (the approvals pattern), so every
click is stateless and the message survives a restart.
"""

from __future__ import annotations

import hikari
import lightbulb
from sqlalchemy.ext.asyncio import AsyncSession

from coda.catalog.autocomplete import song_choices
from coda.catalog.jackets import display_name
from coda.db.models import Song
from coda.db.session import async_session
from coda.ownership import components as ids
from coda.ownership.picker import (
    Option,
    beyond_options,
    chunked,
    held_count,
    locked_note,
    pack_options,
    pickable,
    range_label,
)
from coda.ownership.service import (
    beyond_charts,
    charts_in_packs,
    charts_in_song,
    clear_all,
    declared_chart_ids,
    inferred_pack_ids,
    pack_counts,
    replace,
)
from coda.scores import TrackingService
from coda.utils.render import COLOR_INFO, Rendered, apply, notice, respond

loader = lightbulb.Loader()

_NOT_REGISTERED = "You're not registered yet. Run `/register` first."
_NOT_YOURS = "That isn't your picker. Run `/owned` to open your own."
_SINGLES_HINT = "-# Memory Archive songs: `/owned song`"


# --- views ------------------------------------------------------------------


async def _pack_state(
    db: AsyncSession, account_id: int
) -> tuple[list[Option], list[list[Option]]]:
    """Every pack, and the menu chunks -- which exclude the locked ones.

    One helper for the view and the write, so a menu index can never mean two
    different things between drawing a message and clicking it.
    """
    packs = pack_options(
        await pack_counts(db, account_id), await inferred_pack_ids(db, account_id)
    )
    return packs, chunked(pickable(packs))


async def _packs_view(
    db: AsyncSession,
    discord_id: int,
    account_id: int,
    locale: object,
    *,
    confirming_clear: bool = False,
) -> Rendered:
    packs, chunks = await _pack_state(db, account_id)
    beyonds = beyond_options(await beyond_charts(db, account_id), locale)

    lines = [f"**{held_count(packs)} of {len(packs)} packs**"]
    note = locked_note(packs)
    if note is not None:
        lines.append(note)
    lines.append(_SINGLES_HINT)

    embed = hikari.Embed(
        title="Songs you can play",
        description="\n".join(lines),
        color=COLOR_INFO,
    )
    rows = [
        ids.menu_row(discord_id, ids.PACK_MENU, index, chunk, range_label(chunk))
        for index, chunk in enumerate(chunks)
    ]
    rows.append(
        ids.pack_buttons(
            discord_id,
            beyonds=_beyond_tally(beyonds) if beyonds else None,
            confirming_clear=confirming_clear,
        )
    )
    return Rendered(embed, rows=rows)


async def _beyond_state(
    db: AsyncSession, account_id: int, locale: object
) -> tuple[list[Option], list[list[Option]]]:
    """Every offered Beyond, and the menu chunks -- which exclude the played ones.

    The pack page's :func:`_pack_state` with a different subject, and for the
    same reason: one builder for the view and the write.
    """
    options = beyond_options(await beyond_charts(db, account_id), locale)
    return options, chunked(pickable(options))


async def _beyonds_view(
    db: AsyncSession, discord_id: int, account_id: int, locale: object
) -> Rendered:
    options, chunks = await _beyond_state(db, account_id, locale)
    if not options:
        return notice(
            "Nothing to answer", "None of your packs has a Beyond.", transient=True
        )

    lines = [f"**{held_count(options)} of {len(options)}**"]
    note = locked_note(options)
    if note is not None:
        lines.append(note)

    embed = hikari.Embed(
        title="Which Beyonds can you play?",
        description="\n".join(lines),
        color=COLOR_INFO,
    )
    rows = [
        ids.menu_row(discord_id, ids.BEYOND_MENU, index, chunk, range_label(chunk))
        for index, chunk in enumerate(chunks)
    ]
    rows.append(ids.beyond_buttons(discord_id))
    return Rendered(embed, rows=rows)


async def _summary_view(
    db: AsyncSession, account_id: int, locale: object
) -> Rendered:
    packs, _chunks = await _pack_state(db, account_id)
    beyonds = beyond_options(await beyond_charts(db, account_id), locale)
    line = f"**{held_count(packs)} of {len(packs)} packs**"
    if beyonds:
        owned, total = _beyond_tally(beyonds)
        line += f" · **{owned} of {total} Beyonds**"
    return Rendered(hikari.Embed(title="Saved", description=line, color=COLOR_INFO))


def _beyond_tally(options: list[Option]) -> tuple[int, int]:
    return held_count(options), len(options)


# --- writes -----------------------------------------------------------------


async def _write_packs(
    db: AsyncSession, account_id: int, index: int, selected: set[str]
) -> None:
    """Apply one pack menu's selection.

    Chunk membership is recomputed here rather than trusted from the click, so a
    pack that shifted chunks since the message was drawn is simply left alone
    instead of being cleared by a stale menu.

    Deselected packs are cleared over their FULL chart set so their Beyond
    answers go too; selected ones are granted only their non-Beyond charts, which
    is what keeps a pack re-tick from wiping the Beyond page.
    """
    _packs, chunks = await _pack_state(db, account_id)
    if index >= len(chunks):
        return
    chunk_ids = {option.value for option in chunks[index]}
    kept = selected & chunk_ids

    owned = await charts_in_packs(db, kept)
    within = owned | await charts_in_packs(
        db, chunk_ids - kept, include_beyond=True
    )
    await replace(db, account_id, owned=owned, within=within)


async def _write_beyonds(
    db: AsyncSession, account_id: int, index: int, selected: set[str], locale: object
) -> None:
    _options, chunks = await _beyond_state(db, account_id, locale)
    if index >= len(chunks):
        return
    within = {int(option.value) for option in chunks[index]}
    owned = {int(value) for value in selected if value.isdigit()} & within
    await replace(db, account_id, owned=owned, within=within)


async def _select_all_packs(db: AsyncSession, account_id: int) -> None:
    """Ticks everything still askable. A locked pack needs no row -- its charts
    are already reachable through the inference that locked it."""
    _packs, chunks = await _pack_state(db, account_id)
    askable = {option.value for chunk in chunks for option in chunk}
    charts = await charts_in_packs(db, askable)
    await replace(db, account_id, owned=charts, within=charts)


async def _set_all_beyonds(
    db: AsyncSession, account_id: int, locale: object, *, owned: bool
) -> None:
    """Bulk-answers only what is still askable -- a played Beyond is not among
    the things `None` can take away."""
    _options, chunks = await _beyond_state(db, account_id, locale)
    within = {int(option.value) for chunk in chunks for option in chunk}
    await replace(db, account_id, owned=within if owned else set(), within=within)


async def _toggle_song(
    db: AsyncSession, account_id: int, song_id: str, locale: object
) -> Rendered:
    song = await db.get(Song, song_id)
    if song is None:
        return notice(
            "No such song", "Pick one from the suggestions as you type.", transient=True
        )
    granted = await charts_in_song(db, song_id)
    if not granted:
        return notice(
            "Nothing to declare",
            "That song has no chart a declaration can cover.",
            transient=True,
        )

    adding = not granted <= await declared_chart_ids(db, account_id)
    # Removing clears the Beyond too, the same asymmetry a pack untick uses.
    within = (
        granted if adding else await charts_in_song(db, song_id, include_beyond=True)
    )
    await replace(db, account_id, owned=granted if adding else set(), within=within)

    name = display_name(song.name_en, song.name_jp, locale)
    body = f"**{name}**"

    return notice("Added" if adding else "Removed", body)


# --- command ----------------------------------------------------------------


async def _ac_song(ctx: lightbulb.AutocompleteContext[str]) -> None:
    """Song rows only -- a level/CC browse has nothing to toggle."""
    typed = str(ctx.focused.value or "").strip()
    async with async_session() as db:
        choices = await song_choices(db, typed, numeric_echo=False)
    await ctx.respond(choices[:25])


@loader.command
class Owned(
    lightbulb.SlashCommand,
    name="owned",
    description="Declare which songs you can play",
):
    song = lightbulb.string(
        "song",
        "Toggle one song instead of a whole pack",
        default=None,
        autocomplete=_ac_song,
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        async with async_session() as db:
            account_id = await _account_id(db, int(ctx.user.id))
            if account_id is None:
                await ctx.respond(_NOT_REGISTERED, ephemeral=True)
                return
            if self.song is not None:
                rendered = await _toggle_song(
                    db, account_id, self.song, ctx.interaction.locale
                )
            else:
                rendered = await _packs_view(
                    db, int(ctx.user.id), account_id, ctx.interaction.locale
                )
            await db.commit()
        await respond(ctx, rendered, ephemeral=True)


async def _account_id(db: AsyncSession, discord_id: int) -> int | None:
    link = await TrackingService().link_of(db, discord_id)
    return None if link is None else link.arcaea_account_id


# --- persistent component listener ------------------------------------------


@loader.listener(hikari.InteractionCreateEvent)
async def _on_owned_component(event: hikari.InteractionCreateEvent) -> None:
    interaction = event.interaction
    if not isinstance(interaction, hikari.ComponentInteraction):
        return
    click = ids.parse(interaction.custom_id)
    if click is None:
        return
    if click.discord_id != int(interaction.user.id):
        await interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_CREATE,
            _NOT_YOURS,
            flags=hikari.MessageFlag.EPHEMERAL,
        )
        return

    async with async_session() as db:
        rendered = await _dispatch(db, interaction, click)
        await db.commit()
    if rendered is not None:
        await apply(interaction, rendered)


async def _dispatch(
    db: AsyncSession, interaction: hikari.ComponentInteraction, click: ids.Click
) -> Rendered | None:
    account_id = await _account_id(db, click.discord_id)
    if account_id is None:
        return notice("No longer registered", _NOT_REGISTERED, transient=True)

    locale = interaction.locale
    discord_id = click.discord_id
    selected = set(interaction.values)

    match click.action:
        case ids.PACK_MENU:
            await _write_packs(db, account_id, click.index, selected)
        case ids.BEYOND_MENU:
            await _write_beyonds(db, account_id, click.index, selected, locale)
            return await _beyonds_view(db, discord_id, account_id, locale)
        case ids.SELECT_ALL:
            await _select_all_packs(db, account_id)
        case ids.CLEAR:
            return await _packs_view(
                db, discord_id, account_id, locale, confirming_clear=True
            )
        case ids.CLEAR_CONFIRM:
            await clear_all(db, account_id)
        case ids.BEYOND_PAGE:
            return await _beyonds_view(db, discord_id, account_id, locale)
        case ids.BEYOND_ALL:
            await _set_all_beyonds(db, account_id, locale, owned=True)
            return await _beyonds_view(db, discord_id, account_id, locale)
        case ids.BEYOND_NONE:
            await _set_all_beyonds(db, account_id, locale, owned=False)
            return await _beyonds_view(db, discord_id, account_id, locale)
        case ids.DONE:
            return await _summary_view(db, account_id, locale)
        case _:
            return None
    return await _packs_view(db, discord_id, account_id, locale)
