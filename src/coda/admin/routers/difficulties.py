"""Difficulty (chart) create / update / delete for a song.

Enforces ``byd``/``etr`` mutual exclusivity on a song, and forces ``err`` charts
to the ``-1`` ("?") sentinels for level/rating. ``name_en`` is treated as a
plain optional override for every difficulty, ``err`` included.
"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from coda.admin import aliassync
from coda.admin.deps import get_session
from coda.admin.forms import parse_overrides
from coda.admin.presenters import parse_level, parse_rating
from coda.db.enums import DifficultyClass
from coda.db.models import (
    DifficultyAlias,
    DifficultyArtist,
    DifficultyCharter,
    SongDifficulty,
)

router = APIRouter()

_EXCLUSIVE = {DifficultyClass.BYD: DifficultyClass.ETR, DifficultyClass.ETR: DifficultyClass.BYD}


def _back(song_id: str, error: str = "", anchor: str = "") -> RedirectResponse:
    url = f"/songs/{song_id}"
    if error:
        url += f"?error={quote(error)}"
    if anchor:
        url += f"#{anchor}"
    return RedirectResponse(url=url, status_code=303)


def _chart_values(form, difficulty: DifficultyClass) -> dict:
    """Level/rating/note/designer/game id, with err forced to its sentinels."""
    overrides = parse_overrides(form)
    if difficulty is DifficultyClass.ERR:
        level = rating = -1
    else:
        level = parse_level(form.get("level") or "")
        rating = parse_rating(form.get("rating") or "")
    return {
        "level": level,
        "rating": rating,
        "note": int(form.get("note") or 0),
        "chart_designer": (form.get("chart_designer") or "").strip() or None,
        "game_song_id": (form.get("game_song_id") or "").strip() or None,
        **overrides,
    }


@router.post("/songs/{song_id}/difficulties")
async def create_difficulty(
    song_id: str, request: Request, session: AsyncSession = Depends(get_session)
) -> RedirectResponse:
    form = await request.form()
    try:
        difficulty = DifficultyClass(form.get("difficulty"))
    except ValueError:
        return _back(song_id, "Unknown difficulty.")

    existing = set(
        (
            await session.scalars(
                select(SongDifficulty.difficulty).where(
                    SongDifficulty.song_id == song_id
                )
            )
        ).all()
    )
    if difficulty in existing:
        return _back(song_id, f"{difficulty.value} already exists for this song.")
    conflict = _EXCLUSIVE.get(difficulty)
    if conflict and conflict in existing:
        return _back(
            song_id,
            f"{difficulty.value} can't coexist with {conflict.value} (mutually exclusive).",
        )

    values = _chart_values(form, difficulty)
    diff = SongDifficulty(song_id=song_id, difficulty=difficulty, **values)
    session.add(diff)
    await session.flush()
    await aliassync.sync_difficulty(
        session, diff.id,
        new_name_en=values.get("name_en"), new_game_song_id=values.get("game_song_id"),
    )
    await session.commit()
    return _back(song_id, anchor=f"chart-{diff.id}")


@router.post("/difficulties/{difficulty_id}")
async def update_difficulty(
    difficulty_id: int, request: Request, session: AsyncSession = Depends(get_session)
):
    diff = await session.get(SongDifficulty, difficulty_id)
    if diff is None:
        return HTMLResponse("Difficulty not found", status_code=404)

    form = await request.form()
    old_name_en, old_game_song_id = diff.name_en, diff.game_song_id
    values = _chart_values(form, diff.difficulty)
    for key, value in values.items():
        setattr(diff, key, value)
    await aliassync.sync_difficulty(
        session, diff.id,
        old_name_en=old_name_en, old_game_song_id=old_game_song_id,
        new_name_en=diff.name_en, new_game_song_id=diff.game_song_id,
    )
    await session.commit()
    return _back(diff.song_id, anchor=f"chart-{diff.id}")


@router.post("/difficulties/{difficulty_id}/delete")
async def delete_difficulty(
    difficulty_id: int, session: AsyncSession = Depends(get_session)
):
    diff = await session.get(SongDifficulty, difficulty_id)
    if diff is None:
        return HTMLResponse("Difficulty not found", status_code=404)
    song_id = diff.song_id
    await session.execute(
        delete(DifficultyAlias).where(DifficultyAlias.difficulty_id == difficulty_id)
    )
    await session.execute(
        delete(DifficultyArtist).where(DifficultyArtist.difficulty_id == difficulty_id)
    )
    await session.execute(
        delete(DifficultyCharter).where(DifficultyCharter.difficulty_id == difficulty_id)
    )
    await session.execute(
        delete(SongDifficulty).where(SongDifficulty.id == difficulty_id)
    )
    await session.commit()
    return _back(song_id)
