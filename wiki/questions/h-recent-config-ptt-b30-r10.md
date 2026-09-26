---
type: question
status: superseded
blocks: ["/recent rating-impact config"]
source: conversation 2026-07-23
created: 2026-07-23
updated: 2026-08-28
tags: [question, recent, potential, unresearched, pre-7.0]
aliases: ["Should /recent be configurable to show ptt/b30/r10 impact of a score?"]
---

# Should `/recent` be configurable to show ptt/b30/r10 impact of a score?

## Why it is open

Showing "this play moved your PTT by X" or "this cracked your b30" needs either
a live scan of full play history on each `/recent` call, or a maintained
running best30/best10 cache updated as new scores land. Neither exists yet —
current score storage shape (poll loop, both read paths) is built for
latest-score-per-chart tracking, not for rating-relevant history queries.
Unknown whether that shape is sufficient as-is.

Harder blocker: [[potential]] documents r10 as **impossible to reconstruct on
the friend path** ([[d-r10-impossible-friend-path]]) — tier-1 recent tracking
is dropped, not approximated. A config toggle that promises r10 impact has to
degrade differently depending on which read path produced the score, or it
silently lies on the friend path.

## What would answer it

- ~~Confirm current `play_scores` storage is enough to compute b30 on
  demand, or decide a running best30/best10 cache is needed (and who
  invalidates it).~~ **Settled 2026-07-23** — see below.
- Decide the friend-path degradation: omit r10 entirely, show "unavailable",
  or restrict the config option to owner/self-tracked accounts only.
- Reuse the existing consent rule from [[potential]] (self-invoke = consent,
  no passive exposure) rather than inventing new privacy rules for this
  config surface.

## Current best guess

r10 delta should probably be hard-restricted to the self/owner-consented
path and openly labeled unavailable elsewhere, matching the existing b30/r10
asymmetry rather than fighting it.

**2026-08-28: SUPERSEDED.** **DEV-STATED** (official `@arcaea_en` tweet,
[[arcaea-7.0-potential-notes]]): Arcaea 7.0 removed r10 from the potential formula. This
question's r10 half dissolves — there is no r10 impact left to gate or show, and no friend-path
degradation to design for it. The b30 half of this question (should `/recent` show a rating-
impact line at all, and how) is superseded by shipped work anyway: `b30_stat_line` in
`scores/b30_stat.py` (built 2026-08-10, [[h-b30-cache-stores-sum]]) already answers it for the
best-30 pool. A fresh version of this question may be worth filing once
[[h-7.0-potential-rework]] settles the best-50/top-10-doubled formula, since "which pool did
this play affect" is a real question again under the new shape — but it would be a new question,
not a reopening of this one.

## Answer

Superseded 2026-08-28, not separately answered. Its harder blocker (whether current storage is
enough) was resolved 2026-07-23 — `play_scores` needs no schema change,
`B30Service.compute` (`src/coda/scores/b30.py`) computes on demand, no cache — and its r10 half
is now moot per [[h-7.0-potential-rework]]. See that page for what remains open in the 7.0
formula, and `scores/b30_stat.py` for the `/recent`-adjacent rating-impact line that already
shipped for best-30.
