"""Manual alias add/remove for all four alias tables.

Auto-derived aliases (ids/names) are managed by :mod:`coda.admin.aliassync` on
entity saves; these routes are for the hand-typed extras that live alongside
them. Removing an alias here deletes whatever row matches — including an
auto term, which will simply be re-created on the next save of that entity.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from coda.admin import aliassync
from coda.admin.deps import get_session
from coda.db.models import (
    ArtistAlias,
    CharterAlias,
    DifficultyAlias,
    SongAlias,
    SongDifficulty,
)

router = APIRouter(prefix="/aliases")

# kind -> (alias model, fk column)
_KINDS = {
    "song": (SongAlias, "song_id"),
    "difficulty": (DifficultyAlias, "difficulty_id"),
    "artist": (ArtistAlias, "artist_id"),
    "charter": (CharterAlias, "charter_id"),
}


async def _back_url(kind: str, fk: str, session: AsyncSession) -> str:
    """Where to return after editing aliases for this entity."""
    if kind == "song":
        return f"/songs/{fk}#aliases"
    if kind == "difficulty":
        diff = await session.get(SongDifficulty, int(fk))
        return f"/songs/{diff.song_id}#chart-{fk}" if diff else "/songs"
    if kind == "artist":
        return f"/artists/{fk}"
    return f"/charters/{fk}"


def _coerce_fk(kind: str, fk: str):
    return int(fk) if kind == "difficulty" else fk


@router.post("/{kind}/{fk}/add")
async def add_alias(
    kind: str, fk: str, alias: str = Form(...), session: AsyncSession = Depends(get_session)
):
    if kind not in _KINDS:
        return HTMLResponse("Unknown kind", status_code=404)
    model, fk_col = _KINDS[kind]
    await aliassync.add_manual(session, model, fk_col, _coerce_fk(kind, fk), alias)
    await session.commit()
    return RedirectResponse(await _back_url(kind, fk, session), status_code=303)


@router.post("/{kind}/{fk}/remove")
async def remove_alias(
    kind: str, fk: str, alias: str = Form(...), session: AsyncSession = Depends(get_session)
):
    if kind not in _KINDS:
        return HTMLResponse("Unknown kind", status_code=404)
    model, fk_col = _KINDS[kind]
    await aliassync.remove(session, model, fk_col, _coerce_fk(kind, fk), alias)
    await session.commit()
    return RedirectResponse(await _back_url(kind, fk, session), status_code=303)
