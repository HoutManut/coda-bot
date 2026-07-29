"""Artists, charters, packs: CRUD, song linking, and destructive merge.

Artists and charters share one shape (id + name + aliases + a song junction), so
their routes are registered from a small spec in a loop. Packs carry their own
metadata columns and get explicit routes.

Merge is destructive (acceptable in early dev): it repoints the source's song
links onto the target, folds the source id+name and its alias rows into the
target's aliases, then deletes the source row.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from coda.admin import aliassync
from coda.admin.deps import get_session
from coda.admin.listing import paginate
from coda.admin.presenters import display_date, parse_date
from coda.admin.templating import templates
from coda.catalog.aliases import entity_alias_terms
from coda.db.enums import ArtistKind
from coda.db.models import (
    Artist,
    ArtistAlias,
    ArtistMember,
    Charter,
    CharterAlias,
    DifficultyArtist,
    DifficultyCharter,
    Pack,
    Song,
    SongArtist,
    SongCharter,
    SongDifficulty,
)

router = APIRouter()


@dataclass(frozen=True)
class _Spec:
    kind: str             # url segment + template noun, e.g. "artists"
    entity: type          # Artist / Charter
    alias_model: type     # ArtistAlias / CharterAlias
    junction: type        # SongArtist / SongCharter
    diff_junction: type   # DifficultyArtist / DifficultyCharter
    id_col: str           # "artist_id" / "charter_id"
    sync: Callable        # aliassync.sync_artist / sync_charter
    has_kind: bool = False  # artists carry a person/unit kind + members; charters don't


_SPECS = {
    "artists": _Spec("artists", Artist, ArtistAlias, SongArtist, DifficultyArtist, "artist_id", aliassync.sync_artist, has_kind=True),
    "charters": _Spec("charters", Charter, CharterAlias, SongCharter, DifficultyCharter, "charter_id", aliassync.sync_charter),
}


def _redirect(url: str, error: str = "") -> RedirectResponse:
    if error:
        url += ("&" if "?" in url else "?") + f"error={quote(error)}"
    return RedirectResponse(url, status_code=303)


async def _list(spec: _Spec, request: Request, session: AsyncSession) -> HTMLResponse:
    q = (request.query_params.get("q") or "").strip()
    id_col = getattr(spec.entity, spec.id_col)
    base = select(spec.entity)
    if q:
        base = (
            base.join(spec.alias_model, getattr(spec.alias_model, spec.id_col) == id_col)
            .where(spec.alias_model.alias.ilike(f"%{q}%"))
            .distinct()
        )
    page = await paginate(
        session, base, request=request,
        columns={"id": id_col, "name": spec.entity.name},
        default_sort="name", path=f"/{spec.kind}", q=q,
    )
    return templates.TemplateResponse(
        request, "entity_list.html",
        {"kind": spec.kind, "id_col": spec.id_col, "page": page},
    )


async def _detail(
    spec: _Spec, request: Request, eid: str, session: AsyncSession
) -> HTMLResponse:
    entity = await session.get(spec.entity, eid)
    if entity is None:
        return HTMLResponse("Not found", status_code=404)
    aliases = (
        await session.scalars(
            select(spec.alias_model)
            .where(getattr(spec.alias_model, spec.id_col) == eid)
            .order_by(spec.alias_model.alias)
        )
    ).all()
    songs = (
        await session.scalars(
            select(Song)
            .join(spec.junction, spec.junction.song_id == Song.song_id)
            .where(getattr(spec.junction, spec.id_col) == eid)
            .order_by(Song.idx)
        )
    ).all()
    others = (
        await session.scalars(
            select(spec.entity)
            .where(getattr(spec.entity, spec.id_col) != eid)
            .order_by(spec.entity.name)
        )
    ).all()
    # Per-chart credits: charts whose artist/charter set is overridden to include
    # this entity (e.g. a remix difficulty credited to a different artist). The
    # chart may override name_en, so show its effective name. Works for both
    # artists and charters via the spec's per-difficulty junction.
    chart_rows = (
        await session.execute(
            select(SongDifficulty, Song.name_en, Song.idx, func.coalesce(SongDifficulty.date, Song.date))
            .join(spec.diff_junction, spec.diff_junction.difficulty_id == SongDifficulty.id)
            .join(Song, Song.song_id == SongDifficulty.song_id)
            .where(getattr(spec.diff_junction, spec.id_col) == eid)
            .order_by(Song.idx)
        )
    ).all()
    chart_credits = [
        {
            "song_id": d.song_id,
            "difficulty_id": d.id,
            "difficulty": d.difficulty,
            "name": d.name_en or song_name,
            "as_name": None,
            "idx": idx,
            "date": date,
        }
        for d, song_name, idx, date in chart_rows
    ]

    # Charter-only: resolve the specific charts this charter is responsible for,
    # following the song-link → per-chart override inheritance. A chart credits
    # this charter when it inherits (charters_overridden = False) and the song is
    # linked, or it overrides (charters_overridden = True) and its own set names
    # this charter. The two sets are disjoint by the override flag, so union_all.
    # Grouped by song and rendered as difficulty badges.
    responsible_songs: list[dict] = []
    if spec.kind == "charters":
        rdate = func.coalesce(SongDifficulty.date, Song.date)
        cols = (Song.song_id, Song.name_en, Song.idx, rdate, SongDifficulty.difficulty)
        inherited = (
            select(*cols)
            .join(SongDifficulty, SongDifficulty.song_id == Song.song_id)
            .join(spec.junction, spec.junction.song_id == Song.song_id)
            .where(
                getattr(spec.junction, spec.id_col) == eid,
                SongDifficulty.charters_overridden.is_(False),
            )
        )
        overridden = (
            select(*cols)
            .join(SongDifficulty, SongDifficulty.song_id == Song.song_id)
            .join(spec.diff_junction, spec.diff_junction.difficulty_id == SongDifficulty.id)
            .where(
                getattr(spec.diff_junction, spec.id_col) == eid,
                SongDifficulty.charters_overridden.is_(True),
            )
        )
        rows = (await session.execute(inherited.union_all(overridden))).all()
        # Key by (song, resolved date): charts of one song that release on
        # different dates (e.g. a later BYD) split into separate rows.
        groups: dict[tuple, dict] = {}
        for song_id, name_en, idx, date, difficulty in rows:
            g = groups.setdefault(
                (song_id, date),
                {"song_id": song_id, "name": name_en, "idx": idx, "date": date, "diffs": set()},
            )
            g["diffs"].add(difficulty)
        # Total chart count per involved song — to drop the badges when the
        # charter covers the whole song (full credit needs no per-chart detail).
        totals = dict(
            (
                await session.execute(
                    select(SongDifficulty.song_id, func.count())
                    .where(SongDifficulty.song_id.in_({sid for sid, _ in groups}))
                    .group_by(SongDifficulty.song_id)
                )
            ).all()
        ) if groups else {}
        responsible_songs = sorted(groups.values(), key=lambda g: (g["idx"], g["date"]))
        for g in responsible_songs:
            g["total"] = totals.get(g["song_id"], 0)
            # A single (non-split) group covering the whole song needs no badges.
            # The merged idx/name view drops them client-side via data-total too.
            full = len(g["diffs"]) >= g["total"]
            g["diffs"] = [] if full else sorted(
                g["diffs"], key=lambda d: d.ordinal if d.ordinal is not None else 99
            )

    members = []
    part_of = []
    via_songs = []
    if spec.has_kind:
        members = (
            await session.scalars(
                select(Artist)
                .join(ArtistMember, ArtistMember.member_id == Artist.artist_id)
                .where(ArtistMember.group_id == eid)
                .order_by(Artist.name)
            )
        ).all()
        # Reverse edges: units this artist is a member of.
        part_of = (
            await session.scalars(
                select(Artist)
                .join(ArtistMember, ArtistMember.group_id == Artist.artist_id)
                .where(ArtistMember.member_id == eid)
                .order_by(Artist.name)
            )
        ).all()
        # Songs credited to those units — shown in the artist's own song list as
        # "(as <unit>)". Skip songs the artist is already directly credited on.
        if part_of:
            direct_ids = {s.song_id for s in songs}
            rows = (
                await session.execute(
                    select(Song, Artist.name)
                    .join(SongArtist, SongArtist.song_id == Song.song_id)
                    .join(Artist, Artist.artist_id == SongArtist.artist_id)
                    .where(SongArtist.artist_id.in_([u.artist_id for u in part_of]))
                    .order_by(Song.idx)
                )
            ).all()
            via_songs = [
                {"song": s, "as_name": n} for s, n in rows if s.song_id not in direct_ids
            ]
            # Same idea at chart granularity: remix charts credited to those units.
            direct_chart_ids = {c["difficulty_id"] for c in chart_credits}
            crows = (
                await session.execute(
                    select(SongDifficulty, Song.name_en, Song.idx, func.coalesce(SongDifficulty.date, Song.date), Artist.name)
                    .join(DifficultyArtist, DifficultyArtist.difficulty_id == SongDifficulty.id)
                    .join(Song, Song.song_id == SongDifficulty.song_id)
                    .join(Artist, Artist.artist_id == DifficultyArtist.artist_id)
                    .where(DifficultyArtist.artist_id.in_([u.artist_id for u in part_of]))
                    .order_by(Song.idx)
                )
            ).all()
            chart_credits += [
                {
                    "song_id": d.song_id,
                    "difficulty_id": d.id,
                    "difficulty": d.difficulty,
                    "name": d.name_en or song_name,
                    "as_name": uname,
                    "idx": idx,
                    "date": date,
                }
                for d, song_name, idx, date, uname in crows
                if d.id not in direct_chart_ids
            ]
    # Non-charter (artist) song list: flatten direct songs, via-unit songs, and
    # per-chart credits into one list ordered by Song.idx (not grouped by type).
    entries: list[dict] = []
    if spec.kind != "charters":
        for s in songs:
            entries.append(
                {"idx": s.idx, "date": s.date, "song_id": s.song_id, "name": s.name_en,
                 "note": None, "difficulty": None, "difficulty_id": None}
            )
        for vs in via_songs:
            s = vs["song"]
            entries.append(
                {"idx": s.idx, "date": s.date, "song_id": s.song_id, "name": s.name_en,
                 "note": f"as {vs['as_name']}", "difficulty": None, "difficulty_id": None}
            )
        for c in chart_credits:
            note = f"as {c['as_name']}" if c["as_name"] else None
            entries.append(
                {"idx": c["idx"], "date": c["date"], "song_id": c["song_id"], "name": c["name"],
                 "note": note, "difficulty": c["difficulty"], "difficulty_id": c["difficulty_id"]}
            )
        entries.sort(key=lambda e: e["idx"])

    return templates.TemplateResponse(
        request, "entity_detail.html",
        {
            "kind": spec.kind,
            "id_col": spec.id_col,
            "has_kind": spec.has_kind,
            "entity": entity,
            "eid": eid,
            "aliases": aliases,
            "auto_terms": entity_alias_terms(eid, entity.name),
            "songs": songs,
            "others": others,
            "members": members,
            "part_of": part_of,
            "via_songs": via_songs,
            "chart_credits": chart_credits,
            "responsible_songs": responsible_songs,
            "entries": entries,
            "error": request.query_params.get("error", ""),
        },
    )


async def _create(spec: _Spec, request: Request, session: AsyncSession) -> RedirectResponse:
    form = await request.form()
    eid = (form.get("id") or "").strip()
    name = (form.get("name") or "").strip()
    if not eid or not name:
        return _redirect(f"/{spec.kind}", "id and name are required.")
    if await session.get(spec.entity, eid):
        return _redirect(f"/{spec.kind}", f"{eid} already exists.")
    session.add(spec.entity(**{spec.id_col: eid, "name": name}))
    await session.flush()
    await spec.sync(session, eid, new_name=name)
    await session.commit()
    return _redirect(f"/{spec.kind}/{eid}")


async def _update(spec: _Spec, request: Request, eid: str, session: AsyncSession) -> RedirectResponse:
    entity = await session.get(spec.entity, eid)
    if entity is None:
        return _redirect(f"/{spec.kind}", "not found.")
    form = await request.form()
    old_name = entity.name
    entity.name = (form.get("name") or "").strip()
    if spec.has_kind:
        # Checkbox: present (any value) = unit, absent = person.
        entity.kind = ArtistKind.UNIT if form.get("kind") else ArtistKind.PERSON
    await spec.sync(session, eid, old_name=old_name, new_name=entity.name)
    await session.commit()
    return _redirect(f"/{spec.kind}/{eid}")


async def _rename(spec: _Spec, request: Request, eid: str, session: AsyncSession) -> RedirectResponse:
    """Change an artist/charter primary key. The child FKs cascade on update (see
    migration b3f1c2d4e5a6), so links and alias rows follow automatically. The
    only manual fixup is the id string that lives as its own auto alias term."""
    entity = await session.get(spec.entity, eid)
    if entity is None:
        return _redirect(f"/{spec.kind}", "not found.")
    form = await request.form()
    new_id = (form.get("new_id") or "").strip()
    if not new_id:
        return _redirect(f"/{spec.kind}/{eid}", "New id is required.")
    if new_id == eid:
        return _redirect(f"/{spec.kind}/{eid}", "New id is unchanged.")
    if await session.get(spec.entity, new_id):
        return _redirect(f"/{spec.kind}/{eid}", f"{new_id} already exists.")

    await session.execute(
        update(spec.entity).where(getattr(spec.entity, spec.id_col) == eid).values(**{spec.id_col: new_id})
    )
    # The old id was an auto alias term; swap it for the new id (the alias rows
    # themselves were already repointed to new_id by the FK cascade).
    alias_id_col = getattr(spec.alias_model, spec.id_col)
    await session.execute(
        delete(spec.alias_model).where(alias_id_col == new_id, spec.alias_model.alias == eid)
    )
    await session.execute(
        pg_insert(spec.alias_model)
        .values([{spec.id_col: new_id, "alias": new_id}])
        .on_conflict_do_nothing(index_elements=[spec.id_col, "alias"])
    )
    await session.commit()
    return _redirect(f"/{spec.kind}/{new_id}")


async def _delete(spec: _Spec, eid: str, session: AsyncSession) -> RedirectResponse:
    await session.execute(delete(spec.junction).where(getattr(spec.junction, spec.id_col) == eid))
    await session.execute(delete(spec.diff_junction).where(getattr(spec.diff_junction, spec.id_col) == eid))
    await session.execute(delete(spec.alias_model).where(getattr(spec.alias_model, spec.id_col) == eid))
    if spec.has_kind:
        # Drop membership edges in both directions (no ondelete cascade on the FK).
        await session.execute(
            delete(ArtistMember).where(
                (ArtistMember.group_id == eid) | (ArtistMember.member_id == eid)
            )
        )
    await session.execute(delete(spec.entity).where(getattr(spec.entity, spec.id_col) == eid))
    await session.commit()
    return _redirect(f"/{spec.kind}")


async def _merge(spec: _Spec, request: Request, eid: str, session: AsyncSession) -> RedirectResponse:
    """Fold source ``eid`` into the target id from the form."""
    form = await request.form()
    target = (form.get("target") or "").strip()
    if not target or target == eid:
        return _redirect(f"/{spec.kind}/{eid}", "pick a different target to merge into.")
    src = await session.get(spec.entity, eid)
    tgt = await session.get(spec.entity, target)
    if src is None or tgt is None:
        return _redirect(f"/{spec.kind}/{eid}", "source or target missing.")

    id_attr = getattr(spec.junction, spec.id_col)
    # 1. Repoint song links; the target may already link some of those songs.
    src_song_ids = set(
        (await session.scalars(select(spec.junction.song_id).where(id_attr == eid))).all()
    )
    await session.execute(delete(spec.junction).where(id_attr == eid))
    if src_song_ids:
        stmt = pg_insert(spec.junction).values(
            [{"song_id": s, spec.id_col: target} for s in src_song_ids]
        )
        await session.execute(
            stmt.on_conflict_do_nothing(index_elements=["song_id", spec.id_col])
        )

    # 1b. Same for per-chart links.
    dj_attr = getattr(spec.diff_junction, spec.id_col)
    src_diff_ids = set(
        (await session.scalars(select(spec.diff_junction.difficulty_id).where(dj_attr == eid))).all()
    )
    await session.execute(delete(spec.diff_junction).where(dj_attr == eid))
    if src_diff_ids:
        stmt = pg_insert(spec.diff_junction).values(
            [{"difficulty_id": d, spec.id_col: target} for d in src_diff_ids]
        )
        await session.execute(
            stmt.on_conflict_do_nothing(index_elements=["difficulty_id", spec.id_col])
        )

    # 2 & 3. Fold source id+name and the source's own alias rows into the target.
    terms = entity_alias_terms(eid, src.name)
    terms |= set(
        (
            await session.scalars(
                select(spec.alias_model.alias).where(getattr(spec.alias_model, spec.id_col) == eid)
            )
        ).all()
    )
    await session.execute(delete(spec.alias_model).where(getattr(spec.alias_model, spec.id_col) == eid))
    if terms:
        stmt = pg_insert(spec.alias_model).values(
            [{spec.id_col: target, "alias": t} for t in terms]
        )
        await session.execute(
            stmt.on_conflict_do_nothing(index_elements=[spec.id_col, "alias"])
        )

    # 3b. Repoint membership edges (artists only), dropping any self-edge the
    # merge would create, then de-duping against the target's existing edges.
    if spec.has_kind:
        as_group = set(
            (await session.scalars(select(ArtistMember.member_id).where(ArtistMember.group_id == eid))).all()
        )
        as_member = set(
            (await session.scalars(select(ArtistMember.group_id).where(ArtistMember.member_id == eid))).all()
        )
        await session.execute(
            delete(ArtistMember).where(
                (ArtistMember.group_id == eid) | (ArtistMember.member_id == eid)
            )
        )
        edges = [{"group_id": target, "member_id": m} for m in as_group if m != target]
        edges += [{"group_id": g, "member_id": target} for g in as_member if g != target]
        if edges:
            await session.execute(
                pg_insert(ArtistMember).values(edges).on_conflict_do_nothing(
                    index_elements=["group_id", "member_id"]
                )
            )

    # 4. Drop the now-empty source entity.
    await session.execute(delete(spec.entity).where(getattr(spec.entity, spec.id_col) == eid))
    await session.commit()
    return _redirect(f"/{spec.kind}/{target}")


# Register artist/charter routes from the spec (closures bind their spec).
def _register(spec: _Spec) -> None:
    p = f"/{spec.kind}"

    async def lst(request: Request, session: AsyncSession = Depends(get_session), _s=spec):
        return await _list(_s, request, session)

    async def create(request: Request, session: AsyncSession = Depends(get_session), _s=spec):
        return await _create(_s, request, session)

    async def detail(eid: str, request: Request, session: AsyncSession = Depends(get_session), _s=spec):
        return await _detail(_s, request, eid, session)

    async def update(eid: str, request: Request, session: AsyncSession = Depends(get_session), _s=spec):
        return await _update(_s, request, eid, session)

    async def rename(eid: str, request: Request, session: AsyncSession = Depends(get_session), _s=spec):
        return await _rename(_s, request, eid, session)

    async def delete_(eid: str, session: AsyncSession = Depends(get_session), _s=spec):
        return await _delete(_s, eid, session)

    async def merge(eid: str, request: Request, session: AsyncSession = Depends(get_session), _s=spec):
        return await _merge(_s, request, eid, session)

    router.add_api_route(p, lst, methods=["GET"], response_class=HTMLResponse)
    router.add_api_route(p, create, methods=["POST"])
    router.add_api_route(f"{p}/{{eid}}", detail, methods=["GET"], response_class=HTMLResponse)
    router.add_api_route(f"{p}/{{eid}}", update, methods=["POST"])
    router.add_api_route(f"{p}/{{eid}}/rename", rename, methods=["POST"])
    router.add_api_route(f"{p}/{{eid}}/delete", delete_, methods=["POST"])
    router.add_api_route(f"{p}/{{eid}}/merge", merge, methods=["POST"])


for _spec in _SPECS.values():
    _register(_spec)


# --- artist unit membership (shown on a unit's detail page) ----------------

@router.post("/artists/{eid}/members")
async def add_member(
    eid: str, request: Request, session: AsyncSession = Depends(get_session)
):
    if await session.get(Artist, eid) is None:
        return _redirect("/artists", "not found.")
    form = await request.form()
    mid = (form.get("id") or "").strip()
    if not mid or mid == eid:
        return _redirect(f"/artists/{eid}", "pick a different artist as member.")
    if await session.get(Artist, mid) is None:
        return _redirect(f"/artists/{eid}", f"no such artist: {mid!r}")
    stmt = pg_insert(ArtistMember).values([{"group_id": eid, "member_id": mid}])
    await session.execute(
        stmt.on_conflict_do_nothing(index_elements=["group_id", "member_id"])
    )
    await session.commit()
    return _redirect(f"/artists/{eid}#members")


@router.post("/artists/{eid}/members/{mid}/unlink")
async def remove_member(
    eid: str, mid: str, session: AsyncSession = Depends(get_session)
):
    await session.execute(
        delete(ArtistMember).where(
            ArtistMember.group_id == eid, ArtistMember.member_id == mid
        )
    )
    await session.commit()
    return _redirect(f"/artists/{eid}#members")


# --- song <-> entity linking (used from the song detail page) -------------

@router.post("/songs/{song_id}/{kind}")
async def link_to_song(
    song_id: str, kind: str, request: Request, session: AsyncSession = Depends(get_session)
):
    spec = _SPECS.get(kind)
    if spec is None:
        return HTMLResponse("Unknown kind", status_code=404)
    form = await request.form()
    eid = (form.get("id") or "").strip()
    if not eid or not await session.get(spec.entity, eid):
        return _redirect(f"/songs/{song_id}", f"no such {spec.kind[:-1]}: {eid!r}")
    stmt = pg_insert(spec.junction).values([{"song_id": song_id, spec.id_col: eid}])
    await session.execute(stmt.on_conflict_do_nothing(index_elements=["song_id", spec.id_col]))
    await session.commit()
    return _redirect(f"/songs/{song_id}#links")


@router.post("/songs/{song_id}/{kind}/{eid}/unlink")
async def unlink_from_song(
    song_id: str, kind: str, eid: str, session: AsyncSession = Depends(get_session)
):
    spec = _SPECS.get(kind)
    if spec is None:
        return HTMLResponse("Unknown kind", status_code=404)
    await session.execute(
        delete(spec.junction).where(
            spec.junction.song_id == song_id, getattr(spec.junction, spec.id_col) == eid
        )
    )
    await session.commit()
    return _redirect(f"/songs/{song_id}#links")


# --- per-difficulty entity links (override of the song's links) -----------

# singular kind -> (difficulty junction model, entity spec)
_DIFF_JUNCTION = {
    "artist": (DifficultyArtist, _SPECS["artists"]),
    "charter": (DifficultyCharter, _SPECS["charters"]),
}


async def _diff_back(difficulty_id: int, session: AsyncSession) -> str:
    """Per-chart links live on the song page; return there, anchored to the chart."""
    diff = await session.get(SongDifficulty, difficulty_id)
    if diff is None:
        return "/songs"
    return f"/songs/{diff.song_id}#chart-{difficulty_id}"


@router.post("/difficulties/{difficulty_id}/{kind}/override")
async def set_diff_override(
    difficulty_id: int, kind: str, request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Toggle a chart's artist/charter override flag. Off = inherit the song's
    links; on = use the chart's own set (empty set = explicitly unknown)."""
    if kind not in _DIFF_JUNCTION:
        return HTMLResponse("Unknown kind", status_code=404)
    diff = await session.get(SongDifficulty, difficulty_id)
    if diff is None:
        return HTMLResponse("Difficulty not found", status_code=404)
    form = await request.form()
    setattr(diff, f"{kind}s_overridden", form.get("on") is not None)
    await session.commit()
    return _redirect(await _diff_back(difficulty_id, session))


@router.post("/difficulties/{difficulty_id}/{kind}")
async def link_to_difficulty(
    difficulty_id: int, kind: str, request: Request,
    session: AsyncSession = Depends(get_session),
):
    entry = _DIFF_JUNCTION.get(kind)
    if entry is None:
        return HTMLResponse("Unknown kind", status_code=404)
    junction, spec = entry
    form = await request.form()
    eid = (form.get("id") or "").strip()
    if not eid or not await session.get(spec.entity, eid):
        return _redirect(await _diff_back(difficulty_id, session), f"no such {kind}: {eid!r}")
    stmt = pg_insert(junction).values([{"difficulty_id": difficulty_id, spec.id_col: eid}])
    await session.execute(
        stmt.on_conflict_do_nothing(index_elements=["difficulty_id", spec.id_col])
    )
    await session.commit()
    return _redirect(await _diff_back(difficulty_id, session))


@router.post("/difficulties/{difficulty_id}/{kind}/{eid}/unlink")
async def unlink_from_difficulty(
    difficulty_id: int, kind: str, eid: str,
    session: AsyncSession = Depends(get_session),
):
    entry = _DIFF_JUNCTION.get(kind)
    if entry is None:
        return HTMLResponse("Unknown kind", status_code=404)
    junction, spec = entry
    await session.execute(
        delete(junction).where(
            junction.difficulty_id == difficulty_id,
            getattr(junction, spec.id_col) == eid,
        )
    )
    await session.commit()
    return _redirect(await _diff_back(difficulty_id, session))


# --- packs ----------------------------------------------------------------

@router.get("/packs", response_class=HTMLResponse)
async def list_packs(request: Request, session: AsyncSession = Depends(get_session)):
    q = (request.query_params.get("q") or "").strip()
    base = select(Pack)
    if q:
        base = base.where(Pack.name.ilike(f"%{q}%") | Pack.pack_id.ilike(f"%{q}%"))
    page = await paginate(
        session, base, request=request,
        columns={"pack_id": Pack.pack_id, "name": Pack.name},
        default_sort="name", path="/packs", q=q,
    )
    return templates.TemplateResponse(request, "pack_list.html", {"page": page})


def _pack_fields(form) -> dict:
    return {
        "name": (form.get("name") or "").strip(),
        "description": (form.get("description") or "").strip() or None,
        "cover_art": (form.get("cover_art") or "").strip() or None,
        "release_date": parse_date(form.get("release_date") or ""),
    }


@router.post("/packs")
async def create_pack(request: Request, session: AsyncSession = Depends(get_session)):
    form = await request.form()
    pid = (form.get("pack_id") or "").strip()
    if not pid:
        return _redirect("/packs", "pack_id required.")
    if await session.get(Pack, pid):
        return _redirect("/packs", f"{pid} already exists.")
    session.add(Pack(pack_id=pid, **_pack_fields(form)))
    await session.commit()
    return _redirect(f"/packs/{pid}")


@router.get("/packs/{pack_id}", response_class=HTMLResponse)
async def pack_detail(
    pack_id: str, request: Request, session: AsyncSession = Depends(get_session)
):
    pack = await session.get(Pack, pack_id)
    if pack is None:
        return HTMLResponse("Not found", status_code=404)
    songs = (
        await session.scalars(
            select(Song).where(Song.pack_id == pack_id).order_by(Song.idx)
        )
    ).all()
    return templates.TemplateResponse(
        request, "pack_detail.html",
        {
            "pack": pack, "songs": songs,
            "release_date_str": display_date(pack.release_date),
            "error": request.query_params.get("error", ""),
        },
    )


@router.post("/packs/{pack_id}")
async def update_pack(
    pack_id: str, request: Request, session: AsyncSession = Depends(get_session)
):
    pack = await session.get(Pack, pack_id)
    if pack is None:
        return HTMLResponse("Not found", status_code=404)
    form = await request.form()
    for key, value in _pack_fields(form).items():
        setattr(pack, key, value)
    await session.commit()
    return _redirect(f"/packs/{pack_id}")


@router.post("/packs/{pack_id}/rename")
async def rename_pack(
    pack_id: str, request: Request, session: AsyncSession = Depends(get_session)
):
    """Change a pack's primary key. songs.pack_id cascades on update (see migration
    b3f1c2d4e5a6), so its songs follow automatically. Packs have no alias table."""
    pack = await session.get(Pack, pack_id)
    if pack is None:
        return HTMLResponse("Not found", status_code=404)
    form = await request.form()
    new_id = (form.get("new_id") or "").strip()
    if not new_id:
        return _redirect(f"/packs/{pack_id}", "New pack_id is required.")
    if new_id == pack_id:
        return _redirect(f"/packs/{pack_id}", "New pack_id is unchanged.")
    if await session.get(Pack, new_id):
        return _redirect(f"/packs/{pack_id}", f"{new_id} already exists.")
    await session.execute(
        update(Pack).where(Pack.pack_id == pack_id).values(pack_id=new_id)
    )
    await session.commit()
    return _redirect(f"/packs/{new_id}")


@router.post("/packs/{pack_id}/delete")
async def delete_pack(pack_id: str, session: AsyncSession = Depends(get_session)):
    # Detach songs (FK is nullable) rather than cascade-deleting the catalog.
    await session.execute(
        Song.__table__.update().where(Song.pack_id == pack_id).values(pack_id=None)
    )
    await session.execute(delete(Pack).where(Pack.pack_id == pack_id))
    await session.commit()
    return _redirect("/packs")
