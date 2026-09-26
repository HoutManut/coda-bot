---
type: question
status: open
blocks: ["tournament module build"]
source:
created: 2026-07-30
updated: 2026-07-30
tags: [question, tournaments, unbuilt, brainstorm]
aliases: ["What should bracket + chart-ban tournament formats look like?"]
---

# What should bracket + chart-ban tournament formats look like?

## Why it is open

[[tournaments|Tournaments]] only models the **leaderboard/FFA** shape: one
round (chart + window), everyone scored against it, ranked. Nothing in the
domain page covers pairwise elimination brackets or player-facing chart
bans — both raised in a 2026-07-30 brainstorm as formats to aim for, distinct
from what's already designed. This page is that sketch: shapes pinned down
enough to build from later, not yet built, not yet formally decided the way
[[tournaments|Tournaments]]'s scoring-rule parameter is.

Both additions are pure Discord-side state — neither touches the
"tournament layer never calls the lowiro API" invariant ([[tournaments|Tournaments]] §Model).

## Bracket tree shape

Adds a `Match` entity above the existing `round`/`Game` primitive. A round
(chart + window, tie-break, `scoring_rule`) becomes one **game** inside a
match; a match resolves once one side wins `ceil(best_of/2)` games.

```
Match
  id, tournament_id
  bracket: WB | LB | GF
  round_number, slot
  participant_a, participant_b   (nullable until fed)
  winner_to_match_id, winner_to_slot
  loser_to_match_id, loser_to_slot   (null on LB matches — no third bracket)
  best_of: int
  state: PENDING | READY | BANNING | IN_PROGRESS | DONE
  winner_id

Game   (= existing round primitive)
  match_id, sequence_no
  chart_id, window_start, window_end, scoring_rule
  winner_side (a | b)
```

**Decisions made in the brainstorm:**

- **Best-of-N per match**, not single-round. A match owns N games; games can
  land on different charts.
- **Explicit pointers** (`winner_to_match_id`, `loser_to_match_id`), not
  round/slot arithmetic. Handles byes and irregular bracket sizes without
  special-casing the math.
- **True double elimination**, including bracket reset: the WB champion
  enters the grand final with zero losses. If the LB champion beats them in
  GF1, both sides are now tied at one loss and a second match (GF2) is
  created **lazily** — the only match in the whole tree not wired up front.

**Generation is a one-time build step at roster-freeze** (reuses the
existing invariant that the roster locks at `OPEN`, [[tournaments|Tournaments]] §State
machine). The entire match graph — every WB match, every LB match, the GF
placeholder — is built once at that moment: bracket padded to the next
power of 2, byes assigned to top seeds, LB routing computed via the
standard interleaved-round formula (well-known bracket-generator algorithm,
not something to invent from scratch, but non-trivial to hand-roll
correctly).

**Bye** = a match with one slot permanently null. Auto-resolves `DONE` at
generation time, no games played, winner propagates via `winner_to` only —
nothing goes to `loser_to` since there's no loser.

**Propagation**: on `Match.DONE`, `winner_id` writes into
`winner_to_match_id`'s slot; on a WB match, `loser_id` also writes into
`loser_to_match_id`'s slot. A match flips `PENDING → READY` once both its
slots are filled.

## Chart-ban phase shape

A pick/ban negotiation before a match's games are played — the first
player-facing *interactive configuration* step anywhere in the tournament
design (everything else reads `play_scores` passively).

```
BanPhase
  id, match_id
  scope: MATCH (upfront) | GAME (per-game)
  game_sequence_no        (null if scope=MATCH)
  pool: [chart_id]        snapshot at phase start
  turn_order: [participant_id]
  turn_index: int
  turn_deadline: timestamp
  status: ACTIVE | COMPLETE

BanAction
  ban_phase_id, actor_id (null if auto), chart_id, order_index, was_timeout: bool, at
```

**Decisions made in the brainstorm:**

- **Both ban cadences allowed, chosen at match/tournament creation**: upfront
  (ban down to exactly `best_of` charts before game 1, survivors assigned to
  games in ban-completion order) or per-game (ban from the remaining,
  already-played-excluded pool down to 1, immediately before each game).
- **Loser-priority turn order** for per-game cadence — whoever's behind
  after the previous game bans/picks first next. **Does not apply to
  upfront cadence**: banning all of a match's charts happens before any game
  is played, so there is no loser yet. Upfront cadence needs its own
  first-turn order (seed-based, same fallback used elsewhere) — this is a
  necessary reconciliation, not an open question, but flag if the seed-order
  fallback is wrong.
- **Random auto-ban on timeout.** Each `BanPhase` turn carries its own
  `turn_deadline`; on expiry the system bans a random remaining chart on the
  inactive player's behalf and advances the turn.

**Match state machine, revised** to insert banning between roster-fill and
play:

```
PENDING ──both slots filled──> READY
READY ──create BanPhase(scope)──> BANNING
BANNING ──phase COMPLETE──> IN_PROGRESS (game runs the existing round
                                          state machine unchanged)
  [scope=GAME only] game CLOSED, match undecided ──> BANNING (next game)
IN_PROGRESS ──majority reached──> DONE ──propagate──
```

**New machinery this needs that nothing else in the tournament design
needs today**: a per-turn timeout ticker independent of the score poller
(the poller reacts to plays; this reacts to *inaction*), and a live
Discord interaction surface (select-menu-per-turn, ephemeral to whoever's
turn it is) — the tournament layer's first prompt-the-player mechanism
rather than passive ingest.

## What would answer it

Pick one shape to build first (leaderboard/FFA is already fully designed
and unblocked; bracket and bans are both net-new). Bracket tree generation
and the ban-timer ticker are the two pieces of genuinely new machinery this
page identifies — either could be scoped as its own handoff once picked up.

## Current best guess

The shapes above are the brainstorm's pinned-down answer, not yet reasoned
against the shipped poller/db schema the way [[tournaments|Tournaments]]'s
core model was. Treat as a target, not a spec — re-open discussion before
building, per this vault's convention for sketch-stage pages.

## Answer

Not yet answered — not yet built.
