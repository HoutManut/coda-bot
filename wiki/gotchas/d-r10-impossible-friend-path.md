---
type: gotcha
status: superseded
severity: high
area: wire
verified: 2026-07-17
created: 2026-07-21
updated: 2026-08-28
tags: [gotcha, potential, wire, pre-7.0]
aliases: ["r10 cannot be reconstructed on the friend path — even approximately. b30 can."]
---

# r10 cannot be reconstructed on the friend path — even approximately. b30 can.

## Symptom

A tier-1 (friend-path-only) player gets an r10 or PTT figure computed and displayed, and it
quietly diverges from the game's in a way that isn't explainable by "we haven't seen every play
yet" — because on this path the tracker is running a fundamentally different admission rule than
the game, not merely a delayed one.

## Cause

A play rating needs only `score` + chart CC — both available on the friend path (see
[[potential|Potential]] §Encoding). But **recent-30 pool admission needs more**: excluding hard-gauge
losses requires `clear_type` **and** `modifier` (see [[d-hard-gauge-early-submit]]), and **both
fields are own-credentials only** (see [[scoring|Scoring]]). The friend path returns `score` and nothing
else about the play — there is no threshold on `score` alone that reliably distinguishes a
hard-gauge loss (scores low) from a legitimately bad clear (also scores low) or a legitimately
high-scoring-but-failed normal-gauge track lost (health < 70 at the end is legal at *any* score).

b30 is structurally immune to the same gap: it takes the **max** play rating per chart, and a
hard-gauge loss scores low by construction, so it's naturally filtered out by the max unless it's
a chart's *only* play — and even then it lands at a rating too low to reach a top-30 cut. r10 has
no equivalent self-correcting mechanism, because the very rule that makes b30 safe ("low score
loses to the max") is the opposite of r10's rule ("< 9.8M always enters").

## The wrong fix

Computing r10 on the friend path with the closest available approximation — e.g. "exclude scores
below some threshold" as a stand-in for the hard-gauge check. This isn't a *lagging* r10 (the
ordinary, acceptable kind of divergence described in [[potential|Potential]] §5 for missed plays); it is
a **different admission rule** than the game's, one that will admit hard-gauge losses lowiro
rejects and evict legitimate entries in their place. The source is explicit that this is not a
case to approximate: ordinary tracker drift is *missing data behaving correctly on what it did
see* — a threshold-based friend-path r10 is *wrong on data it did see*.

## The right handling

**Tier-1 recent tracking is dropped, not approximated** (owner, 2026-07-17). Compute and show
b30 on any tier. Gate r10 (and by extension any PTT figure that depends on it) behind tier 2+
(own-credentials). Do not offer a "best effort" r10 for friend-only players.

## Regression signal

An r10 or PTT value rendered for a player known to be tier-1 (friend-path only, no linked
credentials); a support report of "my recent shows something the game doesn't" that traces back
to a friend-path-derived recent-30 pool.

## 2026-08-28 update — SUPERSEDED

**DEV-STATED** (official `@arcaea_en` tweet, [[arcaea-7.0-potential-notes]]): Arcaea 7.0 removed
r10 from the potential formula entirely. This page's specific mechanism (r10's asymmetric
recent-30 admission rule, and the friend path's inability to see `clear_type`/`modifier`) is
retired along with it — there is no more r10 to reconstruct, on any path.

Kept, not deleted: the *reasoning* here is the direct ancestor of a live, unresolved question.
7.0 added a clear-status play-rating bonus (item 4 of [[h-7.0-potential-rework]]), and if that
bonus keys off `clear_type` the same way r10's admission rule did, the **replacement** best-50
pool inherits this exact gap — a different mechanic, the same "own-credentials-only field the
friend path structurally cannot see" shape. See [[potential|Potential]] §Traps for the current
framing of that open question.
