---
type: gotcha
status: active
severity: medium
area: catalog
verified: 2026-07-28
created: 2026-07-27
updated: 2026-07-28
tags: [gotcha, chardle]
aliases: ["A clue column can carry zero information — narrow pools kill `level`, and `pack`/`version` duplicate each other"]
---
# A clue column can carry zero information — narrow pools kill `level`, and `pack`/`version` duplicate each other

## Symptom

A [[chardle|Chardle]] board where a column is green on every row of every game, or where
two adjacent columns always agree. The board looks informative and is not — the player is
paying board width and reading time for nothing, and the effective clue count is lower
than the column count suggests.

Three concrete forms:

- **`level` inside a narrow tier.** Tier "FTR 10–11" plus a `level` column: every answer
  and every plausible guess sits in the same one or two levels, so the column is green or
  ±1 forever.
- **`pack` and `version` together.** A pack ships at a game version, so the two columns
  agree on nearly every guess. Two columns, roughly one column of information.
- **`level` and `rating` together.** CC determines level. Both green, or both arrowed the
  same way.
- **`class` outside the extras pool.** Every other tier reveals its difficulty up front,
  so a `class` column would be green on every row of every game.
- **`level`, `rating` and `bpm` on an err puzzle** — the severe case, below.

## err is the 100% case

Measured against the live catalog, re-measured 2026-07-28:

| Class | Charts | With a real level | With a real CC | With an effective BPM |
|---|---|---|---|---|
| `err` | 7 | **0** | **0** | **7** |

This is not "usually weak". Every err chart stores `level = -1` and `rating = -1`
(one distinct `(level, rating)` row across all seven), so those two columns are dead
**100% of the time** on an err puzzle.

Two corrections to the 2026-07-27 numbers, both measured:

- **`bpm` survives.** Only 2 of 7 set `bpm_base` on the *chart* row, but every err chart
  inherits its song's BPM, and `ChartFacts.bpm` is the `effective()` value. All seven
  carry a real, varying BPM.
- **`charter` and `side` do not.** All seven set `charters_overridden = true` with zero
  chart-level charter links, so the effective charter set is empty on every one of them;
  and all seven are Conflict-side. The working err columns are `title`, `artist`,
  `pack`|`version`, `bpm`, `note` — **five**, not seven. Confirmed by rolling
  `select_columns` over the live err pool: two possible board shapes, both 5 wide.

It also means the err tier is a standing exception to [[chardle-mechanics|Chardle — Mechanics]] §Pool's rule
that sentinel-valued charts are excluded from the answer pool: applied literally, that
rule deletes the entire tier. err carves itself out and drops the affected columns
instead — see [[h-chardle-err-is-an-event]].

## Cause

The prototype rolled its column set from a fixed dice sequence in `Chardle.__init__` with
no reference to the answer pool: `pack` and `version` were **always** appended, `artist`,
`charter` and `side` were 50/50, and only `level` vs `rating` was coin-flipped as
mutually exclusive.

That was survivable there because its window was levels 2–24 — the whole catalog — so
`level` always spread. The revival introduces **named tiers** ([[chardle-mechanics|Chardle — Mechanics]] §Pool),
which deliberately narrow the pool. The same dice roll that was fine over the whole
catalog produces a dead column over a two-level slice. The prototype could not hit this
bug; the revival can.

## The wrong fix

Hardcoding "never show `level`". That over-corrects: `level` is a *good* clue over a wide
tier, and it is the most legible column on the board for a new player. The information
content depends on the pool, not on the column.

The other wrong fix is dropping `version` permanently because it correlates with `pack`.
Either is fine alone; only the pair is redundant. Deleting one loses a usable column
forever to avoid a per-puzzle collision.

## The over-correction that shipped first

**Fixed 2026-07-28.** `_informative` read

```python
return None not in values and len(values) > 1
```

— "unknown *anywhere* in the pool" on top of the variance rule. That is a stricter rule
than this page ever asked for, and it deleted real columns:

| Tier | eligible fillers, before | after |
|---|---|---|
| `pst` / `prs` / `ftr` / `etr` / `extras` | `bpm`, `note`, `side` | `artist`, `charter`, `bpm`, `note`, `side` |
| `byd` | `artist`, `bpm`, `note`, `side` | `artist`, `charter`, `bpm`, `note`, `side` |

`charter` was dead on **every** tier (41–42 Future/Present/Past charts carry no charter
link, 11 Beyond, 8 Eternal) and `artist` on all but `byd` (a single chart with no artist).
Two of eleven clue columns, gone, over a handful of rows.

Its docstring justified the clause as "how an err puzzle loses `level` and `rating`
without special-casing". **That was false**: err's `level`/`rating` are uniformly `-1`, so
`values == {None}` and the variance rule drops them on its own. The clause bought nothing
it was written for.

The knock-on was worse than the missing columns. Eligible fillers (3, or 4 on `byd`) never
exceeded the budget of `7 − len(chosen)`, so the truncation never truncated and
`rng.shuffle` was a no-op: board shape varied **only** by the two coin flips — exactly
**4 shapes per tier, forever**, against [[chardle-clue-columns|Chardle — Clue Columns]]'s "the board's
*shape* is itself a variable". Post-fix: **20 shapes** per ordinary tier, 40 on `extras`,
and every board runs the full 7 columns.

## The right handling

Column selection is a function of the **active pool** and the **drawn answer**, not a
fixed dice sequence:

1. Drop any column whose value does not vary across the pool, **ignoring the unknowns**.
   `level` over a two-level tier fails this; over "anything" it passes. err fails it for
   `level` and `rating` unconditionally.
2. Drop any column the **answer** has no value for. A *guess* missing one is fine —
   `feedback.evaluate` renders that row's cell ⬛ and the column keeps working for
   everyone else. An *answer* missing one makes every row ⬛: a dead column wearing a live
   one's clothes. This is the half that has to survive relaxing step 1, and it is why
   `select_columns` takes the answer as a positional argument.
3. Compare on the value the **board** shows, not the one the column stores. `_value` for
   `class` reads `ChartFacts.visible_class`, so a pool of nothing but Beyond and `byd_2`
   reads as constant — matching `feedback`, which collapses `byd_2` → Beyond. Reading the
   raw slot would have selected a column green on every row. Latent until some tier both
   hides its class and excludes Eternal; fixed alongside the above.
4. Pick at most one from each redundant group: `{level, rating}` (the prototype already
   did this one) and `{pack, version}` (it did not).
5. Gate tier-specific columns on the tier family — `class` only on extras
   ([[h-chardle-extra-pool-hides-class]]).
6. Freeze the survivors on the puzzle row, so a daily board is identical for everyone —
   see [[h-chardle-puzzle-rows-not-modes]].

Only *membership* is selected this way. **Render order is a canonical constant**, capped at
7 columns counting `title` ([[chardle-clue-columns|Chardle — Clue Columns]]) — the prototype had that part
right, and its only order-related bug was that the `level`/`rating` branch skipped the cap
check and could push a board to 8.

Step 1 also has to run *after* the sentinel exclusions in [[chardle-mechanics|Chardle — Mechanics]] §Pool, since
removing TBA and delisted charts can itself collapse a column's spread.

## Regression signal

A daily whose board has a column green on every row for every player, or two columns that
never disagree across a whole game. Cheap check once built: for each puzzle, count
distinct feedback values per column over its sessions' guesses — a column with one
distinct value across many guesses was dead.

The *silent* form is the one that shipped: a board that renders perfectly and simply never
shows a column it dropped. Signal for it is `SELECT count(DISTINCT clue_columns) FROM
chardle_puzzles` — a tier producing a handful of distinct sets over many puzzles has an
over-tight eligibility rule, not bad luck. Pinned by `tests/test_chardle_columns.py`,
which asserts against the live catalog that a gap *elsewhere in the pool* keeps `charter`
and a gap *on the answer* drops it.
