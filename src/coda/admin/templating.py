"""Shared Jinja2 environment.

Kept separate from :mod:`coda.admin.app` so routers can import ``templates``
without importing the app (which imports the routers).
"""

from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

from coda.admin import presenters

TEMPLATES_DIR = Path(__file__).parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Expose presenter helpers to every template so display formatting lives in one
# place instead of being re-derived in markup.
templates.env.globals.update(
    display_level=presenters.display_level,
    display_rating=presenters.display_rating,
    side_label=presenters.side_label,
    side_choices=presenters.side_choices,
    difficulty_label=presenters.difficulty_label,
    display_date=presenters.display_date,
    display_time=presenters.display_time,
    tag_chip_style=presenters.tag_chip_style,
    DIFFICULTY_ORDER=presenters.DIFFICULTY_ORDER,
)
