---
type: domain
status: active
source: 2024 prototype (`classes/chardle.py`, `plugins/chardle.py`, 2024-09/10, archived outside this repo) + design session 2026-07-27
verified: 2026-07-28
created: 2026-07-29
updated: 2026-07-29
tags: [domain, chardle, game]
aliases: ["Chardle Mechanics", "Chardle — Mechanics"]
---

# Chardle — Mechanics

Split out of [[chardle|Chardle]] 2026-07-29 (that page had grown past the vault's 300-line
soft threshold — see `meta/lint-report-2026-07-29.md`). Covers the answer pool, lifetime
stats, standing rules, and the prototype-comparison table. Clue-column mechanics live in
[[chardle-clue-columns|Chardle — Clue Columns]]; the Discord channel/scoreboard surface
lives in [[chardle-discord-surface|Chardle — Discord Surface]].

## Pool

A puzzle's answer is drawn from a **tier**: a (level window, allowed difficulty classes)
pair, nothing more. Tiers are scoped settings, not a table.

Three tier families, with live catalog counts as of 2026-07-27:

| Family | Classes | Charts | Notes |
|---|---|---|---|
| **base** | `pst` / `prs` / `ftr`, level-windowed | 540 each | the ordinary tiers |
| **extras** | Beyond + Eternal pooled | **167** over 166 songs | class hidden; see [[h-chardle-extra-pool-hides-class]] |
| **byd** / **etr** | Beyond alone (incl. `byd_2`) / Eternal alone | **64** / **103** | free play only; class revealed, so no `class` column |
| **err** | `err` | **7** | April Fools only; see [[h-chardle-err-is-an-event]] |

`byd` and `etr` are offered on `/chardle play` but are **not in the daily rotation** — the
thin-pool and free-narrowing arguments only bite on a puzzle nobody chose. The merged entry
reads **"ETR + BYD" in the picker** and still prints `Extra` on the board.

Beyond (63) and Eternal (103) are individually thin and are mutually exclusive per song, so
they are pooled rather than offered separately. **165 of 166 songs carry exactly one
extra chart**, which is what makes "the song's extra" a well-defined guess target.

**`byd_2` is not a third class.** It is the underlying mechanism that lets a single song
carry *two charts in one class*, and a player has no concept of it — what they know is that
Last has two Beyonds and that the game and the bot both handle that without comment. So the
merged tier holds exactly **two visible classes, Beyond and Eternal**, and the `class` clue
column reads both of Last's charts as Beyond. Last is the single song where "the song's
extra" is two charts, resolved by the ordinary ambiguity rule in
[[h-chardle-closest-match-always-costs]] — answer-preference first, else the first Beyond.
That tiebreak is invisible from the player's seat, which is the point.

Obscurity is explicitly **not** filtered for. Arcaea's catalog is official and finite —
there are no community-made charts — so every song is canonical and learnable, and an
unfamiliar answer teaches rather than cheats. Play-frequency weighting and tag-gated pools
were both considered and rejected on that basis.

Excluded from the answer pool regardless of tier:

- charts with a level or CC sentinel (`0` = TBA, `-1` = err-only) — arrow comparison against an unknown is meaningless. See [[d-level-cc-sentinel-values]].
- delisted songs (negative CC), via `catalog.search.is_delisted`.

As a **guess**, a sentinel-valued chart renders `?` in that column with no colour and no
arrow, rather than being rejected.

Those exclusions apply **when the answer is drawn**, and a puzzle outlives them. A song
delisted *after* its puzzle was created would otherwise be cloaked out of its own game and
leave the board unwinnable, so the answer check runs ahead of the cloak: **naming the answer
wins even when the answer is delisted; naming any other delisted song is an invalid guess
and stays free.** See [[h-chardle-closest-match-always-costs]] §Rule 0.

The **err** tier is the standing exception to the sentinel exclusion — every err chart is
all-sentinel, so the tier carves itself out and drops the affected columns instead. See
[[d-chardle-dead-clue-columns]] §err.

### err charts are never guessable outside an err puzzle

`SearchService` already cloaks err behind `include_hidden`, and chardle passes it
straight through: **`False` in every ordinary mode**, so an err chart can never be
guessed, matched, or shown. An err *puzzle* passes `True`, which forces every guess onto
the err class and therefore narrows valid guesses to the seven err-charted songs.

Because an invalid guess is free, a player can enumerate that roster at no attempt cost.
That is accepted — with seven answers the roster is common knowledge anyway, and the
mode is a joke, not a test.

## Stats

Derived from the sessions table on read; no denormalised stats table.

- **Streak** — longest run of consecutive solved `puzzle_number`. Deliberately not
  calendar days; that is what makes per-guild rollover safe. See
  [[h-chardle-puzzle-number-not-date]].
- **Guess distribution** — histogram of solve-in-N. This is why the daily's
  `max_attempts` is pinned at 6: a histogram over a varying denominator is incoherent, so
  changing that number later orphans every prior result. One-way door. **err dailies run
  at 3 and are excluded from the histogram**, and an **attempted** err daily counts as
  solved for the streak whether it was won or lost — an April-1-only exception, see
  [[h-chardle-err-is-an-event]]. Skipping April 1 outright still breaks the streak.
- **Share string** — spoiler-safe emoji grid, `Chardle #412 4/6`. Arrows are safe to
  include: the reader cannot see the guess an arrow points *from*, so it carries no
  information about the answer. The column set is identical for everyone on a daily, so
  revealing it leaks nothing either. A finished **free-play** board is shareable too, but
  its string is self-describing rather than numbered — `Chardle · FTR 9 · 4/6` — because a
  reader with no puzzle number has no legend to decode the grid against, and no shared
  puzzle to compare it to. Unranked by construction, which is the same test as
  `puzzle_number IS NULL`.
- **Guild leaderboard** — stats are per-user and location-independent; the board filters
  to guild members. Solving in DMs still counts.

## Rules

Carried over from the prototype:

- An **unresolvable** guess (no match, or the song lacks the puzzle's difficulty) does
  not consume an attempt.

Added by the revival:

- A **duplicate** guess is rejected, not silently charged. The prototype spent an attempt
  re-comparing a song already on the board.
- The daily expires at its guild's rollover — **local 00:00 + 4 h**, default zone GMT+7
  ([[h-chardle-puzzle-number-not-date]]) — and scores as a loss. A free-play board never
  expires on a clock, but it holds its channel's one live-board slot until it is won,
  lost, or ended — so an abandoned board needs `/chardle play end` plus an inactivity
  sweep. A *lost* board frees the slot for free.
- `attempts:` must be **1 or greater**. `0` and negatives construct a board that is lost
  before its first guess.
- `/chardle end` is allowed to anyone who has guessed on the board **or** to anyone holding
  `MANAGE_MESSAGES` — and, **15 minutes after the board started, to anyone at all**
  (2026-07-27, owner: "no game would actually go past 15 mins, let alone the full day TTL").
  Past that window a board is abandoned in practice, and freeing the channel's one live slot
  should not need a moderator. `chardle_abandon_hours` remains the backstop for when nobody
  is present to ask.
- A puzzle carrying custom filters is stats-ineligible **by construction**, not by a flag
  someone must remember to set. Otherwise "level 1 pool, 20 attempts" farms a perfect
  record. Since only dailies carry stats at all, eligibility is really just
  `puzzle_number IS NOT NULL`; a `CHECK (puzzle_number IS NULL OR filters IS NULL)` keeps
  that redundancy enforced instead of assumed.

## Prototype provenance

The Tenniel implementation (`classes/chardle.py`, 799 lines) is the source for the clue
semantics and the feedback thresholds in [[chardle-clue-columns|Chardle — Clue Columns]].
What it got right is kept. What it got wrong is recorded so the port does not reproduce it:

| Prototype behaviour | Why it must not survive |
|---|---|
| `wait_for(MessageCreateEvent)` per game | Game state lived in a coroutine — no persistence, one long-lived task per player, a bot restart silently killed every game |
| `bg_file` branched on sides 0–2 and `byd`/`byd_2` only | `Side.LEPHON` (3) and `DifficultyClass.ETR` both exist now and fall through |
| `fuzzy_search(...)[:2]`, `reverse()`, arbitrary pick | Superseded by `catalog.search.SearchService` |
| No sentinel guard on level/CC | Delisted and TBA charts poison arrow arithmetic |
| Answer leaked to a hardcoded debug channel | `1285895916863098920`, unconditional |
| `play_cost` / `base_reward` / currency economy | Tenniel had a currency. coda-bot has none; dropped entirely |
| `max_attempts` 5 in config, 10 in code | Code overrode its own config |

## Related

[[chardle|Chardle]] · [[chardle-clue-columns|Chardle — Clue Columns]] ·
[[chardle-discord-surface|Chardle — Discord Surface]] ·
[[h-chardle-extra-pool-hides-class]] · [[h-chardle-err-is-an-event]] ·
[[h-chardle-puzzle-number-not-date]] · [[h-chardle-closest-match-always-costs]] ·
[[d-level-cc-sentinel-values]] · [[d-chardle-dead-clue-columns]]
