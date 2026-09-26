---
type: question
status: answered
blocks: ["[[ownership|Ownership]] World Mode resolution"]
source: conversation 2026-07-29
created: 2026-07-29
updated: 2026-07-29
tags: [question, ownership, wire]
---
# How do `world_songs` ids on `/user/me` map to `song_id`?

## Why it was open

Original premise (now corrected): `world_songs` was thought to be a wholly different
namespace from `singles`/`packs`, needing an unmapped world-map-id → song-id table. That
premise was wrong — the real rule is simpler and was found by direct comparison, not by
sourcing a mapping table.

## What answered it

A live `/user/me` capture (`assets/me_sample.json`, gitignored) cross-referenced against
the live catalog DB (`songs.song_id`, `packs.pack_id`), 2026-07-29:

- `singles` (127 entries) and `packs` (58 entries): 100% match `song_id`/`pack_id`
  directly, zero misses.
- `world_songs` (144 entries): 94 match `song_id` directly; the remaining 50 all carry
  a trailing `3` and none of the 144 has any other non-matching shape. `3` is the
  `DifficultyClass` ordinal for BYD (`src/coda/db/enums.py:49-54`) — the suffix means
  **World Mode unlocked that song's BYD chart specifically**, not "the song again." Both
  paired (`goodtek` + `goodtek3`) and standalone (`fairytale3`, no bare `fairytale`
  entry) shapes are present in the capture.
- No `song_id` in the live catalog ends in a digit (checked against all 484 rows), so
  stripping a trailing ordinal digit to recover the base `song_id` is unambiguous.

## Answer

`world_songs` entries are `song_id`, optionally suffixed with a `DifficultyClass` ordinal
digit. No suffix = the song was granted (song-level). A suffix = that specific chart was
granted via World Mode — currently only observed as `3` (BYD). Whether ETR (`4`) or any
other ordinal ever appears this way is unconfirmed (not present in this capture), but the
owner states this sample contains all possible owned-value shapes currently reachable
in-game, so no further digits are expected under the current catalog.

This turned out to be chart-grained, not song-grained — it feeds directly into
[[h-passive-unlock-model-unsettled]] rather than closing independently of it: World Mode
BYD grants are a second wire-visible unlock source, alongside (not instead of) score-row
derivation.
