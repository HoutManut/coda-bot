---
type: decision
status: active
date: 2026-07-30
reverses:
created: 2026-07-30
updated: 2026-09-26
tags: [decision, chardle, commands]
aliases: ["/chardle play option rework: side hidden, random tier weighted, columns count-only"]
---
# `/chardle play`'s option rework: hide `side`, add weighted random-tier, column count only

## Context

[[h-chardle-play-options-rework]] filed three unsettled changes to `Play`'s options
(`extensions/chardle.py:457-497`): drop `side`, add a random-tier option, and give column
count and/or explicit column choice some caller-facing control instead of
`columns.select_columns`'s hardcoded `MAX_COLUMNS = 7` roll. Owner design pass 2026-07-30
settled all three plus one ordering tweak, and the changes were built the same session.

## Alternatives

| Option | Why not |
|---|---|
| Delete `side`'s param path from `puzzles.free`/`_filters` entirely | Costs nothing to keep it in the service; deleting closes the door if the removal reverses, for no benefit today. |
| Random tier re-rolled per guess-pool refresh | Novel — no other board property (columns, answer) changes mid-board, and the refresh path carries no reroll hook today. Once-per-board matches existing precedent. |
| Uniform random-tier weighting across `playable_names()` | Ignores that `ftr`/`prs`/`pst` are 540-chart pools and `byd`/`etr`/`extras` are the thin "extras" pools ([[h-chardle-extra-pool-hides-class]]) — uniform would surface the thin pools far more often than the daily's own weighting treats them. |
| A separate err weight inside the random-tier table | `roll_err`'s ambient/event chance (`ERR_AMBIENT_CHANCE`/`ERR_EVENT_CHANCE`) already fires inside `PuzzleService.free` on **every** free-play call, explicit-tier or random alike (`puzzle.py:71`, discovered mid-design) — a second err mechanism would stack redundantly with the first. |
| Explicit column choice (pick specific `Clue`s) now | Bigger surface — needs a multi-select-shaped option Discord doesn't natively have, plus rejection logic for a pick `_informative` can't support for the rolled pool/answer. Deferred; still blocked on [[h-chardle-board-rendering]] settling column-count assumptions for whatever board layout it picks. |

## Decision

- **`side`**: hidden, not deleted. Dropped from `Play`'s command options; `PuzzleService.free`
  and `_filters` keep `side: int | None = None` untouched. The extension-layer `_side_id`/
  `_SIDE_IDS` translation helpers were deleted as genuinely dead code (no caller left), not kept
  as a shim.
- **Random tier**: `tiers.RANDOM_TIER = "random"` is an extra `"Random"` choice on the existing
  `difficulty` picker (`tiers.playable_names()` unchanged — the real tier names). Resolved once
  per board inside `PuzzleService.free`, before the pool draw, via `tiers.roll_random_tier` —
  same frozen-at-creation timing as columns/answer. Weighted: `ftr .55 / prs .15 / pst .1 /
  extras .1 / byd .05 / etr .05` (`_FREE_RANDOM_WEIGHTS`) — same shape as the daily's
  `_DAILY_WEIGHTS`, but extras' wider `.2` share splits three ways since free play offers
  `byd`/`etr` separately: extras keeps half (the safer, wider merged pool), `byd`/`etr` split
  the rest evenly. `err` has no entry in this table — it stays reachable only through the
  existing ambient/event `roll_err` chance in `PuzzleService.free`, applied after tier
  resolution regardless of how the tier was picked, so random-tier needed no new err handling.
- **Columns**: count only, not explicit choice. New `columns` integer option on `Play`
  (`min_value=3, max_value=8, default=MAX_COLUMNS`). `8` was the structural ceiling when this
  was decided (`TITLE` + one winner from each of two `REDUNDANT_GROUPS` pairs + 5 `_FILLERS`).
  Since `(BPM, NOTE)` became a third redundant group, the ceiling is **7** — `TITLE` + three
  group winners + the 3 remaining `_FILLERS` (`ARTIST`, `CHARTER`, `SIDE`) — which equals
  `MAX_COLUMNS`. The option still accepts 8; `select_columns` clamps it. Threads through as `max_columns`: `Play.invoke` → `PuzzleService.free` → `_draw`
  → `columns.select_columns`. `select_columns` still clamps to what `_informative` actually
  supports for that pool/answer — the option sets a target ceiling, not a guarantee.
- **`room`**: moved to `Play`'s first option (was last).

## Consequences

- `daily()` and any other `_draw`/`select_columns` caller are unaffected — both new params
  default to today's behavior (`MAX_COLUMNS`, no random resolution) when unspecified.
- A player who picks `"Random"` still cannot land on `err` from the picker itself; `err` boards
  in free play remain purely a `roll_err` surprise, dated per [[h-chardle-err-is-an-event]].
- Explicit column choice is still open — [[h-chardle-play-options-rework]] is answered for
  count, but choice stays deferred behind [[h-chardle-board-rendering]].
- If `err` is ever meant to be directly pickable (reversing the testing-scaffolding note in
  `tiers.playable_names()`), it would need its own entry in `_FREE_RANDOM_WEIGHTS` too — not
  automatic from this decision.

## Enforced at

`chardle/tiers.py` (`RANDOM_TIER`, `_FREE_RANDOM_WEIGHTS`, `roll_random_tier`),
`chardle/puzzle.py:57-91` (`free`/`_draw`), `chardle/columns.py:90` (`select_columns`),
`extensions/chardle.py:455-497` (`Play` options), `extensions/chardle.py` `Play.invoke`.
