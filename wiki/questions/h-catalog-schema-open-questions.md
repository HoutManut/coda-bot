---
type: question
status: answered
blocks: []
source: arcaea-bot-db-schema.md
created: 2026-07-21
updated: 2026-07-23
tags: [question, catalog, schema]
aliases: ["What is still unresolved in the catalog schema design (`arcaea-bot-db-schema.md` §10)?"]
---

# What is still unresolved in the catalog schema design (`arcaea-bot-db-schema.md` §10)?

## Why it is open

The catalog schema (§1–8 of the source doc) is built and verified current
against the shipped models ([[db]]), but its own §10 lists four questions
that doc never resolves, none of which have a visible resolution in the
shipped schema either:

1. **Which fields have real-world difficulty-level overrides** beyond
   `name_en`, `jacket`, `aliases`? This validates (or invalidates) the
   nullable-column inheritance approach as sized correctly — every
   overridable column exists on `song_difficulties` today regardless of
   whether real data ever uses most of them.
2. **Should artist/charter entities be seeded from song data automatically**,
   or managed as a separate admin operation? The `artists`/`charters` tables
   and their alias/junction tables exist and are populated (per
   `src/coda/db/models/artist.py` / `charter.py`, read for this ingest), but
   the doc does not say — and this ingest did not verify — which path the
   seed/admin code actually takes.
3. **Similarity threshold values for search confidence** — `min_similarity`
   and `strong` on `difficulty_search_config` are seeded with placeholder
   values pending real test data, per the doc's own §3.12 table note
   ("Threshold values are placeholders to be tuned once test data is
   loaded"). Whether they have since been tuned was not checked.
4. **Should `packs.release_date` be derived from the earliest song in the
   pack, or managed independently?** `packs.release_date` exists as a
   nullable column (`src/coda/db/models/pack.py`) with no visible derivation
   logic checked in this ingest.

## What would answer it

Items 1, 3, 4 are catalog-content/tuning questions the catalog admin editor
owner can answer by inspecting live data. Item 2 is a design decision
answerable by reading `src/coda/catalog/seed.py` (Tier 1/module territory,
not read for this ingest) or asking whoever built it.

## Current best guess

Not attempted — these are catalog-content questions outside a persistence-
schema ingest's ability to answer from the schema alone.

## Answer

Queried the live dev DB (`song_difficulties`, 1794 rows) and read
`src/coda/catalog/seed.py`, `src/coda/admin/routers/entities.py` +
`presenters.py`, and the `d3f9a1c07b2e` migration directly.

1. **12 of 14 `OVERRIDABLE` fields see real use**: `name_en` (16), `artist`
   (11), `bpm`/`bpm_base` (6 each), `time` (14), `side` (1), `world_unlock`
   (7), `bg` (19), `date` (56), `version` (50), `jacket` (65),
   `jacket_designer` (22). Two never fire in current data: `name_jp` (0) and
   `remote_download` (0). Schema sizing is validated for 12/14 columns; the
   remaining two are either genuinely unused-so-far or dead weight — not
   determinable from data alone, worth asking whoever curates JSON source
   data whether either ever appears upstream.
2. **Seeded automatically, not a separate admin operation.** `seed.py::seed()`
   upserts `Artist`/`Charter` rows straight from `song.artist_ids` /
   `charter_ids` with `name == id` (see `_named_rows`, called before the
   `Song` upsert as an FK-ordering requirement). The admin editor only takes
   over curating names *after* bootstrap seeding — it never does the initial
   population. **Caveat (confirmed real, not hypothetical):** this is exactly
   why reseeding is bootstrap-only — a real incident produced duplicate
   artist/charter rows after ids were renamed via the admin editor's
   `_rename` (`entities.py:345`, a PK `UPDATE` relying on `ON UPDATE CASCADE`)
   and the seed was run again, resurrecting the original JSON ids as fresh
   rows. See [[d-reseed-duplicates-renamed-entities]].
3. **Never tuned — still exactly the migration's placeholder values.**
   `d3f9a1c07b2e` is the only migration touching
   `difficulty_search_config`, and no admin route or template edits it
   (`grep` for `search_config`/`min_similarity` under `src/coda/admin/` is
   empty). Live values: all of pst/prs/ftr/byd/etr/byd_2 share
   `min_similarity=0.4, strong=0.55, hidden_from_broad=false`; `err` is
   `min_similarity=0.85, strong=0.9, hidden_from_broad=true` with
   `af_suffixes = {af, err, error, "april fools"}`. Tuning these needs a
   real search-quality pass, not code archaeology.
4. **Managed independently — not derived.** `packs.release_date` is a plain
   admin-editable date field (`entities.py:685`, `pack_detail.html:14`),
   same treatment as `songs.date`: `presenters.py:139` states explicitly
   "`packs.release_date` is treated the same way" as a manual midnight-UTC
   date-picker edit. No derivation-from-earliest-song logic exists anywhere
   in `src/`.
