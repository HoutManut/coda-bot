---
type: question
status: open
blocks: ["manual ownership declaration sizing", "[[tournaments|Tournaments]] pool.owned_by_all", "any read of Song.world_unlock"]
source: ownership-worksheet-2026-09-03.md
created: 2026-09-03
updated: 2026-09-03
tags: [question, ownership, catalog, data-fix, decided-unapplied]
aliases: ["The 18 world_unlock rows that are wrong"]
---

# Which `world_unlock` rows are wrong, and what should they be?

> [!note] Decided, not open — this page holds unapplied work
> Every row below is settled by owner answer (2026-09-03). Nothing here needs research.
> It is filed as a question only because **no code or data has been changed yet** — the
> answering session was explicitly scoped to documentation.

## Why it is open

`Song.world_unlock` was measured against one t3 account's `world_songs` during the
[[ownership-worksheet-2026-09-03|ownership worksheet]] and disagreed in both directions.
The owner ruled on every disputed row. 18 rows are wrong out of 129 currently flagged.

Until they are fixed, three things are wrong downstream: the count of packs that can be a
single checkbox in a manual declaration (46 vs the true 49), which packs need per-song
questions (17 vs 14), and any consumer that reads the flag as "this song is free".

## What would answer it

Nothing — it is answered. What remains is applying it, with a `./scripts/dump-songs.sh`
backup first, as with the [[ownership-worksheet-2026-09-03|three defects fixed the same
day]].

## The rows

### Set `world_unlock = True` (7)

Both packs release songs incrementally into world mode and the catalog never caught up —
**staleness, not a semantics problem** (owner: *"prob stale"*, on all seven).

| song_id | pack |
|---|---|
| `hailstone` | `extend_3` |
| `rostpagegene` | `extend_3` |
| `flexidefine` | `extend_4` |
| `mirrorrmx` | `extend_4` |
| `riotsystem` | `extend_4` |
| `tabootears` | `extend_4` |
| `vallista` | `extend_4` |

Owner confirmed the totals independently of the row list: **all 20** of `extend_3` and
**all 16** of `extend_4` are world-unlockable. 18 + 2 = 20 ✓ and 11 + 5 = 16 ✓ — the two
answers corroborate exactly.

`extend_4` is still filling — *"all 16 (current, will be 20 by the end)"* — so expect four
more rows to need the flag as they ship.

### Clear `world_unlock` (11)

| song_id | pack | note |
|---|---|---|
| `essenceoftwilight` | `core` | |
| `pragmatism` | `core` | its **Beyond** is world-earned; the song is not |
| `sheriruth` | `core` | |
| `astralquant` | `lephon` | |
| `designant` | `lephon` | its **Beyond** is story-gated; the song is not |
| `etherstrike` | `rei` | |
| `axiumcrisis` | `yugamu` | its **Beyond** is world-earned; the song is not |
| `lostdesire` | `vs` | |
| `bbkkbkk` | `single` | |
| `eternitybreak` | `single` | |
| `ionostream` | `single` | |

Owner answers behind these: `core` — *"1 world unlock 'song'. solitary dream"*; `lephon`,
`rei`, `yugamu` — *"none"*; `vs` — *"1. 'arcahv'"*; `single` — *"desive is world_unlock,
rest false. checked"*.

Three of the eleven (`pragmatism`, `designant`, `axiumcrisis`) are songs whose **Beyond**
carries the unlock, with the flag mistakenly recorded at song grain. That is the same
grain confusion the OWNED/UNLOCKED split is meant to end — see
[[ownership-worksheet-2026-09-03]].

### Left alone, deliberately

- **`innocence`** (`single`) stays `False`. It is free — unlocked by a beginner mission
  (owner) — but it is not a *world-mode* unlock, and the flag has no way to say "free
  without purchase". This is the clearest single case for the OWNED/UNLOCKED model.
- **`desive`** (`single`) stays `True`. Its map has a prerequisite (five other singles),
  but it is a world-mode unlock like the rest.
- The remaining 4 flagged in `single` — `acheron`, `chronologia`, `diein`, `guardina` —
  stay `True` (owner, §3: all four are world unlocks whose maps require other packs).

### Also stale: one pack name

`packs.extend_3.name` is `"World Extend 3"` and should be **`"Extend Archive 3"`** (owner).
`extend_4`'s `"World Extent 4"` is **correct as stored** — do not "fix" the apparent typo.

## Resulting counts

| | now | after |
|---|---|---|
| songs flagged `world_unlock` | 129 | **125** |
| packs with zero flagged songs | 46 | **49** |
| packs with some flagged songs | 17 | **14** |

`lephon`, `rei` and `yugamu` move from "needs per-song questions" to "one checkbox".

## Answer

Answered 2026-09-03 by owner, in the [[ownership-worksheet-2026-09-03|worksheet session]].
**Unapplied** — this page closes when the 18 rows and the pack rename land.
