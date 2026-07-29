---
type: question
status: open
blocks: []
source: arcaea-bot-db-schema.md
created: 2026-07-21
updated: 2026-07-21
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

Not yet answered.
