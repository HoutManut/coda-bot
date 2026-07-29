---
type: domain
status: active
source: arcaea-score-mapping.md
verified:
created: 2026-07-21
updated: 2026-07-21
tags: [domain, arcaea, score-mapping, wire]
aliases: ["Score Mapping"]
---

# Score Mapping

## Model

Both score paths (own-credentials and friend) identify a chart with exactly two wire fields:
`song_id` (game-native string) and `difficulty` (int). Together they are the join key into our
catalog's `song_difficulties` table. Resolving that join correctly requires handling two
app-defined difficulty classes — `byd_2` and `err` — that have no wire representation of their
own (see [[Catalog]] §3.2).

## Encoding

### Wire example

```json
{ "song_id": "xterfusion", "difficulty": 4 }
```

### Difficulty int → class

| Wire | Class | Notes |
|------|-------|-------|
| `0`  | `pst` | |
| `1`  | `prs` | |
| `2`  | `ftr` | |
| `3`  | `byd` | |
| `4`  | `etr` | Confirmed by capture (`xterfusion`) |

`byd_2` and `err` are **ours, not the game's** — neither has a wire int.

### `byd_2` — arrives under a different `song_id`

The game has no second-Beyond slot. "Last | Eternity" is a **separate song entry** in the
game's data, `song_id: "lasteternity"`, carrying only its Beyond chart. Our catalog consolidates
it as a sibling row under `song_id = 'last'` with `difficulty = 'byd_2'` and
`game_song_id = 'lasteternity'`.

A Last | Eternity play therefore arrives on the wire as:

```json
{ "song_id": "lasteternity", "difficulty": 3 }
```

— a `song_id` that matches no `songs` row of ours, and `difficulty: 3` (byd), which is *not*
the class we store it under.

> **Verification status**: the game's separate-entry structure is owner-stated domain knowledge
> and matches seed data, but the exact wire payload for a `lasteternity` play **has not been
> captured**. Confirm the `difficulty: 3` assumption the first time one is actually observed.

### `err` — never appears on the wire

April Fools ERROR charts are **never saved or exposed over the API**. No score will ever carry
one. `err` rows exist for catalog/search display only — a score claiming an `err` chart is a bug
in our code, not a case to support.

### Resolution algorithm

```
1. match song_difficulties.game_song_id = wire.song_id
       AND the row's class maps to wire.difficulty
   → covers byd_2 (and any future consolidated entry)

2. fall back to songs.song_id = wire.song_id
       AND song_difficulties.difficulty = wire_int_to_class(wire.difficulty)
   → covers every normal chart

3. no match → unknown chart (log + surface raw song_id; do not discard the score)
```

**Step 1 must run first.** A `lasteternity` wire ID falling through to step 2 finds nothing and
silently drops a legitimate play.

## Traps

- **Naive `(songs.song_id, difficulty)` lookup misses every `byd_2` play** — the wire `song_id`
  for "Last | Eternity" (`"lasteternity"`) matches no row in `songs` at all, and the wire
  `difficulty: 3` collides with the *unrelated* `byd` class. See
  [[d-byd2-game-song-id-resolution]].
- **Resolution order is load-bearing** — checking `game_song_id` before `song_id` is not an
  optimization, it's correctness. Reversing the two steps drops `byd_2` plays with no error.
- **An unresolvable `song_id` is expected, not exceptional.** A new song can ship in-game before
  the catalog is reseeded. Log it and surface the raw ID; never discard the score — the seed can
  catch up later and the play still happened.
- **The wire never sends note count or CC.** `song_difficulties.note` (needed to decompose/
  verify a score — see [[Scoring]]) and CC (needed for play rating — see [[Potential]]) both
  live only in the catalog. Catalog freshness is therefore a correctness dependency of the score
  path, not just a display concern.

## Source

[[arcaea-score-mapping]] — authoritative and more detailed than this page. See
[[arcaea-score-mapping]] (source page).
