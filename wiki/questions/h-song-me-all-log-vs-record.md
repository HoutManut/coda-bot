---
type: question
status: answered
blocks: []
source: 10-score-history-backfill-research.md
created: 2026-07-21
updated: 2026-07-23
verified: 2026-07-23
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

**Verified 2026-07-23**, real subscribed account, browser-captured (`arcaea.lowiro.com` SPA
session against `webapi.lowiro.com`). Ran the exact experiment this page named: chart
`undyingmacula` diff `2`, already at a personal best, replayed for a strictly worse
attempt (same clear, worse would-be score on a fresh try). Before/after diff on that
chart's row in `score/song/me/all`:

```
score: 9973199        -> unchanged
score_below_max: ...   -> unchanged
shiny_perfect_count, perfect_count, near_count, miss_count, clear_type,
best_clear_type, health, time_played, modifier -> all unchanged
yearly_play_count: 4  -> 5   (only field that moved)
```

**Confirmed: one row per chart, kept as a running best — not a log.** The worse attempt
did not create a new row and did not touch the best-score fields; only the aggregate
play counter advanced. Matches [[arcaea-auth-behavior]] §7.5's guess exactly — that
page's grading can now drop from DISPUTED, cite this capture as the resolving evidence.

### Bonus: confirmed query/response shape while testing

```
GET /webapi/score/song/me/all?difficulty={1-4}&page={n}&sort={date|score|score_below_max|title}&term={search string, blank = no filter}

-> {"success":true,"value":{"scores":[...row...],"count":<total matches, unpaginated>}}
```

`count` reflects the full filtered set (e.g. `64` for one difficulty with no `term`);
pagination observed at page size 10 (pages 1/3/5/7 all returned data at `count:64`).
`term` matches on title (tested `"testify"`, `"last"` — both narrowed results). Useful
reference for [[Score history backfill]] pagination if it ends up walking this endpoint
directly rather than relying on `score/rating/me`'s b30/r10 shortcut.
