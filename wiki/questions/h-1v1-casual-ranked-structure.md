---
type: question
status: open
blocks: ["1v1 module build"]
source:
created: 2026-07-30
updated: 2026-07-30
tags: [question, unbuilt, brainstorm, tournaments]
aliases: ["What should the 1v1 casual/ranked match structure look like?"]
---

# What should the 1v1 casual/ranked match structure look like?

## Why it is open

The owner wants an in-between step before [[tournaments|Tournaments]]: a
standalone 1v1 mode (casual + ranked with Elo, matchmaking) that ships ahead
of the full tournament module. Nothing in [[tournaments]] or
[[h-tournament-bracket-and-ban-formats]] designs matchmaking or rating —
those pages assume a roster already exists (signed up for a tournament).
This page is the 2026-07-30 design session's sketch, same status as the
bracket/ban page: pinned down enough to build from, not yet built, not yet
reasoned against shipped schema.

Most of the *match-play* machinery is not new — a 1v1 reuses the `Match`/
`Game`/`BanPhase` primitives from [[h-tournament-bracket-and-ban-formats]]
almost unchanged (a 1v1 is a degenerate bracket: one `Match`, no WB/LB/GF
routing). What's genuinely new is matchmaking, Elo, and a replacement for
`best_of` game-counting: an HP-attrition match-end condition instead of
first-to-N-game-wins.

## Model

### Identity / Elo scope

Elo keys on `arcaea_account_id`, not `discord_id`. `current_account(db,
discord_id)` already enforces one Discord id → exactly one linked account, no
switching (see [[players]]) — an `ArcaeaAccount` can have multiple linked
Discord ids (alt accounts, same person), and that's fine: Elo belongs to the
account actually playing, regardless of which alt issued the command. No new
identity-locking concept needed.

Named `Elo`, not `Rating` — `rating` already means play rating/PTT
([[potential|Potential]]) elsewhere in this codebase; reusing the word here
would collide.

```
Elo
  arcaea_account_id (PK)
  elo: int, default 1200
  matches_played: int
```

Elo update, flat K=32 (no placement-period tiering — population too small at
[[coda-bot-scale-constraint]] to justify the bookkeeping), on `Match.DONE`,
**ranked only**:

```
E_a = 1 / (1 + 10^((R_b - R_a)/400))
R_a' = R_a + K * (S_a - E_a)      S_a ∈ {0, 1}, no draws (HP model always has a winner)
```

### Match entity

Shares the table tournaments will eventually use; bracket-only fields
(`winner_to_match_id`, `bracket`, `round_number`, ...) stay null for 1v1.

```
Match
  id, kind: CASUAL | RANKED, origin: CHALLENGE | QUEUE
  participant_a, participant_b   (arcaea_account_id)
  hp_a, hp_b: int, default 100
  state: PENDING → [BANNING, ranked only] → IN_PROGRESS → DONE
  winner_id

Game = existing round primitive (chart+window+scoring_rule, see [[tournaments]] §Encoding), plus:
  damage_to_a, damage_to_b   # one side always 0, unless exact tie
```

### Match end condition — HP attrition, not best-of-N

Chosen deliberately over best-of-N: each `Game` resolves to a final score for
both players (same `valid(score, round)` rule as tournaments, unchanged), and
the score differential becomes damage.

```
diff = |score_a - score_b|
if diff == 0: both sides take a small fixed chip damage (e.g. 1)   # guarantees the match can't stalemate forever
else: loser.hp -= diff / SCALE_CONSTANT
Match.DONE once either hp <= 0   # fixed HP=100, no game-count cap — pure attrition
```

`SCALE_CONSTANT` is deliberately **not fixed here** — Arcaea scores run
0–10,010,000 (PM=10,000,000 + shiny bonus), and whether a typical close game
(diff ~10–50k) should chip a few HP or a landslide (diff ~1M+) should
near-one-shot needs live-testing to tune, not a guess made at design time.

### Chart selection per game

| Mode | Mechanic |
|---|---|
| Ranked | `BanPhase(scope=GAME)` reused as designed in [[h-tournament-bracket-and-ban-formats]] — loser-priority turn order, random auto-ban on timeout. No upfront-cadence branch: HP model has no `best_of` to ban down to, so per-game is the only cadence that applies to 1v1. |
| Casual | Single pick, no ban negotiation — loser-priority (same ordering rule as ranked, one mental model across both modes), no full ban phase (too heavy for a quick casual match) |
| Both | Game 1 has no loser yet — falls back to the same seed/coinflip first-turn order [[h-tournament-bracket-and-ban-formats]] already flags as a necessary reconciliation for upfront cadence |
| Ranked pool exhaustion | Banning whittles the snapshot pool down; once 1 chart is left, stop banning and play it, repeating as needed until the match ends |

### Matchmaking — two entry paths, both feed the same `Match` creation

Deliberately **not** a search-range-expanding elo-gated queue — population is
under 50 people ([[coda-bot-scale-constraint]]), so gating pairing on rating
proximity has nothing to select from.

```
/challenge @user casual|ranked   → invite/accept → Match(origin=CHALLENGE)
/queue casual|ranked             → FIFO pool, pairs first 2 waiting, separate queues per kind, no elo-range gating
```

## Traps

| Case | Handling |
|---|---|
| Exact-tie games | Chip damage both sides (not zero) — otherwise two evenly-matched players could tie forever with no forced progress |
| Ranked chart pool exhaustion | Repeat the last remaining chart rather than expanding the pool or capping the match |
| Alt accounts | Elo attaches to the account, not the Discord id issuing commands — already correct by construction, no new enforcement needed |
| `SCALE_CONSTANT` | Do not hardcode a value from this design session — needs empirical tuning against real matches before ranked ships |
| Naming | `Elo` table, not `Rating` — `rating` is already play rating/PTT elsewhere ([[potential]]) |

## What would answer it

Pick `SCALE_CONSTANT` empirically (play test matches, tune until damage feels
right at HP=100). Everything else above is a decision already made in the
2026-07-30 session, not an open question — this page graduates to `decisions/`
once built, same as [[tournaments]]'s settled parameters did.

## Current best guess

The shapes above are this session's pinned answer. Treat as a target, not a
spec — re-open discussion before building, per this vault's convention for
sketch-stage pages (same caveat [[h-tournament-bracket-and-ban-formats]]
carries).

## Answer

Not yet answered — not yet built.
