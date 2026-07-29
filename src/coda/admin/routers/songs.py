"""Song list/search, song detail (with difficulty tabs), and song CRUD."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import (
    String,
    case,
    cast,
    delete,
    exists,
    func,
    or_,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from coda.admin import aliassync, songfilters
from coda.admin.deps import get_session
from coda.admin.forms import form_text, parse_song_base, song_date
from coda.admin.listing import paginate, paginate_rows
from coda.admin.presenters import DIFFICULTY_ORDER, tag_chip_style
from coda.admin.templating import templates
from coda.catalog.aliases import difficulty_alias_terms, song_alias_terms
from coda.catalog.resolution import OVERRIDABLE_FIELDS
from coda.db.models import (
    Artist,
    ArtistAlias,
    Charter,
    CharterAlias,
    DifficultyAlias,
    DifficultyArtist,
    DifficultyCharter,
    DifficultyTag,
    Pack,
    Song,
    SongAlias,
    SongArtist,
    SongCharter,
    SongDifficulty,
    SongTag,
    Tag,
    TagCategory,
)

router = APIRouter()

# The default pack a new song falls into when none is picked.
DEFAULT_PACK_ID = "base"

_SONG_COLS = {
    "idx": Song.idx,
    "song_id": Song.song_id,
    "name": Song.name_en,
    "pack": Song.pack_name,
}


def _difficulty_order_case():
    """ORDER BY expression putting charts in :data:`DIFFICULTY_ORDER`.

    The column is a DB enum, so ordering by it would give declaration order --
    which puts BYD before ETR, disagreeing with the detail page.
    """
    # Compared as text: the column is a native PG enum, so binding the ordering
    # keys as plain strings gives "operator does not exist: difficulty_class =
    # character varying".
    return case(
        {d.value: i for i, d in enumerate(DIFFICULTY_ORDER)},
        value=cast(SongDifficulty.difficulty, String),
        else_=99,
    )


_CHART_COLS = {
    "idx": Song.idx,
    "song_id": Song.song_id,
    "name": Song.name_en,
    "pack": Song.pack_name,
    "difficulty": _difficulty_order_case(),
    "level": SongDifficulty.level,
    "cc": SongDifficulty.rating,
    "note": SongDifficulty.note,
}


def _song_search(pattern: str):
    """Songs matching ``pattern`` on any alias.

    EXISTS rather than a join: a join fans out one row per matching alias, which
    then needs DISTINCT, which in turn has to agree with the ORDER BY of
    whichever column is being sorted on.
    """
    return exists().where(
        SongAlias.song_id == Song.song_id, SongAlias.alias.ilike(pattern)
    )


def _chart_search(pattern: str):
    """Charts matching ``pattern`` on a song alias *or* a per-chart alias."""
    return or_(
        _song_search(pattern),
        exists().where(
            DifficultyAlias.difficulty_id == SongDifficulty.id,
            DifficultyAlias.alias.ilike(pattern),
        ),
    )


async def _datalist_options(session: AsyncSession) -> dict:
    """Distinct existing values for the bg / pack_name autosuggest datalists, plus
    the most recent version string (default for a new song)."""
    bgs = (
        await session.scalars(
            select(Song.bg).where(Song.bg != "").distinct().order_by(Song.bg)
        )
    ).all()
    pack_names = (
        await session.scalars(
            select(Song.pack_name)
            .where(Song.pack_name != "")
            .distinct()
            .order_by(Song.pack_name)
        )
    ).all()
    latest_version = await session.scalar(
        select(Song.version).order_by(Song.idx.desc()).limit(1)
    )
    return {
        "bg_options": list(bgs),
        "packname_options": list(pack_names),
        "latest_version": latest_version or "",
    }


async def _entity_link_options(session: AsyncSession) -> dict:
    """Artist/charter link options, each carrying its search terms (name + id +
    aliases) so the picker on the song page can match by alias."""

    async def build(entity, alias_model, id_col):
        rows = (await session.scalars(select(entity).order_by(entity.name))).all()
        alias_rows = (
            await session.scalars(select(alias_model))
        ).all()
        terms_by_id: dict[str, set[str]] = {}
        for a in alias_rows:
            terms_by_id.setdefault(getattr(a, id_col), set()).add(a.alias)
        opts = []
        for r in rows:
            eid = getattr(r, id_col)
            terms = terms_by_id.get(eid, set()) | {r.name, eid}
            opts.append({"id": eid, "name": r.name, "terms": sorted(terms)})
        return opts

    return {
        "artist_opts": await build(Artist, ArtistAlias, "artist_id"),
        "charter_opts": await build(Charter, CharterAlias, "charter_id"),
    }


async def _tag_options(session: AsyncSession) -> dict:
    """Tag vocabulary for the picker.

    ``tag_categories`` drives the new-category datalist; ``tag_groups`` is the
    full vocabulary grouped by category (with a precomputed chip-tint ``style``)
    that the floating picker panel renders and filters client-side.
    """
    categories = (
        await session.scalars(
            select(TagCategory).order_by(TagCategory.sort, TagCategory.label)
        )
    ).all()
    rows = (
        await session.execute(
            select(Tag, TagCategory)
            .join(TagCategory, TagCategory.id == Tag.category_id)
            .order_by(TagCategory.sort, TagCategory.label, Tag.label)
        )
    ).all()
    groups: dict[int, dict] = {}
    for tag, cat in rows:
        g = groups.get(cat.id)
        if g is None:
            g = groups[cat.id] = {
                "label": cat.label,
                "style": tag_chip_style(cat.color),
                "tags": [],
            }
        g["tags"].append({"slug": tag.slug, "label": tag.label})
    return {
        "tag_categories": list(categories),
        "tag_groups": list(groups.values()),
    }


async def _chart_strips(
    session: AsyncSession, song_ids: list[str]
) -> dict[str, list[SongDifficulty]]:
    """Every chart of the songs on screen, grouped by song in display order.

    One query for the whole page: the row's chart strip is its headline feature
    and ``paginate`` selects ``Song`` alone, so templating it off the song would
    fire a lazy load per row.
    """
    if not song_ids:
        return {}
    rows = (
        await session.scalars(
            select(SongDifficulty).where(SongDifficulty.song_id.in_(song_ids))
        )
    ).all()
    order = {d: i for i, d in enumerate(DIFFICULTY_ORDER)}
    strips: dict[str, list[SongDifficulty]] = {sid: [] for sid in song_ids}
    for row in rows:
        strips[row.song_id].append(row)
    for charts in strips.values():
        charts.sort(key=lambda c: order.get(c.difficulty, 99))
    return strips


async def _list_songs(request, session: AsyncSession, q: str, extra: dict) -> dict:
    base = select(Song)
    if q:
        base = base.where(_song_search(f"%{q}%"))
    page = await paginate(
        session, base, request=request, columns=_SONG_COLS,
        default_sort="idx", path="/songs", q=q, extra=extra,
    )
    return {
        "page": page,
        "strips": await _chart_strips(session, [s.song_id for s in page.items]),
    }


async def _list_charts(
    request, session: AsyncSession, q: str, extra: dict, filters: songfilters.ChartFilters
) -> dict:
    base = select(Song, SongDifficulty).join(
        SongDifficulty, SongDifficulty.song_id == Song.song_id
    )
    if q:
        base = base.where(_chart_search(f"%{q}%"))
    for predicate in filters.predicates():
        base = base.where(predicate)
    page = await paginate_rows(
        session, base, request=request, columns=_CHART_COLS,
        default_sort="idx", path="/songs", q=q, extra=extra,
    )
    return {"page": page}


@router.get("/songs", response_class=HTMLResponse)
async def list_songs(
    request: Request,
    q: str = "",
    mode: str = "songs",
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    q = q.strip()
    if mode not in ("songs", "charts"):
        mode = "songs"
    filters = songfilters.parse(request.query_params)
    # A chart-level filter cannot mean anything against one row per song, so it
    # forces charts mode -- and says so, rather than switching silently.
    switched = filters.active and mode == "songs"
    if switched:
        mode = "charts"
    extra = filters.extra(mode)
    if mode == "charts":
        context = await _list_charts(request, session, q, extra, filters)
    else:
        context = await _list_songs(request, session, q, extra)
    return templates.TemplateResponse(
        request,
        "song_list.html",
        {
            "mode": mode, "filters": filters, "switched": switched,
            "gap_choices": songfilters.GAP_CHOICES, **context,
        },
    )


@router.get("/songs/new", response_class=HTMLResponse)
async def new_song_form(
    request: Request, session: AsyncSession = Depends(get_session)
) -> HTMLResponse:
    next_idx = (await session.scalar(select(func.max(Song.idx)))) or 0
    packs = (await session.scalars(select(Pack).order_by(Pack.name))).all()
    return templates.TemplateResponse(
        request,
        "song_form.html",
        {
            "song": None, "packs": packs, "suggested_idx": next_idx + 1,
            "error": None, "default_pack_id": DEFAULT_PACK_ID,
            **(await _datalist_options(session)),
        },
    )


@router.post("/songs", response_class=HTMLResponse, response_model=None)
async def create_song(
    request: Request, session: AsyncSession = Depends(get_session)
) -> HTMLResponse | RedirectResponse:
    form = await request.form()
    song_id = form_text(form, "song_id").strip()
    idx_raw = form_text(form, "idx").strip()

    async def _error(msg: str) -> HTMLResponse:
        packs = (await session.scalars(select(Pack).order_by(Pack.name))).all()
        return templates.TemplateResponse(
            request,
            "song_form.html",
            # posted_date is reconstructed here because the date arrives as a
            # day/offset pair; re-reading a plain "date" field off the form
            # would silently drop it on every validation error.
            {"song": None, "packs": packs, "suggested_idx": idx_raw, "error": msg,
             "form": form, "default_pack_id": DEFAULT_PACK_ID,
             "posted_date": song_date(form),
             **(await _datalist_options(session))},
            status_code=400,
        )

    if not song_id:
        return await _error("song_id is required.")
    if await session.get(Song, song_id):
        return await _error(f"song_id {song_id!r} already exists.")
    try:
        idx = int(idx_raw)
    except ValueError:
        return await _error("idx must be an integer.")
    if await session.scalar(select(Song).where(Song.idx == idx)):
        return await _error(f"idx {idx} is already taken.")

    fields = parse_song_base(form)
    # Pack defaults to the base game pack when none is picked (and base exists).
    if fields["pack_id"] is None and await session.get(Pack, DEFAULT_PACK_ID):
        fields["pack_id"] = DEFAULT_PACK_ID

    # Unlike idx, a taken date bumps on create rather than erroring: an idx
    # collision usually means a typo, whereas a pack releasing several songs on
    # one day makes a date collision the expected case.
    notice = ""
    if fields["date"]:
        try:
            notice = await _reserve_date(session, fields["date"], None)
        except DateConflict as exc:
            await session.rollback()
            return await _error(str(exc))

    song = Song(song_id=song_id, idx=idx, **fields)
    session.add(song)
    await session.flush()
    await aliassync.sync_song(
        session, song_id,
        new_name_en=fields["name_en"], new_name_jp=fields["name_jp"],
    )
    await session.commit()
    url = f"/songs/{song_id}"
    if notice:
        url += f"?notice={quote(notice)}"
    return RedirectResponse(url=url, status_code=303)


@router.get("/songs/{song_id}", response_class=HTMLResponse)
async def song_detail(
    request: Request,
    song_id: str,
    error: str = "",
    notice: str = "",
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    song = await session.get(Song, song_id)
    if song is None:
        return HTMLResponse("Song not found", status_code=404)

    diffs = (
        await session.scalars(
            select(SongDifficulty).where(SongDifficulty.song_id == song_id)
        )
    ).all()
    order = {d: i for i, d in enumerate(DIFFICULTY_ORDER)}
    diffs = sorted(diffs, key=lambda d: order.get(d.difficulty, 99))

    aliases = (
        await session.scalars(
            select(SongAlias).where(SongAlias.song_id == song_id).order_by(SongAlias.alias)
        )
    ).all()
    auto_terms = song_alias_terms(song.song_id, song.name_en, song.name_jp)

    # Per-chart aliases: rows grouped by difficulty, plus each chart's auto terms
    # (its name_en override and game_song_id) so the UI can badge them.
    diff_ids = [d.id for d in diffs]
    diff_alias_rows = (
        await session.scalars(
            select(DifficultyAlias)
            .where(DifficultyAlias.difficulty_id.in_(diff_ids))
            .order_by(DifficultyAlias.alias)
        )
    ).all() if diff_ids else []
    diff_aliases: dict[int, list] = {d.id: [] for d in diffs}
    for row in diff_alias_rows:
        diff_aliases[row.difficulty_id].append(row)
    diff_auto_terms = {
        d.id: difficulty_alias_terms(d.name_en, d.game_song_id) for d in diffs
    }

    # Per-chart relational links (override of the song's links), grouped by chart.
    diff_artists: dict[int, list] = {d.id: [] for d in diffs}
    diff_charters: dict[int, list] = {d.id: [] for d in diffs}
    if diff_ids:
        for diff_id, artist in (
            await session.execute(
                select(DifficultyArtist.difficulty_id, Artist)
                .join(Artist, Artist.artist_id == DifficultyArtist.artist_id)
                .where(DifficultyArtist.difficulty_id.in_(diff_ids))
                .order_by(Artist.name)
            )
        ).all():
            diff_artists[diff_id].append(artist)
        for diff_id, charter in (
            await session.execute(
                select(DifficultyCharter.difficulty_id, Charter)
                .join(Charter, Charter.charter_id == DifficultyCharter.charter_id)
                .where(DifficultyCharter.difficulty_id.in_(diff_ids))
                .order_by(Charter.name)
            )
        ).all():
            diff_charters[diff_id].append(charter)

    linked_artists = (
        await session.scalars(
            select(Artist)
            .join(SongArtist, SongArtist.artist_id == Artist.artist_id)
            .where(SongArtist.song_id == song_id)
            .order_by(Artist.name)
        )
    ).all()
    linked_charters = (
        await session.scalars(
            select(Charter)
            .join(SongCharter, SongCharter.charter_id == Charter.charter_id)
            .where(SongCharter.song_id == song_id)
            .order_by(Charter.name)
        )
    ).all()
    all_artists = (await session.scalars(select(Artist).order_by(Artist.name))).all()
    all_charters = (await session.scalars(select(Charter).order_by(Charter.name))).all()
    packs = (await session.scalars(select(Pack).order_by(Pack.name))).all()

    # Tags: song-level list + per-chart lists (each ordered by label). Chips show
    # the slug tinted by the category color, with the category label on hover, so
    # every assigned tag carries its category's color + label.
    def _chip(tag: Tag, cat: TagCategory) -> dict:
        return {
            "id": tag.id,
            "slug": tag.slug,
            "label": tag.label,
            "color": cat.color,
            "cat_label": cat.label,
        }

    song_tags = [
        _chip(tag, cat)
        for tag, cat in (
            await session.execute(
                select(Tag, TagCategory)
                .join(SongTag, SongTag.tag_id == Tag.id)
                .join(TagCategory, TagCategory.id == Tag.category_id)
                .where(SongTag.song_id == song_id)
                .order_by(Tag.label)
            )
        ).all()
    ]
    diff_tags: dict[int, list] = {d.id: [] for d in diffs}
    if diff_ids:
        for diff_id, tag, cat in (
            await session.execute(
                select(DifficultyTag.difficulty_id, Tag, TagCategory)
                .join(Tag, Tag.id == DifficultyTag.tag_id)
                .join(TagCategory, TagCategory.id == Tag.category_id)
                .where(DifficultyTag.difficulty_id.in_(diff_ids))
                .order_by(Tag.label)
            )
        ).all():
            diff_tags[diff_id].append(_chip(tag, cat))

    existing = {d.difficulty for d in diffs}
    addable = [d for d in DIFFICULTY_ORDER if d not in existing]

    return templates.TemplateResponse(
        request,
        "song_detail.html",
        {
            "song": song,
            "diffs": diffs,
            "aliases": aliases,
            "auto_terms": auto_terms,
            "diff_aliases": diff_aliases,
            "diff_auto_terms": diff_auto_terms,
            "diff_artists": diff_artists,
            "diff_charters": diff_charters,
            "linked_artists": linked_artists,
            "linked_charters": linked_charters,
            "all_artists": all_artists,
            "all_charters": all_charters,
            "packs": packs,
            "addable": addable,
            "overridable": OVERRIDABLE_FIELDS,
            "error": error,
            "notice": notice,
            "song_tags": song_tags,
            "diff_tags": diff_tags,
            **(await _datalist_options(session)),
            **(await _entity_link_options(session)),
            **(await _tag_options(session)),
        },
    )


async def _move_idx(session: AsyncSession, song: Song, new_idx: int) -> str:
    """Move ``song`` to ``new_idx``. If taken, shift the occupied run starting at
    ``new_idx`` up by one (cascading until a gap) to make room. Returns a warning
    string when a shift happened, else "". ``idx`` is UNIQUE, so the moving song is
    first parked at a free negative idx and the run is shifted top-down."""
    park = ((await session.scalar(select(func.min(Song.idx)))) or 0) - 1
    await session.execute(
        update(Song).where(Song.song_id == song.song_id).values(idx=park)
    )
    await session.flush()

    occupied = set((await session.scalars(select(Song.idx))).all())
    warning = ""
    if new_idx in occupied:
        free = new_idx
        while free in occupied:
            free += 1
        for i in range(free - 1, new_idx - 1, -1):
            await session.execute(
                update(Song).where(Song.idx == i).values(idx=i + 1)
            )
            await session.flush()
        warning = f"idx {new_idx} was taken — bumped that song and the ones after it up by 1."

    await session.execute(
        update(Song).where(Song.song_id == song.song_id).values(idx=new_idx)
    )
    await session.flush()
    await session.refresh(song)
    return warning


class DateConflict(Exception):
    """A chart's explicit date override holds a second the cascade needs."""


async def _plan_date_shift(
    session: AsyncSession, date: int, keep_song_id: str | None
) -> list[tuple[str, int]]:
    """``(song_id, new_date)`` moves needed to free ``date``, in cascade order.

    Walks the contiguous run of occupied seconds from ``date`` upward, giving
    each song the next free second and stopping at the first gap. Songs already
    sharing a second (the catalog holds such groups) are spread apart rather
    than moved on top of each other.
    """
    occupants = (
        await session.execute(
            select(Song.song_id, Song.date)
            .where(Song.date >= date, Song.song_id != (keep_song_id or ""))
            .order_by(Song.date, Song.song_id)
        )
    ).all()
    if not any(second == date for _, second in occupants):
        return []

    moves: list[tuple[str, int]] = []
    cursor = date
    for song_id, second in occupants:
        if second > cursor:
            break
        cursor += 1
        moves.append((song_id, cursor))
    return moves


async def _reserve_date(
    session: AsyncSession, date: int, keep_song_id: str | None
) -> str:
    """Make ``date`` free for the song being saved, shifting incumbents up.

    Mirrors :func:`_move_idx`: the saved song keeps the second it asked for and
    the incumbents move, so a value is never silently changed out from under the
    operator. ``songs.date`` has no UNIQUE constraint (unlike ``idx``), so no
    parking step is needed.

    Raises :class:`DateConflict` if the target second, or any second the cascade
    would move a song onto, is held by a chart's explicit date override. Those
    are deliberate placements and auto-moving one would silently undo an
    intentional decision; charts that inherit (``date IS NULL``) resolve to their
    song's second by construction and cannot collide.
    """
    moves = await _plan_date_shift(session, date, keep_song_id)
    highest = moves[-1][1] if moves else date

    blocking = (
        await session.execute(
            select(SongDifficulty.song_id, SongDifficulty.difficulty)
            .where(SongDifficulty.date.between(date, highest))
        )
    ).all()
    if blocking:
        names = ", ".join(f"{sid} {diff.value}" for sid, diff in blocking)
        raise DateConflict(
            f"second {date} is held by a chart's own date override ({names}). "
            "Change that chart's date first."
        )

    if not moves:
        return ""
    for song_id, new_date in moves:
        await session.execute(
            update(Song).where(Song.song_id == song_id).values(date=new_date)
        )
    await session.flush()
    return (
        f"date {date} was taken — shifted "
        f"{', '.join(song_id for song_id, _ in moves)} up to make room."
    )


@router.post("/songs/{song_id}", response_class=HTMLResponse, response_model=None)
async def update_song(
    request: Request, song_id: str, session: AsyncSession = Depends(get_session)
) -> HTMLResponse | RedirectResponse:
    song = await session.get(Song, song_id)
    if song is None:
        return HTMLResponse("Song not found", status_code=404)

    form = await request.form()

    # idx is editable; a collision shifts the occupant(s) up rather than erroring.
    notice = ""
    idx_raw = form_text(form, "idx").strip()
    if idx_raw:
        try:
            new_idx = int(idx_raw)
        except ValueError:
            new_idx = song.idx
        if new_idx != song.idx:
            notice = await _move_idx(session, song, new_idx)

    old_name_en, old_name_jp = song.name_en, song.name_jp
    fields = parse_song_base(form)
    if fields["date"] and fields["date"] != song.date:
        try:
            shifted = await _reserve_date(session, fields["date"], song.song_id)
        except DateConflict as exc:
            await session.rollback()
            return RedirectResponse(
                f"/songs/{song_id}?error={quote(str(exc))}", status_code=303
            )
        notice = " ".join(filter(None, (notice, shifted)))
    for key, value in fields.items():
        setattr(song, key, value)
    await aliassync.sync_song(
        session, song_id,
        old_name_en=old_name_en, old_name_jp=old_name_jp,
        new_name_en=song.name_en, new_name_jp=song.name_jp,
    )
    await session.commit()
    url = f"/songs/{song_id}"
    if notice:
        url += f"?notice={quote(notice)}"
    return RedirectResponse(url=url, status_code=303)


@router.post("/songs/{song_id}/rename")
async def rename_song(
    request: Request, song_id: str, session: AsyncSession = Depends(get_session)
):
    """Change a song's primary key. The child FKs cascade (see migration
    66ad9752c1d2), so difficulties/links/aliases follow automatically. The only
    manual fixup is the song_id string that lives as its own alias term."""
    song = await session.get(Song, song_id)
    if song is None:
        return HTMLResponse("Song not found", status_code=404)
    form = await request.form()
    new_id = form_text(form, "new_id").strip()

    def _err(msg: str) -> RedirectResponse:
        return RedirectResponse(f"/songs/{song_id}?error={quote(msg)}", status_code=303)

    if not new_id:
        return _err("New song_id is required.")
    if new_id == song_id:
        return _err("New song_id is unchanged.")
    if await session.get(Song, new_id):
        return _err(f"song_id {new_id!r} already exists.")

    await session.execute(
        update(Song).where(Song.song_id == song_id).values(song_id=new_id)
    )
    # The old id was an auto alias term; swap it for the new id.
    await session.execute(
        delete(SongAlias).where(SongAlias.song_id == new_id, SongAlias.alias == song_id)
    )
    await session.execute(
        pg_insert(SongAlias)
        .values([{"song_id": new_id, "alias": new_id}])
        .on_conflict_do_nothing(index_elements=["song_id", "alias"])
    )
    await session.commit()
    return RedirectResponse(url=f"/songs/{new_id}", status_code=303)


@router.post("/songs/{song_id}/delete")
async def delete_song(
    song_id: str, session: AsyncSession = Depends(get_session)
) -> RedirectResponse:
    # Children first (no ON DELETE CASCADE declared). difficulty_aliases hang off
    # song_difficulties, so clear them before the difficulties.
    diff_ids = (
        await session.scalars(
            select(SongDifficulty.id).where(SongDifficulty.song_id == song_id)
        )
    ).all()
    if diff_ids:
        await session.execute(
            delete(DifficultyAlias).where(DifficultyAlias.difficulty_id.in_(diff_ids))
        )
        await session.execute(
            delete(DifficultyArtist).where(DifficultyArtist.difficulty_id.in_(diff_ids))
        )
        await session.execute(
            delete(DifficultyCharter).where(DifficultyCharter.difficulty_id.in_(diff_ids))
        )
    await session.execute(
        delete(SongDifficulty).where(SongDifficulty.song_id == song_id)
    )
    await session.execute(delete(SongArtist).where(SongArtist.song_id == song_id))
    await session.execute(delete(SongCharter).where(SongCharter.song_id == song_id))
    await session.execute(delete(SongAlias).where(SongAlias.song_id == song_id))
    await session.execute(delete(Song).where(Song.song_id == song_id))
    await session.commit()
    return RedirectResponse(url="/songs", status_code=303)
