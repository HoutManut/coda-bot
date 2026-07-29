---
type: source
status: active
path: arcaea-score-mapping.md
lines: 109
dated:
verified:
supersedes: []
superseded_by: []
created: 2026-07-21
updated: 2026-07-21
tags: [source, arcaea, score-mapping, wire]
aliases: ["Arcaea — Wire Score → Catalog Chart"]
---

# Arcaea — Wire Score → Catalog Chart

## Covers

Authoritative on resolving a wire score's `{song_id, difficulty}` pair to a
`song_difficulties` row: the difficulty-int table, the two app-defined classes (`byd_2`, `err`)
and how they diverge from a naive lookup, the required resolution order, and why an unresolved
chart is routine rather than exceptional. Companion to `arcaea-scoring.md` and
`arcaea-domain-reference.md` §3.

## Key claims

- Wire `difficulty` ints map directly to `difficulty_class`: `0`=`pst`, `1`=`prs`, `2`=`ftr`,
  `3`=`byd`, `4`=`etr` — `4`=`etr` is **confirmed by capture** (`xterfusion`); the rest are
  domain knowledge, not independently wire-verified in this doc.
- `byd_2` and `err` have **no wire int** — they are app-defined, not game-native. See
  [[Score Mapping]].
- **Grading (verbatim from source)**: the `byd_2` separate-song-entry structure is
  owner-stated domain knowledge and matches seed data, but **the exact wire payload for a
  `lasteternity` play has not been captured** — the `difficulty: 3` assumption needs
  confirming the first time one is observed. This is an open verification gap, not settled
  fact. See [[d-byd2-game-song-id-resolution]].
- `err` charts are **never saved or exposed over the API** — no score will ever carry one; a
  score claiming an `err` chart is a bug in our code, not a case to handle.
- Resolution must try `song_difficulties.game_song_id = wire.song_id` (+ class match) **first**,
  falling back to `songs.song_id = wire.song_id` (+ `wire_int_to_class`) second — reversing the
  order silently drops every `byd_2` play. See [[d-byd2-game-song-id-resolution]].
- An unresolvable `song_id` (new song shipped before catalog reseed) is a **routine staleness
  signal** — log and surface the raw ID, never discard the score.
- `song_difficulties.note` (needed to decompose/verify a score) and CC (needed for play rating)
  both live **only** in the catalog — the wire never sends either. Catalog freshness is a
  correctness dependency of the score path, not just a display concern.

## Contradicts / reversed by

None against the other three sources. The difficulty-int table here (`pst`=0..`etr`=4)
independently confirms — does not contradict — the difficulty ID table in
`arcaea-domain-reference.md` §3.1.

## Feeds

[[Score Mapping]], [[d-byd2-game-song-id-resolution]]
