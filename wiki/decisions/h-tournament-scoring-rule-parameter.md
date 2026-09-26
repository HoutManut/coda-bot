---
type: decision
status: active
date: 2026-07-30
reverses:
created: 2026-07-30
tags: [decision, tournaments, scoring]
aliases: ["Scoring rule is a per-tournament parameter"]
---

# Scoring rule is a per-tournament parameter, not a fixed policy

## Context

A tournament round needs a rule for which of a player's scores counts inside
the open window: `2t` gives room for more than one attempt on short songs
([[tournaments|Tournaments]] — attempt overhead). Three candidate rules exist:

- **first** — the player's first valid score in the window counts.
- **best** — the player's highest valid score in the window counts.
- **last** — the player's most recent valid score before close counts.

## Alternatives

| Option | Why not |
|---|---|
| `last`-counts | Makes instant exit (submit garbage, leave) the strictly dominant strategy — nobody asked for this and it rewards giving up, not playing. Not offered. |
| Fix one rule bot-wide | Denies organizers a real tradeoff: `first` rewards a single clean run and makes hard gauge a trap; `best` makes retrying free and rewards whoever can grind fastest. Different tournaments want different pressure. |

## Decision

```
scoring_rule: "first" | "best"        DEFAULT: "first"
```

Both `first` and `best` ship as a per-tournament config parameter. `last` is
not offered.

| | `first` (default) | `best` |
|---|---|---|
| Counts | each player's first valid score | each player's highest valid score |
| Retrying | pointless | strictly free |
| Instant exit on all-scored | provably lossless | legitimate, but a rule (denies improvement) |
| The `2t` window is | a forfeit timeout | a real attempt budget |
| Hard-gauge loss | **locks in** ⚠️ | recoverable — just retry |

⚠️ **Under `first`, hard gauge is a trap and the player's own choice.** A
hard-gauge loss submits its score seconds in ([[scoring|Scoring]] §5); under
`first` that death is the player's first valid score inside the window, so it
counts and locks in. Normal and easy gauge cannot do this — HP hitting 0 costs
nothing on those gauges, so the play always runs to completion. Under `first`,
hard gauge is strictly self-harming and normal gauge is strictly safe — this
is a rule to tell players, not a bug to fix. It cannot be enforced on tier 1
(`modifier` is own-path only), detectable after the fact on tier 2+, not
preventable.

Under `best`, speed converts into attempts: retrying is free, so everyone
retries until the slowest player posts their first score. Fast players earn
extra tries — state it in the rules.

## Consequences

- Organizers pick the pressure they want per tournament; no bot-wide default
  fight.
- `first` needs the hard-gauge warning surfaced to players (rules text, not
  code) since the trap is undetectable pre-submission on tier 1.
- `best` needs the window (`2t`) sized with retries in mind, since it is a
  real attempt budget rather than a forfeit timeout.

## Enforced at

Not yet built. Design-only — see [[tournaments|Tournaments]] "Scoring rule —
a per-tournament parameter" and the state machine that reads `scoring_rule`.
