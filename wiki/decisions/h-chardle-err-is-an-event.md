---
type: decision
status: active
date: 2026-07-27
reverses:
created: 2026-07-27
updated: 2026-07-27
tags: [decision, chardle, err, april-fools]
aliases: ["err is a dated event: guaranteed on April 1, 25% that week, 0.3% otherwise, never a random daily"]
---

# `err` is a dated event: guaranteed on April 1, 25% that week, 0.3% otherwise, never a random daily

## Context

The Tenniel prototype hid an April Fools mode: a 0.6% roll on every `/chardle play`
swapped the pool to `err` charts and dropped `max_attempts` to 3. It was undated — the
joke could fire in October — and the 3 was unexplained.

The catalog explains it (2026-07-27):

| | |
|---|---|
| err charts | **7** |
| with a real level | **0** — all `-1` |
| with a real CC | **0** — all `-1` |
| with a BPM | **2 of 7** |
| with a note count | 7 |

Seven possible answers makes 6 attempts unlosable for anyone who knows the list. The
prototype's 3 was correct, not arbitrary. But [[chardle|Chardle]] pins the daily at 6 so
the guess-distribution histogram stays coherent, and an all-sentinel answer also kills
`level`, `rating` and most of `bpm` — see [[d-chardle-dead-clue-columns]].

So `err` cannot simply be another tier: it changes the attempt count, the column set, and
the stats contract at once.

## Alternatives

| Option | Why not |
|---|---|
| err as an ordinary random tier | An unannounced 3-attempt, 7-answer daily lands in someone's streak with no warning, and its solve-in-3 result corrupts a histogram denominated in 6 |
| err daily at 6 attempts | No special-casing, but with 7 answers it is a guaranteed win — a free streak day with no game in it |
| A separate bonus puzzle on April 1 | Preserves every invariant untouched, but it is a second puzzle to post and explain, and the joke stops being *the* daily |
| Keep the prototype's undated 0.6% | The joke's entire value is that it is dated. Firing in October is just a confusing puzzle |

## Decision

**The daily is never `err` except on April 1**, where it is guaranteed, AND just by attempting it advances the streak.

| Context                | err chance                                           | Attempts      |
| ---------------------- | ---------------------------------------------------- | ------------- |
| Daily, April 1         | **100%**                                             | 3 *(derived)* |
| Daily, any other day   | **0%**                                               | 6             |
| Freeplay, April 1 week | 25%                                                  | 3 *(derived)* |
| Freeplay, otherwise    | **0.3%**                                             | 3 *(derived)* |
| Custom                 | explicit tier — **testing scaffold only**, see below | 3 *(derived)* |

### Attempts are derived from the pool, not hardcoded

```
max_attempts = min(max(floor(N / 2), 1), 6)      # N = err charts in the catalog
```

N is 7 today, so this yields **3** — the prototype's unexplained number, re-derived rather
than copied. The floor matters because err charts can be *removed* as well as added: at
N ≤ 3 a bare `floor(N/2)` gives 1 or 0, and 0 is a board that is lost before it starts. The
cap of 6 keeps an err board from out-running the daily.

**N is counted with `include_hidden=True`.** err charts store `rating = -1`, which is also
the delisted predicate in `SearchService._chart_visible`, so counting them through the
ordinary visibility path returns 0 and the formula collapses to the floor.

**N is read once, at puzzle creation**, and frozen into `chardle_puzzles.max_attempts`.
Re-deriving it at render time would let an admin catalog edit change the budget of a board
someone is halfway through — the same reasoning that stores the answer instead of
re-deriving it ([[chardle-module|chardle (module)]]).

- **An *attempted* err daily counts as solved for the streak, won or lost, and is excluded
  from the guess distribution.** This is an **April-1-only exception** to
  [[chardle-mechanics|Chardle — Mechanics]] §Stats' "longest run of consecutive *solved* `puzzle_number`", so the
  streak predicate reads `state = 'won' OR (tier is err AND a session exists)`. Skipping
  April 1 entirely **still breaks the streak** — the exception forgives losing the joke
  puzzle, not ignoring it. Streak continuity is what players care about; the histogram is
  what breaks.
- The rate outside the event week is **0.3%**, half the prototype's 0.6% — the guaranteed
  April 1 daily plus a 25% event week already carry the joke, so the ambient rate exists
  only for the rare surprise.
- "April 1 week" is a settings window, defaulting to **April 1–7 inclusive** on the reference calendar.
- April-1-ness is fixed by the **reference calendar the puzzle sequence is anchored to**,
  not by any guild's local date. Puzzle #N is one chart globally
  ([[h-chardle-puzzle-number-not-date]]), so it cannot be err in one guild and not
  another. Guilds far from the reference offset will meet the April Fools puzzle at their
  own local midnight, which may read as March 31 or April 2 to them. Accepted — the
  alternative fragments the global sequence.
- An err puzzle drops the `level`, `rating` and `bpm` columns and passes
  `include_hidden=True`, which forces guesses onto the err class and so narrows valid
  guesses to the seven err-charted songs. Guess any other songs considered invalid and does not consume any attempts

### The custom err tier is scaffolding

Exposing `err` as a selectable custom tier exists **for testing only** — it is the only
way to exercise the mode outside April. It must be written as a **single removable
line** (one entry in the tier registry) and deleted before the joke is meant to land.
Same posture as `arcaea/client.py`'s temporary diagnostic block tracked by
[[h-real-rate-limit-shape-unknown]]: scaffolding is fine as long as the wiki knows it is
scaffolding.

## Consequences

- `chardle_puzzles.max_attempts` must stay per-puzzle rather than a constant, since the
  April 1 daily is 3 and every other daily is 6.
- Stats need an err predicate: streak counts it, histogram does not. Derivable from the
  puzzle's tier — no extra column.
- With 7 answers and free invalid guesses, the err roster is enumerable at no cost.
  Accepted; the mode is a joke, not a test.
- A future game update that adds or removes err charts moves `max_attempts` on its own —
  the formula above reads the catalog, so 7 is a *measurement* here, not a constant, and
  this page does not need re-deriving when it changes. What would need re-deriving is the
  formula's shape, if the joke's difficulty ever felt wrong.
- A leap-year or DST edge cannot shift April 1 here, because the date is read off the
  reference calendar at puzzle generation, not off a guild clock.

## Enforced at

Not yet built. Target: tier selection in `PuzzleService`, the err predicate in
`StatsService` — see [[chardle-module|chardle (module)]].
