---
type: question
status: open
blocks: ["/recent rating-impact config"]
source: conversation 2026-07-23
created: 2026-07-23
updated: 2026-07-23
tags: [question, recent, potential, unresearched]
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

## Answer

Not yet fully answered — this question is about a `/recent` rating-impact
**config surface**, which is still unbuilt. But its harder blocker (whether
current storage is even enough) is resolved: `play_scores` needs no schema
change. `B30Service.compute` (`src/coda/scores/b30.py`, 2026-07-23) computes
b30 on demand, no cache, over the existing `ix_play_scores_account_chart_score`
index — see [[h-b30-cache-stores-sum]]. The r10 friend-path degradation
question and the actual `/recent` config UX remain open.
