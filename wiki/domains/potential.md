---
type: domain
status: active
source: arcaea-7.0-potential-notes.md
verified: 2026-08-31
grade: B
created: 2026-07-21
updated: 2026-08-31
tags: [domain, arcaea, potential, ptt, 7.0]
---

# Potential

> **7.0 rework, DEV-STATED 2026-08-28** ([[arcaea-7.0-potential-notes]], official `@arcaea_en`
> tweet): r10 removed, pool is now best-50 with the top 10 doubled, and a clear bonus was added
> to play rating. First-party confirmed at the mechanism level; **the `/60` divisor and clear-bonus
> magnitude (`+0.2`) are now live-wire confirmed (2026-08-31); the exact `clear_type` boundary for
> the clear bonus is still a working assumption, not confirmed** — tracked at
> [[h-7.0-potential-rework]]. **Ported to code 2026-08-31**: `src/coda/scores/potential.py` /
> `potential_stat.py` / `utils/scoring.py` now implement the model below — see §Implementation
> status. The unconfirmed `clear_type` boundary is encoded on exactly one line
> (`resolve_clear` in `utils/scoring.py`) rather than spread through the codebase, so closing
> that capture is a one-line change. Pre-7.0 material that the rework makes historical is kept,
> not deleted — see §Historical below.

## Model

A player's skill rating (**PTT**) is the average of **60** play ratings, split into two
overlapping pools drawn from the same best-ever-per-chart ranking: **best-50** (the 50 highest
play ratings ever) and its own **top-10**, counted a second time. Each pool holds at most one
entry per `(song_id, difficulty_class)`; a chart in the top 10 sits in both pools simultaneously,
which is normal, not double-counting — the same shape the pre-7.0 b30+r10 split had, just with
r10 replaced by "the best pool's own top slice" instead of an independent rolling window.

Because both pools are **best-ever**, not recent, **PTT cannot decrease from playing a chart**
(DEV-STATED design goal, "allowing for songs to be challenged without a decrease") — a play only
ever matches or improves a chart's entry. This is a direct consequence of dropping the old
recent-30 rolling pool (§Historical below), which was the only path-dependent, decreasable part
of the pre-7.0 formula; best-30 alone was already monotonic for the same reason. PTT is therefore
no longer path-dependent at all: it's fully determined by the best-ever score per chart (plus
whatever the clear bonus turns out to depend on — see §Encoding).

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

**7.0 clear bonus: magnitude confirmed flat `+0.2`, `clear_type` boundary still open**
(live-captured 2026-08-31, [[h-7.0-clear-bonus-investigation-plan]] Phase 0+1, own-credentials
`GET /webapi/score/rating/me`). Residual analysis (`actual_rating − (cc + base_formula(score))`)
against all 50 `best_rated_scores` entries came out to exactly `+0.200000` on every entry, no
exceptions — flat, not scaled by score, CC, or score-formula segment (confirmed across CC
10.7–12.0 and score spanning both formula segments). Held uniformly across every `clear_type`
*present* in that capture — `CLEAR`, `FULL_RECALL`, `PURE_MEMORY`, `HARD_CLEAR` — and across both
gauge modifiers present (`NORMAL`, `HARD`). Two identical scores can now carry different play
ratings depending on clear status, which the pre-7.0 formula never allowed. **Still open**: a
50-best pool structurally can't contain a `TRACK_LOST` (clear_type=0) or `EASY_CLEAR` (clear_type=4)
entry, and a 2026-08-31 attempt to capture a `TRACK_LOST`/`EASY_CLEAR` matched pair directly hit
two charts with unrated/TBA catalog CC ([[d-unknown-cc-no-play-rating]]) — inconclusive.
**Working assumption (owner, 2026-08-31, NOT live-verified)**: `TRACK_LOST → +0.0`,
`EASY_CLEAR → +0.2` (same as every other clear type). Provisional only — see
[[h-7.0-clear-bonus-investigation-plan]] for the full capture history and what a real Phase 2
would need. Do not treat `clear_type != 0` as confirmed in code without re-reading that page.

### PTT composition

```
ptt = (sum(best_50) + sum(top_10_of_best_50)) / 60         -- CONFIRMED 2026-08-31
```

By analogy with the pre-7.0 `(b30_sum + r10_sum) / 40 = 30 + 10` shape: 50 + 10 = 60. The tweet
stated the 50 and the doubled 10 but not the divisor; `/60` is now live-wire confirmed
(2026-08-31, [[h-7.0-potential-rework]] item 2) via a same-moment capture pair —
`GET /webapi/score/rating/me` (`best_rated_scores`, 50 entries) and `GET /webapi/user/me`
(aggregate `rating`) from the same account, same session. `(sum(all 50) + sum(top 10)) / 60 =
13.021390523…` against a wire `rating` of `13021` (→ `13.021` at ×1000) — exact match, and the
`/50` alternative (no doubling) computes `12.982`, ruling out coincidence. No before/after play
was needed: the account's own aggregate PTT served as the "after" value to check the formula
against.

The pre-7.0 "always divide by the full pool size, even underfilled" convention (owner,
2026-07-17) is assumed to carry forward unchanged — the confirming capture's account had ≥50
qualifying charts, so it couldn't exercise the underfilled case. Still inference, not
confirmation, for that specific edge.

### PTT wire encoding

Arrives on friend/player objects as an integer **×1000** (changed from ×100 by a lowiro
maintenance window on 2026-08-27 — the in-game display grew a third decimal the same day,
matching the same 7.0 rework, e.g. `209 → 0.209`):

```
12820 → 12.820
```

| Wire value | Meaning |
|------------|---------|
| `>= 0`     | PTT × 1000 |
| `-1`       | Hidden |

Owner-verified 2026-07-17 (scale re-verified 2026-08-27 against the ×1000 change): a hidden
player's PTT sends `-1` on **both** the friend view and the account's own `/webapi/user/me`; the
game shows `"--"`. `-1` is a sentinel, never let it reach arithmetic — a naive ×1000 decode
renders `-0.001`. See [[d-ptt-hidden-sentinel]].

**Different scale from CC**, which is stored ×10 (see [[catalog|Catalog]]). PTT ×1000, CC ×10 — an
easy bug, and the two fields are both named `rating` on their respective objects (`friend.rating`
for PTT vs. `song_difficulties.rating` for CC). See [[d-ptt-hidden-sentinel]].

This encoding (the scale, the `-1` sentinel) is orthogonal to the formula rework above and is
unaffected by it — a scale/sentinel fact about how the number arrives, not what the number means.

## Historical: pre-7.0 model (superseded, kept for provenance)

Everything in this section describes the formula **before** update 7.0 — r10 and the recent-30
pool no longer exist live (DEV-STATED, [[arcaea-7.0-potential-notes]]). Kept rather than deleted:
the replay-semantics testing below was real, correct research against a mechanic that was live
when it was done, and the reasoning it established (e.g. why b30 tolerated the friend path and
r10 didn't) is the direct ancestor of the open question 7.0 reopens for best-50 — see
[[h-7.0-potential-rework]] §4.

### The old formula

```
ptt = (sum(best_30) + sum(recent_10)) / 40
```

PTT was the average of 40 play ratings: **best-30** (b30, the 30 highest play ratings ever) and
**recent-10** (r10, the best 10 out of a rolling **recent-30 pool** of distinct charts — not
literally the 10 most recent plays). Always divided by 40 even when a pool was underfilled
(decided, owner 2026-07-17) — unfilled slots contributed 0, mirroring the game.

PTT was **path-dependent**: a function of play history and order, not a snapshot of best scores.
Two players with identical best-ever scores could hold different PTT — the property 7.0 removed.

### Recent-30 pool admission (asymmetric)

| Play | Enters the pool? |
|------|-------------------|
| Hard-gauge loss (HP hit 0, terminated early) | **Never**, at any score |
| Completed, < 9,800,000 (AA or below) | **Always** — evicts oldest entry |
| Completed, >= 9,800,000 (EX/EX+) | **Only if it raises PTT** — otherwise discarded |

Consequence: an EX/EX+ play could never lower PTT; a weak play at AA-or-below always entered and
could push a good entry out.

**Discriminator for the hard-gauge exclusion was `clear_type == 0` AND `modifier == 2`** — never
`clear_type == 0` alone (that would wrongly drop full-length normal/easy-gauge track losts,
which entered the pool like any other completed play). Both fields are own-credentials only. See
[[d-hard-gauge-early-submit]].

**Replay semantics onto a chart already in the pool** (owner, live-tested 2026-07-23 via
`score/rating/me` before/after diffs — see method below): a **new chart** (not currently
occupying a pool slot) admitted unconditionally on any completed play <9.8M, evicting the pool's
globally-oldest slot, matching the table above (`leaveallbehind`, a track_lost/normal-gauge play
scoring 0, entered clean and evicted `lamentrain`, dropping real PTT by 0.01 — math checked out:
`(12.735445 - 12.5) / 40 = 0.0059 → rounds to the observed 0.01`). An **already-pooled chart**
replayed with a *worse* play was a **no-op** — no rating change, no `time_played` change, no
eviction anywhere (`designant`, replayed twice at near-zero score, left its existing 12.959 entry
byte-identical both times). Could not establish the entry can never lower — only that a worse
replay on an already-pooled chart didn't, twice.

Left open when 7.0 shipped, never resolved (now moot for r10 itself, but the questions'
*reasoning* is what 7.0 reopens for best-50's own top-10 doubling):
1. Already-pooled chart + an **improvement** — refreshes `rating` only, or `rating` +
   `time_played` both? Never actually exercised; every replay tested was a worse play.
2. Already-pooled chart + worse play that's still **≥9.8M** — does "discard unless improvement"
   hold across the whole score range, or does the ≥9.8M band behave differently even when the
   chart's already pooled?
3. **New** chart scoring **≥9.8M** — does "only if it raises PTT" apply against the pool's
   weakest member, or does a new chart bypass that check the way it bypassed it under 9.8M?
4. **Hard-gauge track_lost** (`clear_type==0` AND `modifier==2`) — never actually exercised live,
   on a new or an already-pooled chart. Everything tested 2026-07-23 was `modifier==0`.
5. A **second independent eviction** on a different chart, to confirm FIFO-by-`time_played` held
   generally and `lamentrain`'s eviction wasn't a coincidence.
6. **Course-mode detection** — spun out to [[h-course-mode-ptt-detection]]. Course plays are
   documented (owner) not to count toward PTT at all; that question is independent of the
   formula rework and stays open regardless.

**Method**: `GET /webapi/score/rating/me` (tier-3/subscribed only, see
[[handoff-10-score-history-backfill-research]]) returned `recent_rated_scores` (10 entries) drawn
from the full 30-slot pool — snapshot before a play, play deliberately, snapshot after, diff. The
visible 10 was a *view* over the 30, so an eviction from the 30 could promote a previously-invisible
11th-ranked entry into view (`aishite`, rating 12.5, surfaced this way after `lamentrain` left) —
a promoted-into-view entry was not the same thing as a newly-admitted one. `score/rating/me`
still exists post-7.0 (confirmed 2026-08-31); it now returns `{ best_rated_scores: [...] }` (50
entries), and `recent_rated_scores` is gone as expected with r10's removal — see
[[h-7.0-potential-rework]].

## Traps

- **Unknown CC → no play rating, not 0.** A chart with a TBA/unknown CC (`rating<=0`) cannot
  enter the pool at all. See [[d-unknown-cc-no-play-rating]].
- **`-1` PTT means hidden, not "rating 0" and not "lowest possible".** Do not sort hidden
  players to the bottom as if rated 0. See [[d-ptt-hidden-sentinel]].
- **Best-50 is confirmed NOT friend-path-safe, the same shape of gap r10 had.** Pre-7.0, b30
  (never r10) was friend-path-safe because play rating was a pure function of `score` — r10's
  admission rule needed `clear_type`+`modifier`, own-credentials only, so it was dropped rather
  than approximated (see [[d-r10-impossible-friend-path]], now historical alongside r10 itself).
  The 7.0 clear bonus depends on `clear_type` the same way, and a live capture confirmed the
  friend wire carries no `clear_type` at all (2026-08-31, [[h-7.0-clear-bonus-investigation-plan]]
  Phase 4, `new_friend_res.json`) — so the *replacement* best-50 pool inherits r10's exact problem
  under a different mechanic. Confirmed, not just analogized. Filed as
  [[d-clear-bonus-impossible-friend-path]] (2026-08-31, ruling revised same day): tier-1 resolves
  clear status via a conservative score-threshold heuristic (`score >= 9,000,000` assumed cleared,
  wire data showing genuine high-score fails are rare in practice), with a per-row owner override
  for the cases it gets wrong — an honestly-labeled inference, not a strict lower bound and not an
  unlabeled guess. See that page for the full reasoning, including why both an unconditional
  no-bonus default and an unconditional assume-clear default were rejected first. See
  [[h-7.0-potential-rework]] §4.
- **Never correct/override/blend our computed PTT toward the server's `rating`.** The server
  value is a coarse (0.01-granularity) debug signal, not a correctness verdict — divergence from
  incomplete coverage is expected and not a defect to chase or alarm the user about.
- **Hidden PTT suppression belongs at the render boundary, never at ingest.** Tracking runs
  unchanged for hidden players; only passive surfaces (leaderboards, auto-posted embeds) suppress
  the value. A self-invoked rating command shows it — invocation is consent, and rating commands
  are self-only by design so that consent is structural. The suppression covers **every
  recoverable form** of the value on passive surfaces (a best-pool average or a rating-sorted
  position both hand out the PTT), not just the literal `rating` field. Individual scores are
  always fine to show.
- **CC precision is not the limiter for higher-precision PTT display** — catalog CCs are exact
  facts at their stored ×10 granularity, not community estimates (owner, 2026-07-21). See
  [[catalog|Catalog]] §Encoding note. Any earlier "CC precision" hedge is stale; this page states
  the corrected position directly rather than repeating a hedge that no longer applies.

## Implementation status

**Ported 2026-08-31.** `PotentialService.compute` in [[scores]] (`src/coda/scores/potential.py`,
renamed from `b30.py`) computes the full 7.0 model on demand, uncached, from `play_scores`:
best-50, its own top-10 summed a second time, `/60`, with the `+0.2` clear bonus applied per
entry. `PotentialResult.potential` is the PTT-scale figure; `pool_sum`/`top_sum` are exposed
separately. Naming went **model-neutral** rather than `b50` (owner, 2026-08-31) so the next
rework is a constant change, not a third rename.

Built alongside it:

- `utils/scoring.py` — `calculate_play_rating(score, cc, *, cleared)` (the kwarg is required,
  so no caller can inherit an answer silently), `CLEAR_BONUS`, `ASSUMED_CLEAR_SCORE`,
  `ClearBasis`/`ClearStatus`, and `resolve_clear`, which is the ONLY place the unconfirmed
  `clear_type` boundary is encoded.
- `play_scores.clear_override` (nullable bool, migration `1acd77155bd9`) — the per-row owner
  correction from [[d-clear-bonus-impossible-friend-path]]. Set from `/potential`'s review card;
  `scores/clears.py` is the only module that writes it.
- Config keys renamed with a data migration (`a5e0c91d7f34`): `recent_b30_stat` →
  `recent_b50_stat`, values `b30`/`b40` → `b50`/`b60`. Mandatory, not cosmetic — the settings
  read path never validates, so a stale value reaches `_MODE_REACH` and `KeyError`s.
- `tests/test_potential.py` pins the bonus, `resolve_clear` precedence, the `/60` divisor
  (including an underfilled pool), and the row-selection cascade from the gotcha's worked example.

The load-bearing structural change: the per-chart winner is picked by **resolved rating over
every stored row**, not `MAX(score)`. `best.py`'s `ORDER BY score DESC` stays correct for
`/score` display and must never feed the rating calc — its docstring now says so.

**UI shipped 2026-08-31**, closing both remaining halves. `/potential`
(`src/coda/extensions/potential.py`) lists the counted pool ten to a page — rank, chart, play
rating — headed by the figure at three fixed decimals, and carries the clear-review card behind
its own button. The board is **ephemeral by default**; the divisor breakdown and the `×2` marker
on the doubled top-10 were dropped as decoration. A board shared with `ephemeral: false` grows a
`Dismiss` button so its owner can delete it instead of leaving it in the channel.
`scores/clears.py` holds the queue filter (counted + tier-1 + unconfirmed) and the only writes to
`clear_override`. `PotentialEntry` gained `rank` so a surface never has to recompute a position it
was already handed.

`/potential` is **self-only and shows the figure unconditionally** — no `rating_visible` gate,
unlike `potential_stat_line`. That is the §Traps rule, not an oversight: suppression is for
passive surfaces, and invoking a self-only rating command *is* the consent.

Still **not** built: nothing from the rework. The remaining open item is the unconfirmed
`clear_type` boundary itself ([[h-7.0-clear-bonus-investigation-plan]] Phase 2), which is a
capture, not code.

## Source

[[arcaea-7.0-potential-notes]] — current (7.0) formula, DEV-STATED, mechanism-level only.
[[arcaea-potential]] — pre-7.0 source, superseded on the formula but still authoritative for
everything in §Historical above (the wire encoding, the play-rating base formula, and the
recent-30 research). See both.
