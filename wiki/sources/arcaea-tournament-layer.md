---
type: source
status: active
path: arcaea-tournament-layer.md
lines: 315
dated: "2026-07-17"
verified: 2026-07-17
supersedes: []
superseded_by: []
created: 2026-07-21
updated: 2026-07-21
tags: [source, tournaments, unbuilt]
aliases: ["Arcaea Tournament Layer — Implementation Doc"]
---

# Arcaea Tournament Layer — Implementation Doc

## Covers

The tournament module as a **consumer** of the API layer, not part of it:
rounds, validity windows, the scoring-rule parameter (`first`/`best`), the
state machine, cadence policy, tiers, and edge cases. Explicitly out of scope:
song ownership (§9, deferred to a manual list / handoff 11's sketch) and
PTT/rating (`arcaea-potential.md`). Status at capture: **design only, nothing
built.**

## Key claims

- The tournament layer never calls the lowiro API — it reads `play_scores`
  (already filling via the friend-path poll sweep) and declares hot windows
  the poller consumes. **Verified structurally sound** against the shipped
  poller design ([[arcaea-api-layer]] §7–§8, Tier 2) and the shipped
  `play_scores` table (`src/coda/db/models/play_score.py`) — both exist and
  match the assumption that scores are already arriving regardless of any
  tournament-specific fetch.
- `time_played` is server-assigned UTC ms, graded and verified 2026-07-17
  against [[arcaea-auth-behavior]] §7.3 — this is the entire
  integrity model for score validity (§2 of the source doc). **Grade: as
  cited in the auth doc; not re-verified by this ingest.**
- Scoring rule is a tournament parameter, `first` (default) | `best`; `last`
  is deliberately not offered. See [[h-tournament-scoring-rule-parameter]].
- Window duration `clamp(2t, 100s, 5m)`; `t=0` is a sentinel, floors
  regardless. See [[h-tournament-attempt-overhead]] for the one open input
  (attempt overhead) this formula depends on.
- Song ownership is **out of scope by decision** (owner, 2026-07-17):
  `pack_id`/`Song.world_unlock` do not encode whether a song is owned. This
  connects directly to [[handoff-11-ownership-blob]] (sketch only).

## Contradicts / reversed by

None found. This doc is internally self-consistent and consistent with the
shipped poller/`play_scores` schema it assumes exists. It predates and is not
contradicted by any handoff in this ingest.

## Feeds

[[tournaments|Tournaments]], [[h-tournament-clock-skew]],
[[h-tournament-attempt-overhead]], [[h-tournament-scoring-rule-parameter]]
(decision), [[h-no-catalog-inferred-ownership]] (decision),
[[h-ownership-blob-open-before-building]]
