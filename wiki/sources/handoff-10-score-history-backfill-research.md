---
type: source
status: active
path: 10-score-history-backfill-research.md
lines: 92
dated: "2026-07-21"
verified: 2026-07-21
supersedes: []
superseded_by: []
created: 2026-07-21
updated: 2026-07-21
tags: [source, handoffs, backfill, research, unbuilt]
aliases: ["10 — Score history backfill (research)"]
---

# 10 — Score history backfill (research)

## Covers

Whether/how to backfill a player's score history from lowiro's tier-3
endpoints, retroactively improving b30's coverage for subscribed players.
**Status: research task, not a design.** Independent of handoff 09 (b30) —
b30 works today on accumulated rows; backfill only improves inputs.

## Key claims

- Two candidate endpoints, not to be conflated: `GET /webapi/score/rating/me`
  (1 request, server's own b30+r10 with a float `rating`, frozen at fetch,
  only 30 entries) vs. `GET /webapi/score/song/me/all` (~250 sequential
  requests, best score per chart + full note detail + `score_below_max`,
  survives a CC re-evaluation since we hold and re-rate the scores).
- Both endpoints are **tier 3 only** (Arcaea Online subscription) — never
  covers the friend path or free credentialed users. An upgrade for a subset,
  not a fix for the model.
- Three genuinely open questions: (1) failure mode for an unsubscribed
  account on these routes (untested — likely 403, possibly a `success: false`
  envelope), which is "the only thing gating a correct fallback path"; (2)
  whether the project even has subscribed users beyond the owner, given <50
  users total; (3) whether `song/me/all` is a play log or a per-chart record
  — graded **DISPUTED** in [[arcaea-auth-behavior]] §7.5 (Tier 2,
  outside this ingest). For b30 specifically this ambiguity does not matter
  (either reading yields a valid best-score-per-chart source); it only
  matters for a future play-log feature.
- Any design must treat a backfill walk as a rate-limited, resumable
  background job, never a slash-command path, never re-walked on a poll —
  the opposite traffic shape from the poller's deliberately jittered cadence.
- `source` would want a third value (`'history'`) distinct from `'own'` to
  preserve provenance, fitting the existing `String(8)` column on
  `play_scores` — **verified** the column is `String(8)` in
  `src/coda/db/models/play_score.py`, so the constraint is real, not
  speculative.

## Contradicts / reversed by

None. This doc raises open questions rather than making claims another doc
disagrees with. It explicitly defers to [[arcaea-auth-behavior]]
§7.5 as authoritative on the wire behavior it discusses, rather than
overriding it.

## Feeds

`[[h-backfill-unsubscribed-failure-mode]]`, `[[h-backfill-worth-building]]`,
`[[h-song-me-all-log-vs-record]]`
