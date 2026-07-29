"""Auto-derived search-alias terms, shared by the seed and the admin editor.

These are the *automatic* aliases the schema's "write triggers" describe: the
terms that must exist for an entity to be findable by its own ids/names. Both
the JSON seed (:mod:`coda.catalog.seed`) and the web admin write path call these
so the alias rows they produce are identical — search behaves the same no matter
which one wrote the data.

Every function returns a de-duplicated set of non-empty strings. Manually-added
aliases live alongside these in the same tables and are never produced here.
"""

from __future__ import annotations

from collections.abc import Iterable


def _clean(terms: Iterable[str | None]) -> set[str]:
    """Drop ``None`` and empty/whitespace-only terms; keep the rest verbatim."""
    return {t for t in terms if t and t.strip()}


def song_alias_terms(
    song_id: str,
    name_en: str,
    name_jp: str | None = None,
    extra: Iterable[str] = (),
) -> set[str]:
    """Auto aliases for a song: its id, English name, Japanese name, and any
    explicit ``aliases[]`` entries."""
    return _clean((song_id, name_en, name_jp, *extra))


def difficulty_alias_terms(
    name_en_override: str | None = None,
    game_song_id: str | None = None,
    extra: Iterable[str] = (),
) -> set[str]:
    """Auto aliases for one chart: its overridden ``name_en`` (set for ``err``),
    its game-native song id (set for ``byd_2``), and explicit ``aliases[]``."""
    return _clean((name_en_override, game_song_id, *extra))


def entity_alias_terms(entity_id: str, name: str | None = None) -> set[str]:
    """Auto aliases for an artist or charter: its id and display name."""
    return _clean((entity_id, name))
