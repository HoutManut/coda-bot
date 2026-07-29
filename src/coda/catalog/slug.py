"""ASCII slug derivation, shared by tag create paths.

Lowercase, collapse every run of non-alphanumeric chars to a single ``-``, and
trim leading/trailing ``-``. Non-ASCII (e.g. Japanese) labels can slugify to the
empty string; callers fall back to the lowercased label so a slug always exists.
"""

from __future__ import annotations

import re

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Return an ASCII slug, or ``""`` if ``text`` has no ASCII alphanumerics."""
    return _NON_ALNUM.sub("-", text.lower()).strip("-")
