---
type: flow
status: active
entrypoint: coda.catalog.chart_resolution.resolve_chart — called by poller._store and reconcile
touches: [scores, catalog, db]
created: 2026-07-22
updated: 2026-07-22
verified: 2026-07-22
grade: A
tags: [flow, catalog, scores, wire]
aliases: ["Chart Resolution", "chart-resolution"]
---

# Chart Resolution

Wire `(song_id, difficulty)` → `song_difficulties.id`, plus the backfill pass that
retries the misses. The mapping itself is documented in
[[score-mapping|Score Mapping]]; this page is the *path* and its ordering rules.

## Trigger

Two callers, one function (`src/coda/catalog/chart_resolution.py:24`):

- **Inline** — `poller._store` resolves every observed play before `ScoreStore.ingest`,
  setting `ScoreResult.difficulty_id` (`poller.py:250`).
- **Backfill** — `reconcile.run_reconcile_loop` (`scores/reconcile.py:51`) re-runs it
  over rows with a NULL FK, at startup and every `RECONCILE_INTERVAL = 300 s`. Started
  as a background task in `bot.py:54`.

## Path

1. **Step 1 — consolidated entry, by `game_song_id`.**
   `SELECT id FROM song_difficulties WHERE game_song_id = <wire_song_id>`.
   Only consolidated rows carry a `game_song_id`, and each is single-chart in-game, so
   the match is unique. Hit ⇒ return.
2. **Step 2 — normal chart.** `DifficultyClass.from_ordinal(wire_difficulty)`; an int
   outside 0–4 returns `None` (nothing legitimate maps there). Then
   `WHERE song_id = <wire_song_id> AND difficulty = <class>`.
3. Miss ⇒ `None`. **Routine, not an error.**
4. Caller stores the play regardless, FK NULL.
5. `reconcile` later re-runs steps 1–2 over exactly the NULL rows and fills what the
   catalog can now answer; returns the count backfilled.

## Ordering constraints

- ⚠️ **`game_song_id` must be matched FIRST.** A consolidated entry like Last | Eternity
  arrives on the wire as `song_id: "lasteternity"` — a value present in no `songs` row
  of ours. Reversed, it falls through the normal lookup and **silently drops a real
  play**.
- ⚠️ **Step 1 must NOT filter on the wire difficulty int.** `byd_2` arrives as int `3`
  (`byd`) while the row's class is `byd_2`, so a difficulty guard excludes the very row
  the step exists to catch. See [[d-byd2-game-song-id-resolution]].
- **`reconcile` is the sole writer of this FK after first insert** —
  `ScoreStore._upsert` omits `song_difficulty_id` from its `DO UPDATE` set, so there is
  no write contention with the poller.
- **`reconcile` touches NULL rows only** — never re-resolves an already-set FK.

## Failure modes

| Failure | Where it surfaces | User-visible result |
|---|---|---|
| Song shipped in-game before our seed | `resolve_chart` → `None` | Play stored, FK NULL; embed drops song name / jacket / rating and shows `_UNRESOLVED_NOTE` |
| Our `song_id` drifted from the game's | same | same — a routine staleness signal, fixed by a catalog edit, then reconcile |
| Wire difficulty int outside 0–4 | `from_ordinal` → `None` | Same NULL FK path |
| Chart deleted from the catalog | FK is `ondelete="SET NULL"` | Rows **re-orphan to NULL** and the next reconcile pass picks them up on its own — no separate invalidation |
| Reconcile pass raises | `run_reconcile_loop:59` logs and retries next interval | Backfill delayed 300 s; nothing lost |

## Self-healing property

Because a miss is stored rather than dropped, and because delete re-orphans to NULL,
the catalog can be fixed *after* the fact and history repairs itself within one
reconcile interval. This is why an unresolved chart must never raise, and why a play is
never discarded for failing to resolve.

## Related

[[scores]] · [[score-poll-loop|Score Poll Loop]] · [[score-mapping|Score Mapping]] ·
[[catalog|Catalog]] · [[d-byd2-game-song-id-resolution]] ·
[[d-level-cc-sentinel-values]] · [[db]]
