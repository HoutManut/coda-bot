---
type: decision
status: active
date: 2026-09-02
reverses:
created: 2026-09-02
updated: 2026-09-05
tags: [decision, tournaments, scoring, anti-cheat]
aliases: ["Every score inside the window counts; a hard-gauge death is a real score"]
---

# Every score inside the window counts; a hard-gauge death is a real score

## Context

A hard-gauge loss submits its score seconds into the chart ([[scoring|Scoring]] §5, and
[[d-hard-gauge-early-submit]]). That death is the player's first valid score in the
window, so it locks in — [[tournaments|Tournaments]] framed this
as a rule that "cannot be enforced on tier 1", since `clear_type`/`modifier` are own-path
only ([[d-clear-bonus-impossible-friend-path]]), implying the round would filter hard
deaths out if only it could see them.

Two candidate filters were considered and both were wrong for the same reason:

1. **Tier 2+:** discard a play where `is_hard_loss` (`src/coda/arcaea/dto/score.py:57`).
2. **Tier 1:** infer it from timing — a completed play cannot be submitted before
   `round.start + t`, so `time_played - start < t` implies a death or a pre-window start.

## Alternatives

| Option | Why not |
|---|---|
| Filter hard deaths on tier 2+, accept tier-1 blindness | **Creates the cheat it looks like it prevents.** A player who dislikes how a run is going kills it on hard, the round rules it "not a real attempt", and their next play becomes their first. Unlimited rerolls under the one rule whose entire purpose is that you get one attempt |
| Infer the death from `time_played` on tier 1 | Same exploit, reached with a different discriminator. Also fragile to clock skew ([[h-tournament-clock-skew]]) and cannot separate a death from a chart legitimately started before the window opened |
| Ban hard gauge in the rules and disqualify offenders | Unobservable on tier 1 at all, and post-hoc on tier 2+ — the score is server-side before the bot ever sees it. Enforcement is always discarding, so it reduces to the rows above |
| Minimum-score floor | Penalizes genuinely weak players, who are the people casual rounds exist for |

## Decision

**Take what the wire gives. Every score with a `time_played` inside the validity window
counts, whatever the gauge, clear type, or magnitude.**

A hard death and a very bad complete play produce the same artifact — a low number inside
the window — and both are real scores. The round never inspects *how* a play was earned.

Hard gauge remains a trap, and that is a **player-facing rule to state**, not
a bug to fix: normal and easy gauge always run to completion, so hard gauge is strictly
self-harming and normal gauge is strictly safe.

## Consequences

- **Discarding is the exploit.** Any future proposal to reject a play must
  first answer why it does not hand back a free retry. This is the general rule; hard gauge
  is only its most tempting instance.
- **Tier 1 loses nothing.** The rule never wanted `clear_type` or `modifier`, so the
  friend path's five fields are complete for it. This is what makes rounds tier-agnostic —
  see [[h-score-is-the-only-ranking-value]].
- **There is no mode where the question is inert.** It used to be answered twice — under
  `best` a death was just a discarded attempt, since retrying was free — but `best` is
  retired ([[h-first-score-is-the-only-rule]]), so this decision now covers every round
  the bot plays.
- The previous "unenforceable on tier 1" framing is **reversed**: there was never anything
  to enforce, so tier parity here is a property of the design, not a shortfall.

## Enforced at

Not built. Belongs in the validity predicate — `valid()` reads `song_difficulty_id` and
`time_played` only, and must never gate on `clear_type`, `modifier`, `health`, or `score`
magnitude.
