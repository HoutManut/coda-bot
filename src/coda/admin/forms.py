"""Form-value coercion for song and difficulty edits.

Two shapes:

* **Base song** fields are always concrete — booleans are real checkboxes, the
  numeric fields must parse. :func:`parse_song_base` returns a fully-typed dict.
* **Difficulty overrides** follow the inheritance model: a blank field means
  "inherit from the song" (``None``). :func:`parse_overrides` returns ``None``
  for every blank and coerces the rest by type, so the form's placeholder/clear
  UX maps straight onto nullable columns.
"""

from __future__ import annotations

from typing import Any

from starlette.datastructures import FormData, UploadFile

from coda.admin.presenters import parse_time
from coda.utils.dates import combine_date, parse_date
from coda.catalog.resolution import OVERRIDABLE_FIELDS

_TRUE = {"true", "1", "yes", "on"}
_FALSE = {"false", "0", "no", "off"}


def form_text(form: FormData, name: str) -> str:
    """Text-field value, blank if absent. Fails loudly if a file was posted instead."""
    value = form.get(name)
    if isinstance(value, UploadFile):
        raise ValueError(f"expected text field {name!r}, got a file upload")
    return value or ""


def _to_bool(raw: str) -> bool:
    v = raw.strip().lower()
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    raise ValueError(f"not a boolean: {raw!r}")


# Coercion for the typed (non-string) overridable fields. Anything not listed is
# kept as a plain string.
_COERCE = {
    "bpm_base": float,
    "time": parse_time,
    "side": int,
    "world_unlock": _to_bool,
    "remote_download": _to_bool,
    "date": parse_date,  # already maps blank -> None
}


def _checkbox(form: FormData, name: str) -> bool:
    """An unchecked checkbox is absent from the POST body."""
    return form.get(name) is not None


def song_date(form: FormData) -> int:
    """Song release second from the split date-picker + offset fields.

    Falls back to a raw ``date`` field so a form posted without the split pair
    (or with a pasted epoch) still parses.
    """
    day = form_text(form, "date_day").strip()
    if not day:
        return parse_date(form_text(form, "date")) or 0
    try:
        offset = int(form_text(form, "date_offset").strip() or 0)
    except ValueError:
        offset = 0
    return combine_date(day, offset) or 0


def parse_song_base(form: FormData) -> dict[str, Any]:
    """Concrete, fully-typed song-row values from the base song form."""
    return {
        "pack_id": form_text(form, "pack_id").strip() or None,
        "pack_name": form_text(form, "pack_name").strip(),
        "name_en": form_text(form, "name_en").strip(),
        "name_jp": form_text(form, "name_jp").strip(),
        "artist": form_text(form, "artist").strip(),
        "bpm": form_text(form, "bpm").strip(),
        "bpm_base": float(form_text(form, "bpm_base") or 0),
        "time": parse_time(form_text(form, "time")),
        "side": int(form_text(form, "side") or 0),
        "world_unlock": _checkbox(form, "world_unlock"),
        "remote_download": _checkbox(form, "remote_download"),
        "bg": form_text(form, "bg").strip(),
        "date": song_date(form),
        "version": form_text(form, "version").strip(),
        "jacket": form_text(form, "jacket").strip(),
        "jacket_designer": form_text(form, "jacket_designer").strip() or None,
    }


def parse_overrides(form: FormData) -> dict[str, Any]:
    """Overridable difficulty fields: blank -> ``None`` (inherit), else typed."""
    out: dict[str, Any] = {}
    for field in OVERRIDABLE_FIELDS:
        raw = form_text(form, field).strip()
        if raw == "":
            out[field] = None
            continue
        coerce = _COERCE.get(field)
        out[field] = coerce(raw) if coerce else raw
    return out
