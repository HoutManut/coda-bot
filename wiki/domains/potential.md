---
type: domain
status: active
source: arcaea-potential.md
verified: 2026-07-29
grade: A
created: 2026-07-21
updated: 2026-07-23
tags: [domain, arcaea, potential, ptt]
---

# Potential

## Model

A player's skill rating (**PTT**) is the average of 40 **play ratings**, split into two pools:
**best-30** (b30, the 30 highest play ratings ever) and **recent-10** (r10, the best 10 out of a
rolling **recent-30 pool** of distinct charts — not literally the 10 most recent plays). Each
pool holds at most one entry per `(song_id, difficulty_class)`, but the *same* chart can occupy a
slot in **both** pools simultaneously — that's normal, not double-counting.

PTT is therefore **path-dependent**: a function of play history and order, not a snapshot of
best scores. Two players with identical best-ever scores can hold different PTT.

## Encoding

### Play rating

```
score >= 10,000,000              → cc + 2
9,800,000 <= score < 10,000,000  → cc + 1 + (score - 9_800_000) / 200_000
score < 9,800,000                → cc + (score - 9_500_000) / 300_000

result floored at 0 (never negative)
```

| Score        | Play rating |
|--------------|-------------|
| 9,500,000    | cc + 0.0    |
| 9,800,000    | cc + 1.0    |
| 10,000,000   | cc + 2.0    |

Verified against the old project's `coda/utils/utils.py`; current as of 2026-07-17. A chart with
an unknown CC (`rating<=0` — see [[catalog|Catalog]]) has **no computable play rating** — never
substitute 0, that is a different thing from "undefined". See [[d-unknown-cc-no-play-rating]].

### PTT composition

```
ptt = (sum(best_30) + sum(recent_10)) / 40
```

Always divide by 40, even when a pool is underfilled (decided, owner 2026-07-17) — unfilled
slots contribute 0, mirroring the game; a new player's PTT is faithfully low, not broken.

### Recent-30 pool admission (asymmetric)

| Play | Enters the pool? |
|------|-------------------|
| Hard-gauge loss (HP hit 0, terminated early) | **Never**, at any score |
| Completed, < 9,800,000 (AA or below) | **Always** — evicts oldest entry |
| Completed, >= 9,800,000 (EX/EX+) | **Only if it raises PTT** — otherwise discarded |

Consequence: an EX/EX+ play can never lower PTT; a weak play at AA-or-below always enters and can
push a good entry out.

**Discriminator for the hard-gauge exclusion is `clear_type == 0` AND `modifier == 2`** — never
`clear_type == 0` alone (that would wrongly drop full-length normal/easy-gauge track losts,
which enter the pool like any other completed play). Both fields are own-credentials only. See
[[d-hard-gauge-early-submit]].

**Replay semantics onto a chart already in the pool** (owner, live-tested 2026-07-23 via
`score/rating/me` before/after diffs — see method below): a **new chart** (not currently
occupying a pool slot) admits unconditionally on any completed play <9.8M, evicting the pool's
globally-oldest slot, matching the table above (`leaveallbehind`, a track_lost/normal-gauge play
scoring 0, entered clean and evicted `lamentrain`, dropping real PTT by 0.01 — math checks out:
`(12.735445 - 12.5) / 40 = 0.0059 → rounds to the observed 0.01`). An **already-pooled chart**
replayed with a *worse* play is a **no-op** — no rating change, no `time_played` change, no
eviction anywhere (`designant`, replayed twice at near-zero score, left its existing 12.959 entry
byte-identical both times). Cannot yet say the entry can never lower — only that a worse replay
on an already-pooled chart didn't, twice.

Still open, not yet tested:
1. Already-pooled chart + an **improvement** — refreshes `rating` only, or `rating` + `time_played`
   both? (The original open question — never actually exercised; every replay tested so far was a
   worse play.)
2. Already-pooled chart + worse play that's still **≥9.8M** — does "discard unless improvement"
   hold across the whole score range, or does the ≥9.8M band behave differently even when the
   chart's already pooled?
3. **New** chart scoring **≥9.8M** — does "only if it raises PTT" apply against the pool's weakest
   member (no chart-local baseline exists yet), or does a new chart bypass that check the way it
   bypassed it under 9.8M?
4. **Hard-gauge track_lost** (`clear_type==0` AND `modifier==2`) — the *only* clear_type-based
   exclusion this page documents, and it has never actually been exercised live, on a new or an
   already-pooled chart. Everything tested 2026-07-23 was `modifier==0` (normal gauge).
5. A **second independent eviction** on a different chart, to confirm FIFO-by-`time_played` holds
   generally and `lamentrain`'s eviction wasn't a coincidence (it was both true-oldest by
   `time_played` and the only eviction observed so far).
6. **Course-mode detection** — spun out to [[h-course-mode-ptt-detection]]. Course plays are
   documented (owner) not to count toward PTT at all, but no captured wire payload so far shows a
   distinguishing field, and it's a separate axis from the new-chart/already-pooled admission
   question above rather than an edge of it.

**Method**: `GET /webapi/score/rating/me` (tier-3/subscribed only, see
[[handoff-10-score-history-backfill-research]]) returns `recent_rated_scores` (10 entries) drawn
from the full 30-slot pool — snapshot before a play, play deliberately, snapshot after, diff. The
visible 10 is a *view* over the 30, so an eviction from the 30 can promote a previously-invisible
11th-ranked entry into view (`aishite`, rating 12.5, surfaced this way after `lamentrain` left) —
don't mistake a promoted-into-view entry for a newly-admitted one.

### PTT wire encoding

Arrives on friend/player objects as an integer **×100**:

```
1282 → 12.82
```

| Wire value | Meaning |
|------------|---------|
| `>= 0`     | PTT × 100 |
| `-1`       | Hidden |

Owner-verified 2026-07-17: a hidden player's PTT sends `-1` on **both** the friend view and the
account's own `/webapi/user/me`; the game shows `"--"`. `-1` is a sentinel, never let it reach
arithmetic — a naive ×100 decode renders `-0.01`. See [[d-ptt-hidden-sentinel]].

**Different scale from CC**, which is stored ×10 (see [[catalog|Catalog]]). PTT ×100, CC ×10 — an easy
bug, and the two fields are both named `rating` on their respective objects (`friend.rating` for
PTT vs. `song_difficulties.rating` for CC). See [[d-ptt-hidden-sentinel]].

## Traps

- **Unknown CC → no play rating, not 0.** A chart with a TBA/unknown CC (`rating<=0`) cannot
  enter either pool at all. See [[d-unknown-cc-no-play-rating]].
- **`-1` PTT means hidden, not "rating 0" and not "lowest possible".** Do not sort hidden
  players to the bottom as if rated 0. See [[d-ptt-hidden-sentinel]].
- **b30 works on any tier; r10 is impossible on the friend path.** Pool admission needs
  `clear_type` + `modifier`, both own-credentials only — there is no score-only threshold that
  distinguishes a hard-gauge loss from a legitimately low/high score. b30 survives structurally
  (it takes the max rating per chart, and a hard-gauge loss's naturally-low score is filtered
  out by that max); r10 does not. **Tier-1 recent tracking is dropped, not approximated**
  (owner, 2026-07-17). See [[d-r10-impossible-friend-path]].
- **Never correct/override/blend our computed PTT toward the server's `rating`.** The server
  value is a coarse (0.01-granularity) debug signal, not a correctness verdict — divergence from
  incomplete coverage is expected and not a defect to chase or alarm the user about.
- **Hidden PTT suppression belongs at the render boundary, never at ingest.** Tracking runs
  unchanged for hidden players; only passive surfaces (leaderboards, auto-posted embeds) suppress
  the value. A self-invoked `/b30` shows it — invocation is consent, and rating commands are
  self-only by design so that consent is structural. The suppression covers **every recoverable
  form** of the value on passive surfaces (a b30 average or a rating-sorted position both hand
  out the PTT), not just the literal `rating` field. Individual scores are always fine to show.
- **CC precision is not the limiter for higher-precision PTT display** — catalog CCs are exact
  facts at their stored ×10 granularity, not community estimates (owner, 2026-07-21). See
  [[catalog|Catalog]] §Encoding note. Any earlier "CC precision" hedge is stale; this page states the
  corrected position directly rather than repeating a hedge that no longer applies.

## Implementation status

b30's read side is **built** (2026-07-23): `B30Service.compute` in
[[scores]] (`src/coda/scores/b30.py`) computes it on demand, uncached, from
`play_scores` — see [[h-b30-cache-stores-sum]] for the backend-shape
decision and [[handoff-09-b30]] for the original algorithm design. No `/b30`
command or embed yet. r10/PTT (this whole page otherwise) remain unbuilt.

## Source

[[arcaea-potential]] — authoritative and more detailed than this page. See
[[arcaea-potential]] (source page).
