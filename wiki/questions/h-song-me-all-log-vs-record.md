---
type: question
status: open
blocks: []
source: 10-score-history-backfill-research.md
created: 2026-07-21
updated: 2026-07-21
tags: [question, backfill, wire, tier-3]
aliases: ["Is `GET /webapi/score/song/me/all` a full play log, or one row per chart (a personal-best record)?"]
---

# Is `GET /webapi/score/song/me/all` a full play log, or one row per chart (a personal-best record)?

## Why it is open

The original reading of this endpoint was "full play history" — every
attempt ever made. [[arcaea-auth-behavior]] §7.5 (Tier 2, not
re-verified in this ingest) flags that reading as **probably wrong** and
grades the question **DISPUTED**: `count: 495` for one difficulty is close to
the number of FTR charts in the game, and fields like `yearly_play_count` and
`best_clear_type` read as aggregates rather than per-attempt data — both
point toward "one row per chart, kept as a running best" rather than a log of
every play.

This question is raised independently in this ingest's source
([[handoff-10-score-history-backfill-research]]) because it
matters differently for backfill than it does elsewhere: **for b30 the
ambiguity is irrelevant** — b30 needs best-score-per-chart, and either a
per-chart record *is* that or a log's max *gives* that, so the endpoint is a
valid backfill source under either reading. It only matters for a
hypothetical future feature wanting a true play *log* (accuracy trends,
replaying the best-30 pool's history) — which is why it is tracked here as
open rather than blocking backfill's b30 use case.

## What would answer it

The cheap experiment named in `arcaea-auth-behavior.md` §7.5: replay a
chart already beaten, score *worse* than the existing best, and observe
whether a new row appears (log) or an existing one stays put / updates in
place (per-chart record).

## Current best guess

Leaning per-chart record, per the `count`/aggregate-field evidence in
`arcaea-auth-behavior.md` §7.5 — **their grade, not independently re-verified
here.**

## Answer

Not yet answered. Tracked in both this page and
[[arcaea-auth-behavior]] §7.5 (Tier 2) — resolve there first since
that doc owns the grading, then update this page to point at the answer.
