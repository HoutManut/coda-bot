"""Tag vocabulary CRUD and song/chart tag assignment.

Two surfaces:

* ``/tags`` — manage the vocabulary: categories and the tags under them.
* ``/tags/assign/...`` — link/unlink a tag on a song or chart. The picker shows
  only a tag field: picking an existing label links it immediately. Typing a
  brand-new label reveals a category field (its own datalist); the tag is then
  created under that category, auto-creating the category if it is new too. An
  existing label always links the existing tag and **ignores** ``category`` —
  this picker cannot recategorize; that is the ``/tags`` page's job.
"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from coda.admin.deps import get_session
from coda.admin.forms import form_text
from coda.admin.presenters import seed_category_color
from coda.admin.templating import templates
from coda.catalog.slug import slugify
from coda.db.models import (
    DifficultyTag,
    Song,
    SongDifficulty,
    SongTag,
    Tag,
    TagCategory,
)

router = APIRouter(prefix="/tags")

# assign target -> (join model, fk column, fk python type)
_TARGETS = {
    "song": (SongTag, "song_id", str),
    "difficulty": (DifficultyTag, "difficulty_id", int),
}


def _redirect(url: str, error: str = "") -> RedirectResponse:
    if error:
        # Splice the query *before* any "#anchor" — a query after the fragment is
        # part of the fragment, so the error would never be parsed (and the
        # anchor would break, jumping the page to the top).
        base, _, frag = url.partition("#")
        sep = "&" if "?" in base else "?"
        url = f"{base}{sep}error={quote(error)}" + (f"#{frag}" if frag else "")
    return RedirectResponse(url, status_code=303)


# ── vocabulary page ─────────────────────────────────────────────────────────


@router.get("", response_class=HTMLResponse)
async def vocab(
    request: Request, session: AsyncSession = Depends(get_session)
) -> HTMLResponse:
    categories = (
        await session.scalars(
            select(TagCategory).order_by(TagCategory.sort, TagCategory.label)
        )
    ).all()
    tags = (await session.scalars(select(Tag).order_by(Tag.label))).all()
    # usage counts so the page can warn before deleting a tag that is in use.
    song_counts = {
        tag_id: count
        for tag_id, count in (
            await session.execute(
                select(SongTag.tag_id, func.count()).group_by(SongTag.tag_id)
            )
        ).all()
    }
    diff_counts = {
        tag_id: count
        for tag_id, count in (
            await session.execute(
                select(DifficultyTag.tag_id, func.count()).group_by(DifficultyTag.tag_id)
            )
        ).all()
    }
    tags_by_cat: dict[int, list] = {c.id: [] for c in categories}
    for t in tags:
        tags_by_cat.setdefault(t.category_id, []).append(
            {"tag": t, "uses": song_counts.get(t.id, 0) + diff_counts.get(t.id, 0)}
        )
    return templates.TemplateResponse(
        request,
        "tag_vocab.html",
        {
            "categories": categories,
            "tags_by_cat": tags_by_cat,
            "error": request.query_params.get("error", ""),
        },
    )


@router.post("/categories")
async def create_category(
    label: str = Form(...),
    sort: int = Form(0),
    color: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    label = label.strip()
    slug = slugify(label) or label.lower()
    if not slug:
        return _redirect("/tags", "Category label is required.")
    if await session.scalar(select(TagCategory).where(TagCategory.slug == slug)):
        return _redirect("/tags", f"Category {slug!r} already exists.")
    session.add(
        TagCategory(
            slug=slug,
            label=label,
            sort=sort,
            color=color.strip() or seed_category_color(slug),
        )
    )
    await session.commit()
    return _redirect("/tags")


@router.post("/categories/reorder")
async def reorder_categories(
    request: Request, session: AsyncSession = Depends(get_session)
):
    """Persist drag-reordered category order. ``order`` is a comma-joined list of
    category ids in their new on-screen order; each row's ``sort`` is set to its
    index so the page's ``ORDER BY sort`` reflects the drag."""
    form = await request.form()
    ids = [int(x) for x in form_text(form, "order").split(",") if x.strip()]
    for i, cid in enumerate(ids):
        await session.execute(
            update(TagCategory).where(TagCategory.id == cid).values(sort=i)
        )
    await session.commit()
    return _redirect("/tags")


@router.post("/categories/{cid}")
async def update_category(
    cid: int, request: Request, session: AsyncSession = Depends(get_session)
):
    """Inline edits from the category card header: label, slug, and/or color.
    Each field submits on its own, so only the keys present in the form are
    touched. ``slug`` is re-slugified to match the create path's normalization."""
    cat = await session.get(TagCategory, cid)
    if cat is None:
        return _redirect("/tags", "Category not found.")
    form = await request.form()
    if "label" in form:
        label = form_text(form, "label").strip()
        if not label:
            return _redirect("/tags", "Category label is required.")
        cat.label = label
    if "slug" in form:
        slug = slugify(form_text(form, "slug"))
        if not slug:
            return _redirect("/tags", "Category slug is required.")
        clash = await session.scalar(
            select(TagCategory).where(TagCategory.slug == slug, TagCategory.id != cid)
        )
        if clash:
            return _redirect("/tags", f"Category {slug!r} already exists.")
        cat.slug = slug
    if "color" in form:
        cat.color = form_text(form, "color").strip() or None
    await session.commit()
    return _redirect("/tags")


@router.post("/categories/{cid}/delete")
async def delete_category(cid: int, session: AsyncSession = Depends(get_session)):
    # Tag.category_id ON DELETE CASCADE removes the tags; their join rows cascade
    # in turn. Destructive by design (early dev).
    await session.execute(delete(TagCategory).where(TagCategory.id == cid))
    await session.commit()
    return _redirect("/tags")


@router.post("/items")
async def create_tag(
    label: str = Form(...),
    category_id: int = Form(...),
    description: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    label = label.strip()
    slug = slugify(label) or label.lower()
    if not slug:
        return _redirect("/tags", "Tag label is required.")
    if await session.scalar(select(Tag).where(Tag.slug == slug)):
        return _redirect("/tags", f"Tag {slug!r} already exists.")
    session.add(
        Tag(
            slug=slug,
            label=label,
            category_id=category_id,
            description=(description.strip() or None),
        )
    )
    await session.commit()
    return _redirect("/tags")


@router.post("/items/{tid}")
async def edit_tag(
    tid: int,
    label: str = Form(...),
    category_id: int = Form(...),
    description: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    tag = await session.get(Tag, tid)
    if tag is None:
        return _redirect("/tags", "Tag not found.")
    label = label.strip()
    slug = slugify(label) or label.lower()
    clash = await session.scalar(
        select(Tag).where(Tag.slug == slug, Tag.id != tid)
    )
    if clash:
        return _redirect(f"/tags/{tid}", f"Tag {slug!r} already exists.")
    tag.slug, tag.label, tag.category_id = slug, label, category_id
    tag.description = description.strip() or None
    await session.commit()
    return _redirect(f"/tags/{tid}")


@router.post("/items/{tid}/relabel")
async def relabel_tag(
    tid: int, label: str = Form(...), session: AsyncSession = Depends(get_session)
):
    """Inline label edit from a pill (edit mode). Re-slugifies like the create
    path; the slug stays in lockstep with the label. Redirects to the vocab page."""
    tag = await session.get(Tag, tid)
    if tag is None:
        return _redirect("/tags", "Tag not found.")
    label = label.strip()
    slug = slugify(label) or label.lower()
    if not slug:
        return _redirect("/tags", "Tag label is required.")
    clash = await session.scalar(select(Tag).where(Tag.slug == slug, Tag.id != tid))
    if clash:
        return _redirect("/tags", f"Tag {slug!r} already exists.")
    tag.label, tag.slug = label, slug
    await session.commit()
    return _redirect("/tags")


@router.post("/items/{tid}/move")
async def move_tag(
    tid: int, category_id: int = Form(...), session: AsyncSession = Depends(get_session)
):
    """Recategorize a tag by dragging its pill onto another category card."""
    tag = await session.get(Tag, tid)
    if tag is None:
        return _redirect("/tags", "Tag not found.")
    if await session.get(TagCategory, category_id) is None:
        return _redirect("/tags", "Category not found.")
    tag.category_id = category_id
    await session.commit()
    return _redirect("/tags")


@router.post("/items/{tid}/delete")
async def delete_tag(tid: int, session: AsyncSession = Depends(get_session)):
    await session.execute(delete(Tag).where(Tag.id == tid))
    await session.commit()
    return _redirect("/tags")


@router.get("/{tid}", response_class=HTMLResponse)
async def tag_detail(
    tid: int, request: Request, session: AsyncSession = Depends(get_session)
) -> HTMLResponse:
    """Full tag page: edit (label/slug/category/description), delete, and the
    songs + charts the tag is assigned to. Mirrors the entity detail layout."""
    row = (
        await session.execute(
            select(Tag, TagCategory)
            .join(TagCategory, TagCategory.id == Tag.category_id)
            .where(Tag.id == tid)
        )
    ).first()
    if row is None:
        return HTMLResponse("Not found", status_code=404)
    tag, cat = row
    categories = (
        await session.scalars(
            select(TagCategory).order_by(TagCategory.sort, TagCategory.label)
        )
    ).all()
    # Songs carrying this tag (song-level assignment).
    songs = (
        await session.execute(
            select(Song.song_id, Song.name_en, Song.idx)
            .join(SongTag, SongTag.song_id == Song.song_id)
            .where(SongTag.tag_id == tid)
            .order_by(Song.idx)
        )
    ).all()
    # Charts carrying this tag (per-chart assignment); show the chart's effective
    # name and its difficulty so a remix BYD is distinguishable from its song.
    charts = (
        await session.execute(
            select(
                SongDifficulty.id,
                SongDifficulty.song_id,
                SongDifficulty.difficulty,
                func.coalesce(SongDifficulty.name_en, Song.name_en).label("name"),
                Song.idx,
            )
            .join(DifficultyTag, DifficultyTag.difficulty_id == SongDifficulty.id)
            .join(Song, Song.song_id == SongDifficulty.song_id)
            .where(DifficultyTag.tag_id == tid)
            .order_by(Song.idx)
        )
    ).all()
    return templates.TemplateResponse(
        request,
        "tag_detail.html",
        {
            "tag": tag,
            "cat": cat,
            "categories": categories,
            "songs": songs,
            "charts": charts,
            "error": request.query_params.get("error", ""),
        },
    )


# ── assignment on a song / chart ─────────────────────────────────────────────


async def _back_url(target: str, fk, session: AsyncSession) -> str:
    if target == "song":
        return f"/songs/{fk}#tags"
    diff = await session.get(SongDifficulty, fk)
    return f"/songs/{diff.song_id}#chart-{fk}" if diff else "/songs"


@router.post("/assign/{target}/{fk}/add")
async def add_tag(
    target: str,
    fk: str,
    tag: str = Form(...),
    category: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    if target not in _TARGETS:
        return HTMLResponse("Unknown target", status_code=404)
    join, fk_col, fk_type = _TARGETS[target]
    fk_val = fk_type(fk)

    label = tag.strip()
    if not label:
        return _redirect(await _back_url(target, fk_val, session))
    slug = slugify(label) or label.lower()

    row = await session.scalar(select(Tag).where(Tag.slug == slug))
    if row is None:
        # New label → create the tag under the given category, resolving an
        # existing category by slug or auto-creating one (seeded color). An
        # existing tag links as-is and ignores ``category`` (no recategorize).
        cat_label = category.strip()
        if not cat_label:
            return _redirect(
                await _back_url(target, fk_val, session),
                f"Tag {label!r} is new — enter a category to create it.",
            )
        cat_slug = slugify(cat_label) or cat_label.lower()
        # The category field suggests existing *labels*, whose slug may be a
        # custom value (e.g. "Pattern" → slug "pat"). Match the label first so
        # picking an existing category links it instead of creating a duplicate;
        # fall back to slug, then create.
        cat = await session.scalar(
            select(TagCategory).where(
                func.lower(TagCategory.label) == cat_label.lower()
            )
        ) or await session.scalar(
            select(TagCategory).where(TagCategory.slug == cat_slug)
        )
        if cat is None:
            cat = TagCategory(
                slug=cat_slug,
                label=cat_label,
                color=seed_category_color(cat_slug),
            )
            session.add(cat)
            await session.flush()
        row = Tag(slug=slug, label=label, category_id=cat.id)
        session.add(row)
        await session.flush()

    await session.execute(
        pg_insert(join)
        .values([{fk_col: fk_val, "tag_id": row.id}])
        .on_conflict_do_nothing(index_elements=[fk_col, "tag_id"])
    )
    await session.commit()
    return _redirect(await _back_url(target, fk_val, session))


@router.post("/assign/{target}/{fk}/remove")
async def remove_tag(
    target: str,
    fk: str,
    tag_id: int = Form(...),
    session: AsyncSession = Depends(get_session),
):
    if target not in _TARGETS:
        return HTMLResponse("Unknown target", status_code=404)
    join, fk_col, fk_type = _TARGETS[target]
    fk_val = fk_type(fk)
    await session.execute(
        delete(join).where(
            getattr(join, fk_col) == fk_val, join.tag_id == tag_id
        )
    )
    await session.commit()
    return _redirect(await _back_url(target, fk_val, session))
