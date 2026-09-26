---
type: question
status: answered
blocks: [chardle]
source: design conversation 2026-07-30
created: 2026-07-30
updated: 2026-09-26
tags: [question, chardle, unbuilt, commands]
aliases: ["What should /chardle play's option set become?"]
---
# What should `/chardle play`'s option set become?

## Why it is open

Owner flagged three changes to `Play`'s options (`extensions/chardle.py:457-497`) in the same
conversation as [[h-chardle-shared-board-modes]]. Filed, not designed — no schema or option
shape decided yet.

Current options: `tier` (`difficulty`, defaults `tiers.DEFAULT_TIER = "ftr"`, choices from
`tiers.playable_names()`), `level`, `side` (choices from the `Side` enum), `attempts`
(shared-pool size), `thread` (`room`: none/public/private).

## The changes

### 1. Remove `side`

No reasoning captured yet for why — just the instruction to drop it. `puzzles.free`
(`chardle/puzzle.py:57`) takes `side: int | None = None` and folds it into `_filters` alongside
`level`; removing the option means either dropping the parameter path entirely or leaving it
in the service and just not exposing it as a command option (the latter costs nothing and
keeps the door open if this reverses).

### 2. A random-tier option

Today `tier` always names one difficulty (`pst`/`prs`/`ftr`/`byd`/`etr`/`err`, whichever
`tiers.playable_names()` returns). The idea: an option (or an extra choice on the existing
`difficulty` picker, e.g. `"random"`) that rolls a tier instead of pinning one. Open questions:
rolled once per board (frozen like columns/answer) or per guess-pool refresh; whether it's
uniform over `playable_names()` or weighted by pool size (`ftr`/`prs`/`pst` are 540 charts
each, `byd`/`etr`/`byd_2` are the much smaller "extras" pool per
[[h-chardle-extra-pool-hides-class]]); and whether `err` is eligible for random or stays
opt-in-only per [[h-chardle-err-is-an-event]].

### 3. Column count / explicit column choice

`columns.select_columns` (`chardle/columns.py:90`) always rolls up to `MAX_COLUMNS = 7`
(`TITLE` mandatory, one from each `REDUNDANT_GROUPS` pair if eligible, the rest random
fillers), with no caller-facing control today. Two separate asks, either or both:

- **Column *count*** — an option to raise/lower the target instead of the hardcoded 7. Lowering
  raises difficulty (fewer clues); raising is bounded by how many columns exist at all
  (`CANONICAL_ORDER` has 10, minus `TITLE` and whichever `REDUNDANT_GROUPS` member loses,
  minus whatever `_informative` rules out for that pool/answer — see
  [[d-chardle-dead-clue-columns]] for how thin that ceiling already runs on some tiers, e.g.
  err at 5).
- **Column *choice*** — pick specific clues rather than a random set. Bigger surface: needs a
  multi-select-shaped option (Discord slash commands don't have a native one — likely a
  string option parsed against `Clue` names, or several booleans), and has to reject a
  selection `_informative` can't support for the rolled pool/answer rather than silently
  producing dead ⬛ columns.

Both interact with the still-open [[h-chardle-board-rendering]] — whatever layout that page
settles on has its own column-count assumptions (the debug view renders one line per column;
an image board would need to reflow).

## What would answer it

Owner design pass: confirm the `side` removal is intentional and final (vs. hidden-not-removed
in the service layer), decide random-tier's rolling granularity and pool-weighting, and pick
one of {count only, explicit choice, both} for columns before touching `columns.py` or the
`Play` command's option set.

## Current best guess

None ventured — flagged for later, not designed.

## Answer

Settled 2026-07-30, built same day. See [[h-chardle-play-options-settled]].

- `side` hidden, not deleted: dropped from `Play`'s options; `puzzles.free`/`_filters` keep the
  `side: int | None` param untouched.
- Random tier added as an extra `"Random"` choice on `difficulty` (`tiers.RANDOM_TIER`), rolled
  once per board inside `PuzzleService.free` via `tiers.roll_random_tier` before the pool draw —
  same frozen-at-creation timing as columns/answer, no refresh-path reroll. Weighted, not
  uniform: `ftr .55 / prs .15 / pst .1 / extras .1 / byd .05 / etr .05`. `err` is not a weighted
  outcome — it still reaches free play only through the existing `roll_err` ambient/event
  chance in `PuzzleService.free` (discovered this already fires on every free-play call,
  explicit-tier or random, so nothing new was needed for err's interaction with random-tier).
- Column *count* only (not explicit choice — deferred, bigger surface, still blocked on
  [[h-chardle-board-rendering]]): new `columns` integer option, `min_value=3, max_value=8`
  (8 was the structural ceiling then; a third redundant group `(BPM, NOTE)` has since cut it to
  7 — see [[h-chardle-play-options-settled]]),
  default `MAX_COLUMNS` (7). Threads through `PuzzleService.free` → `_draw` → `select_columns`
  as `max_columns`.
- `room` (`thread`) moved to the first option on `Play`.

Built at: `chardle/tiers.py` (`RANDOM_TIER`, `_FREE_RANDOM_WEIGHTS`, `roll_random_tier`),
`chardle/puzzle.py` (`free`/`_draw` `max_columns` + random-tier resolution),
`chardle/columns.py` (`select_columns` `max_columns` param), `extensions/chardle.py`
(`Play` option set + `invoke`).
