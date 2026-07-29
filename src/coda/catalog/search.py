"""Catalog search + resolution — the reusable seam under ``/song``.

``SearchService.resolve`` turns a raw query string into a typed :data:`Resolution`
(plain ids, never a Discord embed) so future callers (``/score``, tournament
chart-pick, alias admin) share one resolver. Presentation lives in the caller.

The query grammar (level / CC / exact id / ``<song> <class>`` chart intent /
name+alias) is defined here; this module is its single source of truth. Candidate generation hits the
``search_index`` materialized view (pg_trgm exact + fuzzy); confidence banding
and conflict resolution happen here in Python.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Union

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from coda.db.enums import DifficultyClass
from coda.db.models import DifficultySearchConfig, Song, SongDifficulty
from coda.utils.encoding import encode_level, encode_rating

# --- result types -----------------------------------------------------------


@dataclass(frozen=True)
class SongHit:
    """A single song (mode A). ``missing_class`` set when a ``difficulty`` option
    named a class this song lacks — the presenter shows the song plus a note."""

    song_id: str
    missing_class: DifficultyClass | None = None


@dataclass(frozen=True)
class ChartHit:
    """A single chart (mode B)."""

    difficulty_id: int


@dataclass(frozen=True)
class SongDupes:
    """Several songs sharing a name — a button-per-song pick, each opening mode A."""

    song_ids: list[str]


@dataclass(frozen=True)
class ChartPick:
    """A small set of charts to choose between (ambiguous Beyond), each mode B."""

    difficulty_ids: list[int]


@dataclass(frozen=True)
class ChartList:
    """A broad level/CC result — paginated select, each option opening mode B."""

    difficulty_ids: list[int]
    truncated: bool = False


@dataclass(frozen=True)
class Candidate:
    """One weak-band suggestion: a song or a specific chart."""

    song_id: str
    difficulty_id: int | None = None


@dataclass(frozen=True)
class DidYouMean:
    """1–3 weak candidates the presenter renders as 'Did you mean …?' buttons."""

    candidates: list[Candidate]


@dataclass(frozen=True)
class NoMatch:
    """No result. ``reason`` None → restate the accepted syntax; otherwise a
    specific note (e.g. 'No charts at level 10+.')."""

    reason: str | None = None


Resolution = Union[
    SongHit, ChartHit, SongDupes, ChartPick, ChartList, DidYouMean, NoMatch
]

# --- parsing constants ------------------------------------------------------

_LEVEL_RE = re.compile(r"^\d{1,2}\+?$")
_CC_RE = re.compile(r"^\d{1,2}\.\d+$")
_WS_RE = re.compile(r"\s+")

_CLASS_TOKENS: dict[str, DifficultyClass] = {
    "pst": DifficultyClass.PST,
    "past": DifficultyClass.PST,
    "prs": DifficultyClass.PRS,
    "present": DifficultyClass.PRS,
    "ftr": DifficultyClass.FTR,
    "future": DifficultyClass.FTR,
    "byd": DifficultyClass.BYD,
    "beyond": DifficultyClass.BYD,
    "etr": DifficultyClass.ETR,
    "eternal": DifficultyClass.ETR,
}

_LIST_CAP = 200


def _normalize(query: str) -> str:
    return _WS_RE.sub(" ", query.strip()).lower()


def _escape_like(term: str) -> str:
    """Escape LIKE wildcards so a typed ``%`` or ``_`` is matched literally."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _is_delisted(song: Song) -> bool:
    name = song.name_en
    return len(name) >= 2 and name.startswith("_") and name.endswith("_")


@dataclass
class _Config:
    """The search-tuning config, loaded once per resolve()."""

    by_class: dict[DifficultyClass, DifficultySearchConfig]
    broad_floor: float
    strong: float
    hidden_classes: frozenset[DifficultyClass]
    af_suffixes: tuple[str, ...]


@dataclass
class _Cand:
    entity_type: str
    song_id: str
    difficulty_id: int | None
    difficulty_class: DifficultyClass | None
    sim: float
    exact: bool = False
    term: str = ""


class SearchService:
    """Stateless catalog resolver; takes an ``AsyncSession`` per call."""

    async def resolve(
        self,
        db: AsyncSession,
        query: str,
        *,
        difficulty: DifficultyClass | None = None,
        include_hidden: bool = False,
    ) -> Resolution:
        """Resolve a raw query to a typed result. ``include_hidden`` unlocks err
        charts (via explicit intent only) and delisted songs; ``/song`` passes
        the default, keeping both cloaked."""
        norm = _normalize(query)
        if not norm:
            return NoMatch()

        config = await self._load_config(db)

        level_or_cc = await self._try_level_or_cc(db, norm, difficulty, include_hidden)
        if level_or_cc is not None:
            return level_or_cc

        chart_intent = await self._try_chart_intent(
            db, norm, config, difficulty, include_hidden
        )
        if chart_intent is not None:
            return chart_intent

        return await self._resolve_name(db, norm, config, difficulty, include_hidden)

    async def candidate_songs(
        self, db: AsyncSession, typed: str, *, limit: int = 25
    ) -> list[tuple[str, str, str, str]]:
        """Autocomplete fast path: up to ``limit`` (song_id, name_en, artist,
        pack_name) rows, err/delisted excluded. Substring match (not the
        similarity gate) so a short prefix like ``prag`` still finds
        ``pragmatism``; ranked by trigram similarity within the matches."""
        norm = _normalize(typed)
        if not norm:
            return []
        like = f"%{_escape_like(norm)}%"
        rows = (
            await db.execute(_AUTOCOMPLETE_SQL, {"q": norm, "like": like})
        ).all()
        best: dict[str, float] = {}
        for row in rows:
            best[row.song_id] = max(best.get(row.song_id, 0.0), float(row.sim))
        ordered = sorted(best, key=lambda sid: best[sid], reverse=True)
        if not ordered:
            return []
        stmt = select(
            Song.song_id, Song.name_en, Song.artist, Song.pack_name
        ).where(Song.song_id.in_(ordered))
        rows = (await db.execute(stmt)).all()
        rank = {sid: i for i, sid in enumerate(ordered)}
        visible = [
            (r[0], r[1], r[2], r[3])
            for r in rows
            if not (len(r[1]) >= 2 and r[1].startswith("_") and r[1].endswith("_"))
        ]
        visible.sort(key=lambda r: rank[r[0]])
        return visible[:limit]

    # -- config ----------------------------------------------------------

    async def _load_config(self, db: AsyncSession) -> _Config:
        rows = (await db.execute(select(DifficultySearchConfig))).scalars().all()
        by_class = {row.difficulty: row for row in rows}
        visible = [row for row in rows if not row.hidden_from_broad]
        broad_floor = min((row.min_similarity for row in visible), default=0.4)
        strong = min((row.strong for row in visible), default=0.7)
        hidden = frozenset(row.difficulty for row in rows if row.hidden_from_broad)
        err = by_class.get(DifficultyClass.ERR)
        suffixes = tuple(err.af_suffixes) if err and err.af_suffixes else ()
        return _Config(by_class, broad_floor, strong, hidden, suffixes)

    # -- level / CC ------------------------------------------------------

    async def _try_level_or_cc(
        self,
        db: AsyncSession,
        norm: str,
        difficulty: DifficultyClass | None,
        include_hidden: bool,
    ) -> Resolution | None:
        if _LEVEL_RE.match(norm):
            code = encode_level(norm)
            charts = await self._charts_where(
                db, SongDifficulty.level == code, difficulty, include_hidden
            )
            return self._collapse_list(charts, f"No charts at level {norm}.")
        if _CC_RE.match(norm):
            whole, frac = norm.split(".")
            code = encode_rating(float(f"{whole}.{frac[0]}"))
            charts = await self._charts_where(
                db, SongDifficulty.rating == code, difficulty, include_hidden
            )
            return self._collapse_list(charts, f"No charts at CC {whole}.{frac[0]}.")
        return None

    async def _charts_where(
        self,
        db: AsyncSession,
        predicate,
        difficulty: DifficultyClass | None,
        include_hidden: bool,
    ) -> tuple[list[int], bool]:
        stmt = (
            select(SongDifficulty, Song)
            .join(Song, Song.song_id == SongDifficulty.song_id)
            .where(predicate)
        )
        rows = (await db.execute(stmt)).all()
        kept = [
            (chart, song)
            for chart, song in rows
            if self._chart_visible(chart, song, difficulty, include_hidden)
        ]
        kept.sort(key=lambda cs: (-cs[0].rating, cs[1].name_en.lower()))
        return [chart.id for chart, _ in kept[:_LIST_CAP]], len(kept) > _LIST_CAP

    def _chart_visible(
        self,
        chart: SongDifficulty,
        song: Song,
        difficulty: DifficultyClass | None,
        include_hidden: bool,
    ) -> bool:
        if chart.difficulty == DifficultyClass.ERR and not include_hidden:
            return False
        if _is_delisted(song) and not include_hidden:
            return False
        if difficulty is not None and chart.difficulty != difficulty:
            return False
        return True

    def _collapse_list(
        self, charts: tuple[list[int], bool], empty_reason: str
    ) -> Resolution:
        ids, truncated = charts
        if not ids:
            return NoMatch(reason=empty_reason)
        if len(ids) == 1:
            return ChartHit(ids[0])
        return ChartList(ids, truncated=truncated)

    # -- exact id / difficulty option -----------------------------------

    async def _get_song(
        self, db: AsyncSession, song_id: str, include_hidden: bool
    ) -> Song | None:
        song = await db.get(Song, song_id)
        if song is None:
            return None
        if _is_delisted(song) and not include_hidden:
            return None
        return song

    async def _apply_difficulty(
        self,
        db: AsyncSession,
        song_id: str,
        difficulty: DifficultyClass | None,
        include_hidden: bool,
    ) -> Resolution:
        if difficulty is None:
            return SongHit(song_id)
        charts = await self._song_charts(db, song_id, include_hidden)
        matched = [c for c in charts if c.difficulty == difficulty]
        if not matched:
            if difficulty == DifficultyClass.BYD:
                matched = [
                    c for c in charts if c.difficulty == DifficultyClass.BYD_2
                ]
        beyonds = [
            c
            for c in charts
            if c.difficulty in (DifficultyClass.BYD, DifficultyClass.BYD_2)
        ]
        if difficulty == DifficultyClass.BYD and len(beyonds) > 1:
            return ChartPick([c.id for c in beyonds])
        if not matched:
            return SongHit(song_id, missing_class=difficulty)
        return ChartHit(matched[0].id)

    async def _song_charts(
        self, db: AsyncSession, song_id: str, include_hidden: bool
    ) -> list[SongDifficulty]:
        stmt = select(SongDifficulty).where(SongDifficulty.song_id == song_id)
        charts = (await db.execute(stmt)).scalars().all()
        if include_hidden:
            return list(charts)
        return [c for c in charts if c.difficulty != DifficultyClass.ERR]

    # -- chart intent (<song> <class|alias|af>) --------------------------

    async def _try_chart_intent(
        self,
        db: AsyncSession,
        norm: str,
        config: _Config,
        difficulty: DifficultyClass | None,
        include_hidden: bool,
    ) -> Resolution | None:
        err_head = self._strip_af_suffix(norm, config.af_suffixes)
        if err_head is not None:
            return await self._resolve_err_intent(db, err_head, config, include_hidden)

        if " " not in norm:
            return None
        head, token = norm.rsplit(" ", 1)
        klass = _CLASS_TOKENS.get(token)
        if klass is not None:
            song_id = await self._head_song(db, head, config, include_hidden)
            if song_id is None:
                return None
            return await self._apply_difficulty(db, song_id, klass, include_hidden)

        chart_id = await self._diff_alias_chart(
            db, token, head, config, include_hidden
        )
        if chart_id is not None:
            return ChartHit(chart_id)
        return None

    def _strip_af_suffix(
        self, norm: str, suffixes: tuple[str, ...]
    ) -> str | None:
        for suffix in suffixes:
            if norm.endswith(" " + suffix):
                return norm[: -len(suffix)].strip()
        return None

    async def _resolve_err_intent(
        self, db: AsyncSession, head: str, config: _Config, include_hidden: bool
    ) -> Resolution:
        if not include_hidden:
            return NoMatch()
        song_id = await self._head_song(db, head, config, include_hidden=True)
        if song_id is None:
            return NoMatch()
        charts = await self._song_charts(db, song_id, include_hidden=True)
        err = [c for c in charts if c.difficulty == DifficultyClass.ERR]
        return ChartHit(err[0].id) if err else NoMatch()

    async def _head_song(
        self, db: AsyncSession, head: str, config: _Config, include_hidden: bool
    ) -> str | None:
        song = await self._get_song(db, head, include_hidden)
        if song is not None:
            return song.song_id
        exact = await self._exact_candidates(db, head)
        exact_songs = [c for c in exact if c.entity_type == "song"]
        if len(exact_songs) == 1:
            return exact_songs[0].song_id
        if exact_songs:
            return None
        fuzzy = await self._fuzzy_candidates(db, head, config.broad_floor)
        fuzzy = await self._filter_candidates(db, fuzzy, config, include_hidden)
        songs = sorted(
            (c for c in fuzzy if c.entity_type == "song"),
            key=lambda c: c.sim,
            reverse=True,
        )
        return songs[0].song_id if songs else None

    async def _diff_alias_chart(
        self, db: AsyncSession, token: str, head: str, config: _Config,
        include_hidden: bool,
    ) -> int | None:
        rows = await self._exact_candidates(db, token)
        charts = [c for c in rows if c.entity_type == "difficulty"]
        if not charts:
            return None
        head_song = await self._head_song(db, head, config, include_hidden)
        for cand in charts:
            if head_song is None or cand.song_id == head_song:
                if cand.difficulty_class == DifficultyClass.ERR and not include_hidden:
                    continue
                return cand.difficulty_id
        return None

    # -- name / alias search --------------------------------------------

    async def _resolve_name(
        self,
        db: AsyncSession,
        norm: str,
        config: _Config,
        difficulty: DifficultyClass | None,
        include_hidden: bool,
    ) -> Resolution:
        if len(norm) <= 2:
            cands = await self._exact_candidates(db, norm)
        else:
            cands = await self._fuzzy_candidates(db, norm, config.broad_floor)
        cands = await self._filter_candidates(db, cands, config, include_hidden)
        if not cands:
            return NoMatch()

        working = self._top_tier(cands)
        working = self._apply_specificity(working)
        top_sim = working[0].sim

        if top_sim >= config.strong or working[0].exact:
            return await self._serve_top_tier(
                db, working, difficulty, include_hidden
            )

        # Prefix rescue: trigram similarity punishes a short query against a long
        # name ("placebo" vs "placebo battler" ~= 0.41 < strong), stranding an
        # obvious match in the "did you mean" band. When the query is a leading
        # prefix of exactly one song's terms, serve it directly. The single-song
        # guard keeps genuinely ambiguous prefixes (several songs) as suggestions.
        prefixed = [c for c in cands if c.term.startswith(norm)]
        if prefixed and len({c.song_id for c in prefixed}) == 1:
            working = self._apply_specificity(prefixed)
            return await self._serve_top_tier(
                db, working, difficulty, include_hidden
            )
        return self._did_you_mean(cands)

    async def _serve_top_tier(
        self,
        db: AsyncSession,
        working: list[_Cand],
        difficulty: DifficultyClass | None,
        include_hidden: bool,
    ) -> Resolution:
        songs = [c for c in working if c.entity_type == "song"]
        charts = [c for c in working if c.entity_type == "difficulty"]
        if len(working) == 1 and songs:
            return await self._apply_difficulty(
                db, songs[0].song_id, difficulty, include_hidden
            )
        if len(working) == 1 and charts:
            return ChartHit(charts[0].difficulty_id)  # type: ignore[arg-type]
        if songs and not charts:
            unique = list(dict.fromkeys(c.song_id for c in songs))
            return SongDupes(unique)
        chart_ids = [c.difficulty_id for c in charts if c.difficulty_id is not None]
        return ChartPick(list(dict.fromkeys(chart_ids)))

    def _did_you_mean(self, cands: list[_Cand]) -> Resolution:
        ordered = sorted(cands, key=lambda c: c.sim, reverse=True)[:3]
        return DidYouMean(
            [Candidate(c.song_id, c.difficulty_id) for c in ordered]
        )

    async def _filter_candidates(
        self,
        db: AsyncSession,
        cands: list[_Cand],
        config: _Config,
        include_hidden: bool,
    ) -> list[_Cand]:
        # err never surfaces via broad/name search -- only its explicit intent.
        kept = [
            c
            for c in cands
            if c.difficulty_class is None
            or c.difficulty_class not in config.hidden_classes
        ]
        if include_hidden:
            return kept
        delisted = await self._delisted_song_ids(db, {c.song_id for c in kept})
        return [c for c in kept if c.song_id not in delisted]

    async def _delisted_song_ids(
        self, db: AsyncSession, song_ids: set[str]
    ) -> set[str]:
        if not song_ids:
            return set()
        stmt = select(Song.song_id, Song.name_en).where(Song.song_id.in_(song_ids))
        rows = (await db.execute(stmt)).all()
        return {
            sid
            for sid, name in rows
            if len(name) >= 2 and name.startswith("_") and name.endswith("_")
        }

    def _top_tier(self, cands: list[_Cand]) -> list[_Cand]:
        exact = [c for c in cands if c.exact]
        if exact:
            return exact
        best = max(c.sim for c in cands)
        return [c for c in cands if best - c.sim < 1e-9]

    def _apply_specificity(self, working: list[_Cand]) -> list[_Cand]:
        chart_songs = {
            c.song_id for c in working if c.entity_type == "difficulty"
        }
        pruned = [
            c
            for c in working
            if not (c.entity_type == "song" and c.song_id in chart_songs)
        ]
        return pruned or working

    async def _exact_candidates(self, db: AsyncSession, norm: str) -> list[_Cand]:
        rows = await db.execute(_EXACT_SQL, {"q": norm})
        return [self._row_to_cand(row, exact=True) for row in rows]

    async def _fuzzy_candidates(
        self, db: AsyncSession, norm: str, floor: float
    ) -> list[_Cand]:
        rows = (await db.execute(_FUZZY_SQL, {"q": norm, "floor": floor})).all()
        merged: dict[tuple[str, str, int | None], _Cand] = {}
        for row in rows:
            cand = self._row_to_cand(row, exact=bool(row.exact))
            key = (cand.entity_type, cand.song_id, cand.difficulty_id)
            existing = merged.get(key)
            if existing is None or cand.sim > existing.sim:
                merged[key] = cand
        return list(merged.values())

    def _row_to_cand(self, row, *, exact: bool) -> _Cand:
        dclass = (
            DifficultyClass(row.dclass) if row.dclass is not None else None
        )
        return _Cand(
            entity_type=row.entity_type,
            song_id=row.song_id,
            difficulty_id=row.difficulty_id,
            difficulty_class=dclass,
            sim=float(row.sim),
            exact=exact,
            term=str(row.term).lower() if row.term is not None else "",
        )


_EXACT_SQL = text(
    """
    SELECT entity_type, song_id, difficulty_id,
           difficulty_class::text AS dclass, term, 1.0 AS sim
    FROM search_index
    WHERE entity_type IN ('song', 'difficulty')
      AND lower(term) = :q
    """
)

_FUZZY_SQL = text(
    """
    SELECT entity_type, song_id, difficulty_id,
           difficulty_class::text AS dclass, term,
           similarity(lower(term), :q) AS sim,
           (lower(term) = :q) AS exact
    FROM search_index
    WHERE entity_type IN ('song', 'difficulty')
      AND (lower(term) = :q OR similarity(lower(term), :q) >= :floor)
    """
)

_AUTOCOMPLETE_SQL = text(
    """
    SELECT song_id, similarity(lower(term), :q) AS sim
    FROM search_index
    WHERE entity_type = 'song' AND lower(term) LIKE :like
    """
)


async def refresh_search_index(db: AsyncSession) -> None:
    """Rebuild the ``search_index`` matview. Call after any alias write.

    Plain (non-concurrent) refresh: the catalog is small and alias writes are
    rare, and CONCURRENTLY would require a unique index on the view.
    """
    await db.execute(text("REFRESH MATERIALIZED VIEW search_index"))
