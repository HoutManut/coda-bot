"""Artist/charter id derivation from a display name.

Deliberately **not** :func:`coda.catalog.slug.slugify`. Slugs are lowercased and
hyphenated, which is right for tag slugs and wrong here: the catalog's existing
artist ids include ``Yuki Kira`` and ``kamome sano`` (spaces), ``A.SAKA`` (a
dot), ``A-zu-ra`` (hyphens), and CJK-only ids such as ``煌`` and ``理``. Over a
hundred carry spaces and over a hundred carry characters outside
``[A-Za-z0-9_-]``, so any stricter rule would derive ids that do not match the
rows already there.

Only what actually breaks a URL path is removed; case, spaces, punctuation and
non-ASCII all survive.
"""

from __future__ import annotations

import re
import unicodedata

# `/` splits the URL path (the existing `a/i` artist 404s for exactly this
# reason); `?` and `#` end it; `%` and `&` corrupt query parsing.
_UNSAFE = re.compile(r"[/?#%&]")
_WHITESPACE = re.compile(r"\s+")


def clean_entity_id(name: str) -> str:
    """Artist/charter id from a display name.

    Drops only URL-breaking and control characters; preserves case, spaces,
    punctuation, and non-ASCII.
    """
    # Whitespace is folded first so a tab between words becomes a space rather
    # than being dropped as a control character.
    spaced = _WHITESPACE.sub(" ", name)
    kept = "".join(
        ch for ch in spaced if unicodedata.category(ch) not in ("Cc", "Cf")
    )
    return _WHITESPACE.sub(" ", _UNSAFE.sub("", kept)).strip()
