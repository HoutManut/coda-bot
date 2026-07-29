---
type: gotcha
status: active
severity: high
area: catalog
verified:
created: 2026-07-21
updated: 2026-07-21
tags: [gotcha, catalog, wire, score-mapping]
aliases: ["`byd_2` needs `game_song_id` and step order — a naive `(song_id, difficulty)` lookup silently drops it"]
---

# `byd_2` needs `game_song_id` and step order — a naive `(song_id, difficulty)` lookup silently drops it

## Symptom

A "Last | Eternity" (`byd_2`) play never appears in tracking — no error, no log line, the play
simply never resolves to a chart and is either dropped or misfiled as a `byd` play on the wrong
song.

## Cause

See [[Score Mapping]] and [[Catalog]] §"Last" — double Beyond. "Last | Eternity" is a **separate
song entry** in the game's own data (`song_id: "lasteternity"`), not a second difficulty row
under `"last"`. Our catalog consolidates it as a sibling `song_difficulties` row under
`song_id = 'last'`, `difficulty = 'byd_2'`, `game_song_id = 'lasteternity'` — but the *wire* score
for that play carries the game's native identifiers:

```json
{ "song_id": "lasteternity", "difficulty": 3 }
```

`"lasteternity"` matches no row in `songs` at all, and `difficulty: 3` maps to `byd` — a
completely different, unrelated class from `byd_2`. Both halves of a naive
`(songs.song_id, difficulty) → song_difficulties` join fail or, worse, silently resolve to the
wrong row if some other chart happens to share those coordinates.

## The wrong fix

1. Joining on `songs.song_id = wire.song_id AND song_difficulties.difficulty =
   wire_int_to_class(wire.difficulty)` as the *only* lookup path. This is exactly the naive join
   that misses `byd_2` — it never checks `game_song_id` at all, so a `lasteternity` play finds no
   `songs` row and is treated as unresolvable, or a code path with a permissive fallback might
   even coerce it toward the wrong `song_id`.
2. Checking `game_song_id` **after** the `songs.song_id` fallback instead of before. Since the
   fallback path fails cleanly (no match) rather than raising, code that runs both checks but in
   the wrong order still "works" for every normal chart and only breaks — silently, no
   exception — on the one case that needed the first check. This is the kind of ordering bug
   that will not surface in testing unless a `byd_2` play is specifically exercised.

## The right handling

Resolve in this order (see [[Score Mapping]] §Resolution algorithm):

```
1. song_difficulties.game_song_id = wire.song_id AND class matches wire.difficulty
   → covers byd_2 (and any future consolidated entry)
2. songs.song_id = wire.song_id AND song_difficulties.difficulty = wire_int_to_class(wire.difficulty)
   → covers every normal chart
3. no match → unknown chart (log + surface raw song_id, do not discard the score)
```

Step 1 must run first — it is not an optimization, it is the only path that can ever match a
`byd_2` play.

**Open verification gap** (from the source itself): the exact wire payload for a `lasteternity`
play has not been captured; the `difficulty: 3` assumption is owner-stated domain knowledge that
matches seed data but should be confirmed the first time a real one is observed.

## Regression signal

A "Last | Eternity" play reported by a user that never shows up in `/recent` or score tracking;
or, if the fallback path has a permissive coercion, a `lasteternity` play silently attributed to
the wrong song/chart instead of failing to resolve.
