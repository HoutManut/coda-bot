---
type: source
status: active
path: arcaea-domain-reference.md
lines: 395
dated:
verified:
supersedes: []
superseded_by: []
created: 2026-07-21
updated: 2026-07-21
tags: [source, arcaea, catalog]
aliases: ["Arcaea — Game Domain Reference"]
---

# Arcaea — Game Domain Reference

## Covers

Authoritative on the Arcaea **catalog data model**: songs, difficulties (`pst`/`prs`/`ftr`/`byd`/`etr`
plus the app-defined `byd_2`/`err`), packs, artists/charters and their per-difficulty override
mechanism, sides, level encoding, chart-constant (CC) encoding, alias/search population, and
effective-value (inheritance) resolution. Pure game-data model — no bot behavior, no wire/API
shape. Companion to `arcaea-scoring.md` and `arcaea-potential.md`.

## Key claims

- Level stored as `game_level*2` (no `+`) or `game_level*2+1` (`+`); sentinels `0`=TBA,
  `-1`=`?` (err-only) — domain knowledge, not a wire capture. See [[Catalog]].
- Chart constant (`rating` on `song_difficulties`) stored ×10; sentinels `0`=TBA, `-1`=`?`
  (err-only) — same domain-knowledge status. See [[Catalog]]. Do not confuse this field with
  the differently-scaled player PTT field of the same name (`rating` ×100 on friend/player
  objects) — see [[d-ptt-hidden-sentinel]] and [[Potential]].
- `ftr` is the source of all song-level defaults (the `default` block); `level`, `rating`,
  `note`, `chart_designer` are always difficulty-specific and never inherited.
- Artist/charter links default to song level but can be overridden per-difficulty via
  `artists_overridden` / `charters_overridden` boolean flags — an *empty* overridden set means
  "explicitly unknown", not "inherit". Replacement is whole-set, never additive.
- `song_id` is always unique; `name_en` is **not** (Genesis, Quon collide) — a shared-name query
  must disambiguate rather than guess.
- "Last" is the only song with two Beyond charts; `byd_2` ("Last | Eternity") is app-defined —
  the game stores it as a **separate song entry** (`song_id: "lasteternity"`) that the app
  consolidates as a sibling difficulty row under `song_id: "last"`. Feeds directly into
  [[Score Mapping]] and [[d-byd2-game-song-id-resolution]].
- `err` (April Fools) charts store `level`/`rating` as `-1` and are hidden from broad search;
  some are later promoted to `byd`, which always wins in search over the surviving `err` row.
- Pack display name is stored **per song**, not on the pack entity — songs sharing a `pack_id`
  can show different `pack_name`; the per-song value is always authoritative.
- The `artist` display string is independent of the `song_artists`/junction IDs — it may use
  aliases or collaboration-unit names that don't literally match any linked artist's canonical
  name.

## Contradicts / reversed by

None found against `arcaea-scoring.md`, `arcaea-potential.md`, or `arcaea-score-mapping.md`.
The difficulty-int table implied here (`pst`=0 .. `etr`=4) is independently confirmed, not
contradicted, by `arcaea-score-mapping.md` §2's wire capture.

## Feeds

[[Catalog]], [[Score Mapping]], [[d-level-cc-sentinel-values]], [[d-byd2-game-song-id-resolution]]
