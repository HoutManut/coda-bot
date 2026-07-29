---
type: gotcha
status: active
severity: medium
area: catalog
verified:
created: 2026-07-23
updated: 2026-07-23
tags: [gotcha, catalog, seed]
aliases: ["Re-running the seed after admin renames/merges duplicates artists and charters"]
---

# Re-running the seed after admin renames/merges duplicates artists and charters

## Symptom

After the admin editor renames or merges an artist/charter id and `coda.catalog.seed` is
run again against the same `arcsongs.json`, the entity list shows two rows for what should
be one artist/charter — the curated id and a fresh row under the original JSON id, both
linked to the same songs.

## Cause

[[h-catalog-schema-open-questions|Q2 of the catalog schema questions]] establishes that
`seed.py::seed()` seeds artists/charters straight from the JSON's id lists
(`_named_rows`, keyed by `artist_id`/`charter_id`). The admin editor's `_rename` (see
`src/coda/admin/routers/entities.py:345`) changes that same primary key in place via
`UPDATE ... SET artist_id = new_id`, relying on `ON UPDATE CASCADE` (migration
`b3f1c2d4e5a6`) to repoint every FK. Once that runs, the DB's id no longer matches the
JSON's id for that entity. A second seed pass upserts `_named_rows` by `index_elements=[id_col]`
— the JSON's original id no longer conflicts with anything, so it inserts as a brand-new row,
and the `SongArtist`/`SongCharter` junction upsert (also keyed off `s.artist_ids` /
`s.charter_ids` straight from the JSON) links the song to *both* the curated row and the
resurrected original.

## The wrong fix

Deleting the duplicate row by hand after each reseed. It comes back the next time seed
runs, because the root cause is unconditional re-seeding against curated data, not a bad
row.

## The right handling

`SeedNotEmptyError` (`src/coda/catalog/seed.py`) refuses to run once the catalog has any
songs, specifically because reseeding "resurrects entities that were merged or renamed in
the editor" (see its docstring). Seed is bootstrap-only; once the admin editor owns the
catalog, `--force` is the only way to reseed, and that flag is for an intentional
re-bootstrap of an empty-by-intent catalog, not routine reruns.

## Regression signal

Two artist/charter rows with near-identical names/aliases both linked to the same song
after a seed run; or `--force` used against a catalog that already had admin-curated
renames/merges.
