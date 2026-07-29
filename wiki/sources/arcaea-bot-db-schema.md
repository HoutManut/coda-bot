---
type: source
status: active
path: arcaea-bot-db-schema.md
lines: 571
dated: "living reference, most recently 2026-07-17 per §9 note"
verified: 2026-07-21
supersedes: []
superseded_by: ["arcaea-api-layer.md §9 (users/accounts — Tier 2, not this ingest)", "src/coda/db/models/play_score.py (scores dedup design — shipped code)"]
created: 2026-07-21
updated: 2026-07-21
tags: [source, db, catalog, schema]
aliases: ["Arcaea Bot — PostgreSQL Database Schema Design"]
---

# Arcaea Bot — PostgreSQL Database Schema Design

## Covers

The song catalog schema authoritatively: `packs`, `songs`, `song_difficulties`,
`artists`/`charters` and their junctions, alias tables, tag tables, the
`difficulty_search_config` tuning table, the `search_index` materialized view,
and the resolution/inheritance rules (`COALESCE(difficulty.field, song.field)`).
**Despite the title, §1–8 does not cover the player-facing tables** — those are
documented in [[arcaea-api-layer]] §9 (Tier 2, outside this ingest).
§9 of this doc is itself a stale forward-pointer written when users/scores
were still future work; §10 lists open catalog questions.

## Key claims

- Natural keys where they exist (`pack_id`, `song_id`, `artist_id`,
  `charter_id` are game-assigned strings, used directly as PKs) — **verified
  current** against `src/coda/db/models/{pack,song,artist,charter}.py`.
- `song_difficulties` uses a SERIAL PK because its natural key is composite
  and `difficulty_aliases` needs a single-column FK target — **verified
  current** against `src/coda/db/models/difficulty.py`.
- Inheritance by NULL: every overridable field on `song_difficulties` is
  nullable, resolved as `COALESCE(difficulty.field, song.field)` — **verified
  current**, same file.
- Sentinel values: `level`/`rating` use `0` = TBA, `-1` = N/A (`err` only,
  displayed `"?"`), never inherited — **verified current**.
- Search is trigram-based (`pg_trgm`), scored in Python not SQL, with
  per-difficulty config in `difficulty_search_config` (`hidden_from_broad`,
  `min_similarity`, `af_suffixes`) — **verified current** against
  `src/coda/db/models/search_config.py`, though that model has an additional
  `strong` column (the "did you mean" cutoff) not in this doc's §3.12 table —
  a minor doc/code drift, not a design reversal.
- §9 "Users & Scores": explicitly self-flags as **stale** in its own text —
  "Users are no longer future... specified in `arcaea-api-layer.md` §9, which
  is authoritative for them — not this section." The doc correctly defers.

## Contradicts / reversed by

> [!contradiction]
> §9's dedup sketch — *"Dedup differs by tier: tier 2 has a stable play `id`;
> tier 1 must key on `(arc_user_id, song_id, difficulty, score, time_played)`"*
> — does **not** match what shipped. `src/coda/db/models/play_score.py` uses
> **one identity tuple for both tiers**:
> `UNIQUE(arcaea_account_id, wire_song_id, wire_difficulty, score, time_played)`.
> `wire_play_id` (the own-tier stable id) is a **secondary** partial-unique
> guard, not the dedup key. No source doc documents this refinement —
> it exists only in the shipped model. Treat the code as authoritative per
> vault precedence (live code / wire behavior outranks docs); this page is
> marked `superseded_by` the code on this specific point.

The rest of §9 (potential/grade as derived-not-stored, clear_type
own-path-only, best-score-vs-full-history as DISPUTED) is **not** contradicted
— it correctly anticipated what shipped (`play_score.py` docstring: "Play
rating is NOT stored... same rule as 'tier is derived, never stored'").

## Feeds

`[[db]]` (this ingest's primary derived page). §9's remaining open items feed
`[[h-catalog-schema-open-questions]]`.
