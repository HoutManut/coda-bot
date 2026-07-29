"""Shared Jinja2 environment.

Kept separate from :mod:`coda.admin.app` so routers can import ``templates``
without importing the app (which imports the routers).
"""

from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

from coda.admin import presenters, tints
from coda.utils.dates import display_date, in_range, split_date

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def asset(name: str) -> str:
    """``/static/<name>`` stamped with the file's mtime.

    ``StaticFiles`` sends an ETag but no ``Cache-Control``, so a browser is free
    to reuse a cached stylesheet without revalidating -- which silently serves
    stale CSS/JS against freshly edited templates. The stamp makes each edit a
    new URL.
    """
    try:
        stamp = int((STATIC_DIR / name).stat().st_mtime)
    except OSError:
        return f"/static/{name}"
    return f"/static/{name}?v={stamp}"

# Expose presenter helpers to every template so display formatting lives in one
# place instead of being re-derived in markup.
templates.env.globals.update(
    display_level=presenters.display_level,
    display_rating=presenters.display_rating,
    list_level=presenters.list_level,
    list_rating=presenters.list_rating,
    is_sentinel=presenters.is_sentinel,
    side_label=presenters.side_label,
    side_choices=presenters.side_choices,
    difficulty_label=presenters.difficulty_label,
    display_date=display_date,
    split_date=split_date,
    date_in_range=in_range,
    display_time=presenters.display_time,
    tag_chip_style=presenters.tag_chip_style,
    DIFFICULTY_ORDER=presenters.DIFFICULTY_ORDER,
    asset=asset,
    difficulty_tint_class=tints.difficulty_tint_class,
    difficulty_tint_style=tints.difficulty_tint_style,
    side_tint_class=tints.side_tint_class,
    side_tint_style=tints.side_tint_style,
    chip_label=tints.chip_label,
)
