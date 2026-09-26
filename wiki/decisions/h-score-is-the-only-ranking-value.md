---
type: decision
status: active
date: 2026-09-02
reverses:
created: 2026-09-02
updated: 2026-09-02
tags: [decision, tournaments, scoring, ux]
aliases: ["Raw score is the only value that decides a tournament; never play rating"]
---

# Raw score is the only value that decides a tournament; never play rating

## Context

Generalizing a round from one chart to a **chart set** ([[tournaments|Tournaments]] §2)
separates two questions the single-chart design could answer at once: which plays are
eligible, and how eligible plays are compared. Song mode makes the second question real —
a player on PST and a player on FTR both post a valid score, and something has to rank
them.

The obvious candidate was play rating: `calculate_play_rating(score, chart_cc, cleared=)`
(`src/coda/utils/scoring.py:159`) already ships, is a pure function of score and chart CC,
and needs no player history — so it would rank a first-time entrant fine. It normalizes
across difficulty by construction, which is exactly what song mode appears to want.

Rejected by the owner, 2026-09-02.

## Alternatives

| Option | Why not |
|---|---|
| Play rating | Depends on a catalog CC the bot maintains, which can be TBA (no rating computable at all) or simply refined later — so a result could change after the fact. Since 7.0 it also folds in a clear bonus that **tier 1 can only infer** ([[d-clear-bonus-impossible-friend-path]]), so the same play would rank differently depending on which path observed it. A competition may not have a rank that depends on how the bot happened to see the play |
| CC-delta handicap | Ad hoc, no better grounded than play rating, and harder to explain |
| Rank only within a difficulty group | Not a ranking — it is N separate rounds sharing a window, and it denies the premise that a song-mode room is one contest |
| Player PTT for seeding or handicap | Needs history the bot does not have for someone who registered for this tournament. Pool selection is the balancing lever instead ([[h-no-catalog-inferred-ownership]]) |

## Decision

**A round is won on raw `score`. Nothing else enters the comparison.** Ties break on
earlier `time_played`, on every tier.

A PST 9,900,000 and an FTR 9,900,000 are the same number and tie. This is intended, not an
approximation being tolerated — casual song mode mirrors the game's own multiplayer room,
where the room picks a song and each player picks their own difficulty.

## Consequences

- **A round is tier-agnostic.** Every field the rule needs — `score`, `time_played` — is on
  the friend path, so mixing tiers in one bracket is safe and "do not mix tiers" survives
  only for detail formats this rule currently rules out. See [[tournaments|Tournaments]] §7.
- **The result is legible.** A player reads the board and knows why they placed there. No
  column depends on a CC value or an inference.
- **The lowest difficulty in a pool is the rational pick**, since a high score is easier to
  post there. Song mode therefore has no built-in reason to choose a hard chart. Accepted:
  casual means people play what they enjoy. An organizer who wants the choice to matter
  picks charts of comparable CC — pool selection is the balancing lever, which is a reason
  for it to stay a deliberate organizer choice.
- **Any future format wanting accuracy, clear type, or gauge to decide a winner reverses
  this page**, and inherits the tier-2+ cost analysis in [[tournaments|Tournaments]] §7.

## Enforced at

Not built. Belongs in the results query — the ranking `ORDER BY` reads `play_scores.score`
and `play_scores.time_played` only, and must not join `song_difficulties.cc`.
