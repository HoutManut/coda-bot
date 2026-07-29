---
type: source
status: active
path: 09-b30.md
lines: 288
dated: "2026-07-21"
verified: 2026-07-21
supersedes: ["arcaea-potential.md §7 (CC precision hedge — reversed, see below)"]
superseded_by: []
created: 2026-07-21
updated: 2026-07-21
tags: [source, handoffs, b30, unbuilt]
aliases: ["09 — b30"]
---

# 09 — b30

## Covers

Design for computing, caching, and displaying a player's best-30 from
accumulated `play_scores` rows. **Status: computation backend built
2026-07-23** (`src/coda/scores/b30.py`, see [[h-b30-cache-stores-sum]] for the
final shape) — **display (a `/b30` command + embed) still not built.** Depends
on nothing unbuilt (the poller landed 2026-07-21). Feeds handoff 08's one
settled post filter.

## Key claims

- b30 is a pure function of best-ever scores — no r10, no pool ordering, no
  admission rules — and is monotone non-decreasing in score for a fixed CC,
  so max score per chart == max rating per chart. A missed poll delays b30,
  it never corrupts it. **Never call it PTT.**
- Rank in Python, not SQL; never store a per-play rating (matches
  `src/coda/db/models/play_score.py`'s own docstring rule, **verified**
  against source).
- Three exclusion cases needing opposite treatment: delisted (silent drop,
  matches the game), TBA/unrated (excluded, counted in a footer), unresolved
  chart (excluded, counted, self-heals after reconcile).
- Cache columns proposed on `arcaea_accounts`: `b30_sum`, `b30_entry_count`,
  `b30_computed_at`, `reported_rating`, `reported_rating_at`. Store the sum,
  not the average — keeps "divide by what" a display decision.
  **Rejected, not just deferred** — [[h-b30-cache-stores-sum]] (2026-07-23)
  decided on-demand compute over `play_scores` instead, at least until scale
  proves it too slow. `arcaea_accounts` carries none of these columns.
- `/b30` is self-only by design (no target option) — consent is structural,
  not an `is_owner` gate, because a non-owner link was explicitly approved at
  registration time.

## Contradicts / reversed by

> [!contradiction]
> §3 states plainly: *"The catalog's CCs are accurate (owner, 2026-07-21) —
> treat them as exact at the stored 0.1 granularity, not as estimates to
> hedge against."* This **reverses** [[arcaea-potential]] §7's
> precision-hedge framing (Tier 1, outside this ingest — not verified
> firsthand against that doc's exact wording here, but consistent with the
> vault owner's existing memory note "catalog CC is fact — CCs copied from
> game, not community estimates; `arcaea-potential.md` §7 precision hedge is
> stale"). **Direction**: this handoff wins per the vault's precedence rule
> (handoffs reverse the source docs by design). Flag [[arcaea-potential]] §7
> as `status: stale` on this specific point — the Tier 1 owner should update
> it; not done here since that file is outside this ingest's write scope.

§7's "divide by what" section clarifies rather than reverses
`arcaea-potential.md` §5's "always divide by 40" — that rule is scoped to PTT
with the game's own complete pools; b30's incomplete-by-construction pool is a
different situation the two docs do not actually disagree about.

## Feeds

[[scores]] (`b30.py`, built 2026-07-23), [[h-b30-cache-stores-sum]] (decision — cache
columns rejected, on-demand compute chosen instead), [[live-updates|Live Updates]]
(§8, the settled filter input)
