---
type: decision
status: active
date: 2026-07-27
reverses:
created: 2026-07-27
updated: 2026-07-27
tags: [decision, chardle, catalog]
aliases: ["The extras pool merges Beyond and Eternal and reveals only \"Extra\""]
---

# The extras pool merges Beyond and Eternal and reveals only "Extra"

## Context

[[chardle|Chardle]] reveals a puzzle's difficulty up front everywhere else. The top
difficulty slots resist that, for a reason visible in the catalog (counts 2026-07-27):

| Class | Charts |
|---|---|
| `byd` | 63 |
| `etr` | 103 |
| `byd_2` | 1 |

(`byd_2` is a storage slot, not a class — it is how the catalog holds Last's *second*
Beyond. Counted separately here only because that is how the rows sit.)

Offered separately, each is a thin pool — 63 answers repeats fast, and a revealed
"Eternal" tells the player before their first guess that the answer is one of 103 charts.
Revealing the class *is* a clue, and a large one.

They also cannot be mixed casually: `byd` and `etr` are mutually exclusive on a song, and
`byd_2` exists on exactly one song.

The catalog turns out to make the merge nearly free. Of the 166 songs carrying any extra
chart, **165 carry exactly one**; the sole exception is Last (`byd` + `byd_2`).

## Alternatives

| Option | Why not |
|---|---|
| Separate `byd` and `etr` tiers | Thin pools that repeat, and revealing the class hands over a 2.5× narrowing for free before the first guess |
| Merge but reveal the exact class | Merges the *pool* and then immediately discards the benefit — the player still starts knowing which 63 or 103 charts are in play |
| Merge and exclude `byd_2` | Cheap (one song) and it would sidestep the [[d-byd2-game-song-id-resolution\|`game_song_id`]] trap, but it silently drops Last's second Beyond from a mode explicitly meant to cover the top slots |

## Decision

Beyond and Eternal form **one `extras` tier** — 167 charts over 166 songs. The board reveals
only **"Extra"**. The class itself is hidden and becomes an optional **`class` clue
column**: green on a matching class, red otherwise, no arrow (the classes are not ordered).

**`byd_2` is not a class and must never be treated as one.** It is the underlying mechanism
that lets a single song carry *two charts within one class* — Beyond, in this case. Players
have no concept of it; what they know is that Last has two Beyonds and that the game and the
bot both support that without comment. So chardle sees **two classes in this tier, Beyond and
Eternal**, and both of Last's charts are Beyond for every purpose: pool membership, the
`class` column, and feedback.

A guess resolves to *the guessed song's extra chart*, unambiguous for 165 of 166 songs. Last
is resolved by the existing rule in [[h-chardle-closest-match-always-costs]] —
answer-preference first (if the answer is either of Last's Beyonds, guessing Last hits it),
otherwise the first Beyond. If the guessed song has no extra chart at all, the guess is
invalid.

This is the **only** place the revealed-difficulty rule is qualified.

### Standalone `byd` and `etr` were added alongside it, 2026-07-27

Owner request. `/chardle play` now also offers **Beyond** (64 charts, `BYD` + `BYD_2`) and
**Eternal** (103) on their own, and the merged entry is renamed **"ETR + BYD" in the picker
only** — the board still prints `Extra`, so nothing about a merged puzzle changed.

This **qualifies rather than reverses** the decision above. The merged tier keeps its hidden
class and stays the only extras tier in the daily rotation, which is where the thin-pool and
free-narrowing arguments actually bite. A player who deliberately picks "Beyond" on free play
has chosen to know; a daily cannot be chosen. So `_DAILY_WEIGHTS` is untouched.

The standalone tiers carry `class_is_hidden=False`, which drops the `class` column
automatically — `columns.select_columns` gates on that flag, never on a tier name, so no new
branch was needed. `byd` includes `BYD_2` for the same reason the merged tier does.

## Consequences

- The `class` column is **binary** here — Beyond or Eternal, 64 charts against 103 — not a
  three-way split. Weaker than a three-valued column would be, and correct: a third value
  would be exposing an implementation detail as a game fact.
- The `class` column is meaningful **only** on extras puzzles. On every other pool the
  class is stated up front, so the column would be green on every row — precisely the
  dead-column failure in [[d-chardle-dead-clue-columns]]. Column selection must gate it on
  the tier family.
- Guessing a song with no extra chart is an *invalid* guess and stays free, so players can
  probe "does this song have an extra" at no cost. Accepted: that is knowledge a player of
  the game already has.
- Level windows behave differently here. `byd` spans stored level 18–24, `etr` 16–22 —
  overlapping but not identical, so a level window applied across the merged tier silently
  reweights the class mix. Windowing the extras tier is legal but not neutral.
- Last is the one song where "the song's extra" is ambiguous, and it is also the song
  behind [[d-byd2-game-song-id-resolution]]. Any future change to `byd_2` handling must
  check this rule too — though that page's `game_song_id` trap is out of scope here, since
  chardle keys on `song_difficulty_id` and never touches the wire.

## Enforced at

`tiers.TIERS` (`class_is_hidden`, `choice_name`) and `columns.select_columns`, which appends
`Clue.CLASS` only when the tier hides its class. `feedback._visible_class` folds `BYD_2` into
Beyond. See [[chardle-module|chardle (module)]].
