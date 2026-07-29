---
type: domain
status: active
source: Tenniel prototype (`classes/chardle.py`, `plugins/chardle.py`, 2024-09/10, archived outside this repo) + design session 2026-07-27
verified: 2026-07-28
created: 2026-07-27
updated: 2026-07-29
tags: [domain, chardle, game]
aliases: ["Chardle"]
---

# Chardle

**Status: BUILT 2026-07-27.** `src/coda/chardle/`, the three tables (migration
`a97f24335635`) and `/chardle` all exist. The renderer is the **emoji/text** option
from [[h-chardle-board-rendering]], shipped as the temporary frontend. A working
prototype shipped in the **Tenniel** bot (2024), and this design was revived from
reading it — see [[chardle-mechanics|Chardle — Mechanics]] §Prototype provenance. Module
shape lives in [[chardle-module|chardle (module)]].

> [!note] Split 2026-07-29
> This page passed the vault's 300-line soft threshold (`meta/lint-report-2026-07-29.md`)
> and was split into three sub-pages: [[chardle-clue-columns|Chardle — Clue Columns]]
> (column set, feedback rules, jacket/duplicate-title identity), the Discord surface
> [[chardle-discord-surface|Chardle — Discord Surface]] (channel, daily scoreboard, board
> location/transport), and [[chardle-mechanics|Chardle — Mechanics]] (answer pool, stats,
> rules, prototype-comparison table). This page keeps the model overview, build notes, and
> cross-references.

**The board currently renders in DEBUG mode, which reveals the answer.** The
compact emoji grid proved unreadable without column labels, so `board_embed`
takes a `debug` flag that spells every column out as `value → answer value`. It is
the scoped setting `chardle_debug_board`, **default `on`** — turn it off with
`/run config set chardle_debug_board off` before anyone plays for real. The compact
grid and the share string are unchanged underneath.

> [!note] Iteration 2 — 2026-07-27
> Added after first use: a guild **Chardle channel** (`/chardle channel`, admin) that parents
> every thread and hosts a **daily scoreboard**; a `thread:` option on `/chardle play`;
> standalone **Beyond** and **Eternal** tiers; and **anyone may end a board 15 minutes after
> it started**. Daily thread reuse was reported broken and now reads an explicit
> `chardle_player_threads` row instead of inferring one from session history — see
> [[h-chardle-boards-are-channel-owned]].

> [!note] Iteration 3 — 2026-07-28
> End-to-end review. The clue-column selector was dropping `charter` on **every** tier and
> `artist` on all but `byd`, over a handful of charts with no links, which also pinned board
> shape to 4 possibilities per tier — see [[d-chardle-dead-clue-columns]] §The
> over-correction that shipped first. Fixed, and pinned by `tests/test_chardle_columns.py`.
> Also fixed: the free-play board's post now answers instead of throwing when the bot cannot
> send in the channel; the sweep re-renders the boards it loses; duplicate-title detection
> reads per-difficulty name overrides; the two `Asia/*` UTC+7 defaults are one zone.

Two things the build changed, both verified against the live catalog:

- **An err puzzle keeps its `bpm` column.** [[chardle-mechanics|Chardle — Mechanics]] §err
  measured `bpm_base` on the *chart* row (2 of 7 set). Every err chart inherits its song's
  BPM, so the **effective** value is real on all 7 and the column carries information. The
  variance rule in [[d-chardle-dead-clue-columns]] drops `level` and `rating`
  unaided; `bpm` survives it correctly. It does **not** keep `charter` or `side`:
  all seven err charts override their charters to empty, and all seven are
  Conflict-side, so an err board runs 5 columns.
- **`/chardle end` is permitted to anyone who has guessed on the board**, not to
  whoever started it. The ownership `CHECK` forces `discord_id IS NULL` on a
  channel-owned session, so the schema records no starter — the original rule is
  not expressible without a `started_by` column.

## Model

Chardle is Wordle over the Arcaea catalog. The game picks one **chart** (a song +
difficulty); the player guesses **song names**; each guess renders as a row of **clue
columns** with green / yellow / red feedback and, on ordered clues, an up/down arrow.
Clue-column mechanics are covered in full on
[[chardle-clue-columns|Chardle — Clue Columns]].

The puzzle's **difficulty is revealed** up front. The player guesses songs only; the
puzzle's difficulty is forced onto every guess. A song that lacks that difficulty is an
*invalid* guess, not a wrong one.

One pool qualifies that: the **extras** pool reveals only "Extra", never which of
`byd`/`etr`/`byd_2` it is — see [[h-chardle-extra-pool-hides-class]].

### Modes

Three modes, one shared engine. They differ only in how the puzzle row was created —
see [[h-chardle-puzzle-rows-not-modes]].

| Mode | Puzzle | Session owner | Attempts | Stats |
|---|---|---|---|---|
| **Daily** | one per `puzzle_number`, global | one user | **6, fixed** | streak + distribution + leaderboard |
| **Free play** | rolled on demand | the channel | free, or bounded by `attempts:` | none |
| **Custom** | rolled on demand, filtered | the channel | free, or bounded by `attempts:` | **ineligible by construction** |

**A free-play board is owned by its channel, never by the player who started it** — see
[[h-chardle-boards-are-channel-owned]]. Anyone in the channel may guess, and solo play
comes from *where* the board runs rather than from a permission check: a DM holds one
human, so a board there is private, and a thread has its own channel id, so it is a
private board inside a guild.

A bounded board shares **one attempt pool** across everyone in the channel — one board,
one budget, collaborative — and can be **lost** when the pool empties. Guesses record who
made them, for attribution only.

There is no separate "race" mode. A shared board is free play run somewhere with other
people in it, and a shared budget is `max_attempts` set on the puzzle.

**Custom is free play with filters**, not a third command: `/chardle play level:9 side:light`.
Only dailies are user-owned, and a free-play board can never point at a daily
puzzle — that combination would let a channel solve the daily collectively and leave every
participant free to log a solo 1/6.

### Where a board lives, and what it draws from

The Chardle channel, the daily scoreboard, and the transport chain a board falls back
through (thread → DM → ephemeral) are covered on
[[chardle-discord-surface|Chardle — Discord Surface]]. The answer pool, lifetime stats,
standing rules, and the Tenniel prototype-comparison table are covered on
[[chardle-mechanics|Chardle — Mechanics]].

## Related

[[chardle-clue-columns|Chardle — Clue Columns]] ·
[[chardle-discord-surface|Chardle — Discord Surface]] ·
[[chardle-mechanics|Chardle — Mechanics]] ·
[[chardle-module|chardle (module)]] · [[catalog|Catalog]] ·
[[h-chardle-puzzle-rows-not-modes]] · [[h-chardle-boards-are-channel-owned]] ·
[[h-chardle-puzzle-number-not-date]] ·
[[h-chardle-closest-match-always-costs]] · [[h-chardle-extra-pool-hides-class]] ·
[[h-chardle-err-is-an-event]] · [[d-chardle-dead-clue-columns]] ·
[[d-level-cc-sentinel-values]] · [[h-chardle-board-rendering]] ·
[[h-chardle-build-time-leftovers]]
