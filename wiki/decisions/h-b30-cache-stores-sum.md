---
type: decision
status: active
date: 2026-07-23
reverses: ["handoff-09-b30.md §Key claims (proposed arcaea_accounts cache columns)"]
created: 2026-07-23
updated: 2026-07-23
tags: [decision, scores, b30, unbuilt-no-longer]
aliases: ["b30 backend: on-demand compute, no cache; configurable limit; source-agnostic"]
---

# b30 backend: on-demand compute, no cache; configurable limit; source-agnostic

## Context

[[handoff-09-b30]] designed b30's algorithm but left the read path open, proposing five
cache columns on `arcaea_accounts` (`b30_sum`, `b30_entry_count`, `b30_computed_at`,
`reported_rating`, `reported_rating_at`) without committing to them — the page's own
title for that section flags "designed, not built." This decision settles the shape of
the actual backend (`src/coda/scores/b30.py`, built 2026-07-23) and folds in three more
implementation questions raised in the same conversation: how far past 30 the result
should reach, what it returns for excluded charts, and whether it needs to know where a
score came from.

## Decision

**No cache, no migration.** `B30Service.compute(db, account_id, limit=30)` reads
`play_scores` fresh on every call — one query fetching `(song_difficulty_id,
wire_song_id, wire_difficulty, score)` for the account, reduced to a max-score-per-chart
dict in Python, then one `outerjoin(SongDifficulty, Song)` fetch for the resolved ids.
Both hit existing indexes (`ix_play_scores_account_chart_score`); at this project's
scale (<50 accounts) this is cheap enough that a cache would be solving a problem that
doesn't exist yet. If it ever does, the proposed columns in [[handoff-09-b30]] are still
there to revive — this decision rejects building them *now*, not the idea permanently.

**Configurable limit beyond 30, capped at 50.** The owner wants to see near-miss charts
just outside the real top-30, to know what to grind next (a "b40/b50" view). Every
returned `B30Entry` carries `counts_toward_b30: bool`; `b30_sum` is always computed over
the true top-30 regardless of what `limit` the caller asked for, so a `limit=50` caller
still gets a correct sum without knowing the cutoff itself. `_MAX_LIMIT = 50` is a plain
constant, not user-configurable — a defensive ceiling, not a product decision.

**Return exclusion counts alongside the entries.** `B30Result` carries
`tba_excluded_count` and `unresolved_excluded_count` so a future footer ("+2 unresolved,
self-heals after reconcile") doesn't need a second query. Delisted charts are the third
exclusion case from [[handoff-09-b30]] but are a **silent drop** — not counted anywhere,
matching how the game itself treats them.

**Source-agnostic.** The algorithm never branches on `play_scores.source`
(`'friend'`/`'own'`, and eventually `'manual'` per [[h-t0-manual-tier-b30]]) — max score
per chart treats every row the same regardless of how it was observed. This means the
b30 backend already works for manual/t0 rows the moment they exist; nothing in
`b30.py` needs to change when [[h-manual-score-import]] lands. What's still unbuilt is
how a t0 `ArcaeaAccount` row gets created at all (today `arc_user_id`/`friend_code` are
`NOT NULL` + unique) — that stays out of scope for this decision.

## Alternatives

| Option | Why not |
|---|---|
| Build the proposed cache columns now | No evidence yet that on-demand compute is slow at this scale. Would also need an invalidation story (poller ingest, catalog CC edits in admin) before it could ship — a second unit of work with no measured need. |
| Plain ranked list, no `counts_toward_b30` marker | Pushes the "which 30 actually count" knowledge onto every caller instead of computing it once where the rank is already known. |
| Uncapped `limit` | A pathological request does unbounded work for a feature whose real use case tops out around 50. |

## Consequences

- No migration shipped with this unit — `arcaea_accounts` is unchanged.
- A future cache, if ever justified, still has to decide invalidation triggers this
  decision never had to answer. Revisit then, not preemptively.
- `b30.py` requires no changes when manual/t0 scoring lands — only the row-creation path
  ([[h-manual-score-import]]) is new work.

## Enforced at

`src/coda/scores/b30.py` (`B30Service.compute`, `B30Entry`, `B30Result`).
