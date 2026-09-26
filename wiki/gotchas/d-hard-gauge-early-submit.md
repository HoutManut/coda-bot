---
type: gotcha
status: active
severity: high
area: wire
verified: 2026-07-17
created: 2026-07-21
updated: 2026-07-21
tags: [gotcha, scoring, potential, polling, sentinel]
aliases: ["A hard-gauge loss submits early — it's the only sub-song-length score, and the r10 exclusion needs BOTH fields"]
---

# A hard-gauge loss submits early — it's the only sub-song-length score, and the r10 exclusion needs BOTH fields

## Symptom

A polling loop tuned to "at least song-length apart" cadence misses a play; or the recent-30 pool
(r10 input, see [[potential|Potential]]) wrongly drops a full-length normal/easy-gauge track lost, or
wrongly admits a hard-gauge loss.

## Cause

_(OWNER-STATED, 2026-07-17.)_ On a hard gauge, HP reaching `0` ends the play **immediately** and
the score is submitted right then — seconds into the chart, not at song length. Every other
play, including a normal/easy-gauge track lost that simply finishes under 70 health, runs the
full song duration. Two consequences:

1. It is the **only** play that can appear in `recent_score` faster than a song's duration —
   which is exactly what makes "poll faster than the shortest song" a sufficient cadence for
   everything else.
2. It is the **only** play excluded from the PTT recent-30 pool. The discriminator is
   `clear_type == 0` **AND** `modifier == 2` — both fields are **own-credentials only** (see
   [[scoring|Scoring]]), so a friend-path consumer cannot identify one at all (see
   [[d-r10-impossible-friend-path]]).

## The wrong fix

1. Excluding the recent-30 pool entry on `clear_type == 0` alone. This is the specific trap the
   source calls out by name: `clear_type == 0` covers **every** track lost, including a full-
   length normal-gauge one that legitimately belongs in the pool. Excluding on `clear_type`
   alone silently drops legitimate plays from r10 tracking.
2. Assuming a "sub-song-length gap between plays" observed in polling means a missed poll or a
   bug in the poller — it can be the expected signature of a clear immediately followed by a
   hard-gauge death, which is the realistic way a poller *does* lose an entry if its cadence
   isn't fast enough to catch the gap between the two.
3. Sizing poll cadence off "average song length" instead of "fast enough to catch the
   clear-then-hard-death gap" — the former is the floor for every other play type, but the
   hard-gauge case is the argument for erring toward a faster cadence than that floor requires.

## The right handling

- Poll cadence faster than the shortest realistic song observes every completed play except the
  clear-then-immediate-hard-death sequence; favor a faster cadence specifically because of that
  gap, not a leisurely one.
- Recent-30 pool exclusion checks **both** `clear_type == 0` AND `modifier == 2` together, never
  `clear_type == 0` in isolation.
- Treat a hard-gauge loss's early score as a real, valid `recent_score` entry — it is not a
  partial/corrupt read.

## Regression signal

A recent-30/r10 computation missing a normal-gauge track lost that the player insists they
played; or a poller silently losing a clear that was immediately followed by a hard-gauge death
(visible only as a gap shorter than the poll interval).

## 2026-08-28 update

The poll-cadence half of this page (the hard-gauge early-submit timing itself) is unaffected by
Arcaea 7.0 and stays fully live. The r10-pool half (§Cause item 2, and the "`clear_type==0`
alone is wrong" warning as applied to *pool admission*) is now historical — r10 and the
recent-30 pool are DEV-STATED removed, see [[d-r10-impossible-friend-path]]. But the underlying
warning — never collapse "not track_lost" logic onto `clear_type == 0` alone without also
checking what it's being used for — is exactly the open question for 7.0's clear bonus: does
"obtaining a Clear" mean `clear_type != 0`, and does a hard-gauge clear (`modifier == 2`,
`clear_type` non-zero) count the same as a normal clear? Unconfirmed, tracked at
[[h-7.0-potential-rework]] §4.
