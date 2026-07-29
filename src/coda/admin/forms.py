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

from starlette.datastructures import FormData

from coda.admin.presenters import parse_date, parse_time
from coda.catalog.resolution import OVERRIDABLE_FIELDS

_TRUE = {"true", "1", "yes", "on"}
_FALSE = {"false", "0", "no", "off"}


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


def parse_song_base(form: FormData) -> dict[str, Any]:
    """Concrete, fully-typed song-row values from the base song form."""
    return {
        "pack_id": (form.get("pack_id") or "").strip() or None,
        "pack_name": (form.get("pack_name") or "").strip(),
        "name_en": (form.get("name_en") or "").strip(),
        "name_jp": (form.get("name_jp") or "").strip(),
        "artist": (form.get("artist") or "").strip(),
        "bpm": (form.get("bpm") or "").strip(),
        "bpm_base": float(form.get("bpm_base") or 0),
        "time": parse_time(form.get("time") or ""),
        "side": int(form.get("side") or 0),
        "world_unlock": _checkbox(form, "world_unlock"),
        "remote_download": _checkbox(form, "remote_download"),
        "bg": (form.get("bg") or "").strip(),
        "date": parse_date(form.get("date") or "") or 0,
        "version": (form.get("version") or "").strip(),
        "jacket": (form.get("jacket") or "").strip(),
        "jacket_designer": (form.get("jacket_designer") or "").strip() or None,
    }


def parse_overrides(form: FormData) -> dict[str, Any]:
    """Overridable difficulty fields: blank -> ``None`` (inherit), else typed."""
    out: dict[str, Any] = {}
    for field in OVERRIDABLE_FIELDS:
        raw = form.get(field)
        if raw is None or raw.strip() == "":
            out[field] = None
            continue
        coerce = _COERCE.get(field)
        out[field] = coerce(raw.strip()) if coerce else raw.strip()
    return out
