---
type: question
status: open
blocks: ["b30/r10 backend correctness", "score ingest"]
source: conversation 2026-07-23
created: 2026-07-23
updated: 2026-07-23
tags: [question, potential, scoring, unresearched]
aliases: ["How do we detect a play was made in course mode, so it can be excluded from PTT?"]
---

# How do we detect a play was made in course mode, so it can be excluded from PTT?

## Why it is open

Course-mode plays are documented (owner) not to count toward PTT at all — a
different rule from any admission logic in [[potential|Potential]], which all
assumes a normal single-chart play. No captured wire payload so far
(`before.json`, `flood_with_loses.json`, live testing 2026-07-23 — see
[[potential|Potential]] §Recent-30 pool admission) shows a course-specific
field, and `from_own_wire` (`src/coda/arcaea/dto/score.py`) parses only
`song_id, difficulty, score, time_played, perfect/near/miss/shiny, health,
clear_type, modifier, id` — nothing that obviously flags "this was a course."

If a course play lands in `recent_score` indistinguishable from a normal
play, the poller (`scores/poller.py`, `scores/service.py`) would ingest it
into `play_scores` like any other row, and it would silently enter b30/r10
computation despite the game itself excluding it from PTT — a correctness
gap in whatever replay/query engine ends up computing those pools.

## What would answer it

- Play a course, capture the raw own-tier `recent_score` entry immediately
  after (same before/after capture method used for the pool-admission
  testing), diff its fields against a normal single-song play.
- Two specific things to check:
  1. Does a course play even land in `recent_score` as a normal per-chart
     entry, or under a different shape entirely (e.g. not present at all,
     or a composite/aggregate record for the course's three songs)?
  2. `GaugeModifier.from_wire` (`src/coda/arcaea/dto/enums.py`) only maps
     `{0: NORMAL, 1: EASY, 2: HARD}` — does a course submission carry a
     `modifier` value outside that set? If so it currently logs
     "unrecognized modifier" and silently parses as `None`, which would be
     an accidental (undocumented) detection signal, not a designed one.

## Current best guess

None yet — no field has been observed that distinguishes a course play from
a normal one. Possible the exclusion happens entirely server-side (the play
never reaches `recent_score`/`recent_rated_scores` in the first place), in
which case no client-side detection is needed at all — but that itself is
unverified.

## Answer

Not yet answered.
