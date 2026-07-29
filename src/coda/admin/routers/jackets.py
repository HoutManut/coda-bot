"""Jacket (cover art) ingestion.

The ``jacket`` field stores a file *stem* (no extension); the real image lives at
``assets/jackets/<stem>.webp``. Song-level art uses the ``song_id`` as the stem;
a per-difficulty override uses ``<song_id>_<DIFF>`` (e.g. ``goodtek_BYD``). This
endpoint takes an uploaded file *or* an image URL and writes it to that stem, so
the editor never has to touch the filesystem by hand.

Note: the game also varies a cover by time-of-day and by user locale. Those are
just extra stems (e.g. ``melodyoflove_NIGHT``); no special logic is needed here —
type or drop onto the stem you want.

This is a localhost-only tool; URL fetching is a deliberate convenience and is
not hardened against SSRF.
"""

from __future__ import annotations

import asyncio
import io
import re
import urllib.request
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from PIL import Image

router = APIRouter(prefix="/jackets")

# cwd-relative, matching the seed's asset paths (admin runs from the repo root).
JACKETS_DIR = Path("assets/jackets")
_STEM = re.compile(r"^[A-Za-z0-9_]+$")
_MAX_BYTES = 8 * 1024 * 1024


def _target(stem: str) -> Path:
    if not _STEM.match(stem):
        raise HTTPException(400, "Stem must be letters, digits, or underscores.")
    path = (JACKETS_DIR / f"{stem}.webp").resolve()
    if path.parent != JACKETS_DIR.resolve():
        raise HTTPException(400, "Invalid stem.")
    return path


def _to_webp(data: bytes) -> bytes:
    """Re-encode arbitrary image bytes to WebP -- uploads/URLs arrive in whatever
    format the source used, and the store is WebP-only."""
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception as exc:
        raise HTTPException(400, "Not a readable image.") from exc
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
    out = io.BytesIO()
    image.save(out, format="WEBP", quality=90)
    return out.getvalue()


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "coda-admin"})
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 (local tool)
        ctype = resp.headers.get_content_type()
        if not ctype.startswith("image/"):
            raise HTTPException(400, f"URL is not an image (got {ctype}).")
        data = resp.read(_MAX_BYTES + 1)
    if len(data) > _MAX_BYTES:
        raise HTTPException(400, "Image exceeds 8 MB.")
    return data


@router.post("/upload")
async def upload(
    stem: str = Form(...),
    url: str = Form(""),
    file: UploadFile | None = File(None),
):
    """Write an uploaded file or fetched URL to ``assets/jackets/<stem>.webp``."""
    stem = stem.strip()
    target = _target(stem)

    if file is not None and file.filename:
        data = await file.read()
    elif url.strip():
        data = await asyncio.to_thread(_fetch, url.strip())
    else:
        raise HTTPException(400, "Provide a file or an image URL.")
    if not data:
        raise HTTPException(400, "Empty image.")
    if len(data) > _MAX_BYTES:
        raise HTTPException(400, "Image exceeds 8 MB.")

    data = await asyncio.to_thread(_to_webp, data)

    JACKETS_DIR.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {"ok": True, "stem": stem, "src": f"/jacket-img/{stem}.webp"}
