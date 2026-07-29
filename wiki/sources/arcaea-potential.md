---
type: source
status: active
path: arcaea-potential.md
lines: 433
dated: 2026-07-21
verified: 2026-07-21
supersedes: []
superseded_by: []
created: 2026-07-21
updated: 2026-07-21
tags: [source, arcaea, potential, ptt]
aliases: ["Arcaea — Potential (PTT)"]
---

# Arcaea — Potential (PTT)

## Covers

Authoritative on play-rating and PTT (potential) computation: the play-rating formula, PTT as
the average of 40 play ratings (b30 + r10), the recent-30 pool's asymmetric admission rule, the
wire PTT encoding (×100, `-1` = hidden), and the design implications for coda-bot's own
b30/r10/PTT tracker (planned, owner-decided 2026-07-17 through 2026-07-21). Game domain only.
Companion to `arcaea-scoring.md` (score) and `arcaea-domain-reference.md` (CC).

## Key claims

- Play rating: `score>=10M → cc+2`; `9.8M<=score<10M → cc+1+(score-9.8M)/200_000`;
  `score<9.8M → cc+(score-9.5M)/300_000`; floored at 0. **Verified against the old project's
  `coda/utils/utils.py`**, current as of 2026-07-17. See [[potential|Potential]].
- An unknown CC (`rating<=0`) yields **no computable play rating** — not 0. See
  [[d-unknown-cc-no-play-rating]].
- PTT = `(sum(best_30) + sum(recent_10)) / 40`. Neither pool holds two entries for the same
  `(song_id, difficulty_class)` — but the **same chart can occupy a slot in both pools
  simultaneously**, which is normal, not double-counting.
- Recent-30 pool admission is asymmetric: hard-gauge losses never enter; completed <9.8M always
  enters (evicts oldest); completed >=9.8M enters only if it raises PTT.
- **OWNER-STATED (2026-07-17)**: the recent-30-pool exclusion is *only* hard-gauge losses — the
  discriminator is `clear_type==0` **AND** `modifier==2`, never `clear_type==0` alone (that
  would wrongly drop full-length normal-gauge track losts). See
  [[d-hard-gauge-early-submit]].
- **UNKNOWN (unresolved in source)**: replay semantics onto a chart already in the pool — whether
  it refreshes recency or can lower the entry. Filed as a question, not guessed.
- PTT arrives ×100 (`1282` → `12.82`); `-1` = hidden (owner-verified 2026-07-17). A different
  scale from CC's ×10. See [[d-ptt-hidden-sentinel]].
- **b30 works on any tier; r10 is impossible on the friend path** — pool admission needs
  `clear_type`+`modifier`, both own-credentials only, and there is no score-only threshold that
  infers a hard-gauge loss. b30 survives because it takes the max play rating per chart, and a
  hard-gauge loss's naturally-low score is filtered out by that max. See
  [[d-r10-impossible-friend-path]].
- Hidden PTT policy (owner, 2026-07-17): keep ingesting/computing for hidden players always;
  suppress on passive surfaces (leaderboards, auto-posts); show only on self-invoked rating
  commands (`/b30`), which are self-only by design so consent is structural.
- **§7 precision note (owner, 2026-07-21) — supersedes any "estimate" framing**: catalog chart
  constants are accurate, full stop. "CC is not the limiter" for the planned 5-significant-digit
  PTT display. Per the project's standing memory (`catalog CC is fact`), any earlier hedge about
  CC precision is stale — this source's own current text already states the corrected position,
  so there is nothing left to override on the page derived from it. See [[potential|Potential]] §Traps.

## Contradicts / reversed by

None against `arcaea-scoring.md` (cross-references and is internally consistent with it on the
hard-gauge discriminator) or `arcaea-domain-reference.md` (CC scale). Note the **field-name
collision**: this doc's `rating` (PTT, ×100, `-1`=hidden on friend/player objects) is a
different field from `arcaea-domain-reference.md`'s `rating` (CC, ×10, `<=0`=unknown on
`song_difficulties`). Not a contradiction between the sources — both are internally correct —
but the shared name is a real cross-source trap. See [[d-ptt-hidden-sentinel]].

## Feeds

[[potential|Potential]], [[d-ptt-hidden-sentinel]], [[d-unknown-cc-no-play-rating]],
[[d-r10-impossible-friend-path]], [[d-hard-gauge-early-submit]]
