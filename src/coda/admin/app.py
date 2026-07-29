"""FastAPI application factory and instance.

Mounts static assets, wires the routers, and redirects the root to the song
list (the catalog's main entry point).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from coda.admin.routers import aliases, difficulties, entities, jackets, songs, tags

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Coda Catalog Admin")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
# Serve the jacket images for in-editor previews (read-only view of assets/jackets).
jackets.JACKETS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/jacket-img", StaticFiles(directory=str(jackets.JACKETS_DIR)), name="jacket-img")

app.include_router(songs.router)
app.include_router(difficulties.router)
app.include_router(entities.router)
app.include_router(aliases.router)
app.include_router(jackets.router)
app.include_router(tags.router)


@app.get("/", include_in_schema=False)
async def index() -> RedirectResponse:
    return RedirectResponse(url="/songs")
