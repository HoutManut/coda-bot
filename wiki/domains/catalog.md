---
type: domain
status: active
source: arcaea-domain-reference.md
verified: 2026-07-29
grade: A
created: 2026-07-21
updated: 2026-07-27
tags: [domain, arcaea, catalog]
---

# Catalog

## Model

Arcaea's catalog is **songs**, each with a set of **difficulties** ("charts"). Every song always
has `pst` (Past), `prs` (Present), `ftr` (Future); it may additionally have `byd` (Beyond) or
`etr` (Eternal), mutually exclusive. Two app-defined pseudo-difficulties exist for special cases:
`byd_2` and `err` (April Fools "ERROR" charts).

**`byd_2` is a storage slot, not a difficulty class.** It is the mechanism by which the catalog
holds a *second chart inside an existing class* — today, only Last's second Beyond. The game
presents no such class and **players have no concept of it**: what a player sees, and what they
will say, is that Last has two Beyonds, handled without comment by the game. So every surface
that classifies a chart — search, display, a minigame comparing classes — must read `byd_2` as
**Beyond**. Treating it as a third value invents a class the game does not have.

**`err` is the same kind of slot, applied one level up.** In game it is not a difficulty at all:
lowiro ships an April Fools track as **its own song entry carrying a single `ftr` chart**, and
classifies it as a *"Limited Time Error Track"* (owner, 2026-07-27). The community calls them
separate songs too, because that is what they are on screen. This catalog folds each one back
onto its parent song as an `err` difficulty — convenient for storage and search, but a
modelling choice of ours, not a class the game hands us. The wire never carries an `err` value
at all (see §Traps).

A song's shared attributes (name, artist, bpm, side, jacket, dates, etc.) live in a `default`
block sourced from the `ftr` difficulty. Every other difficulty **inherits** these values and may
**override** any of them individually — see §Effective Value Resolution below. Four fields are
always difficulty-specific and never have a song-level representation: `level`, `rating` (chart
constant), `note` (note count), `chart_designer`.

Packs group songs for sale/release. Artists and charters are separate entities linked to songs
(and optionally overridden per-difficulty) via junction tables, distinct from the free-form
display strings shown on the song.

## Encoding

### Difficulty keys

| Key     | ID  | Full Name | Notes                                                                                                                                                        |
| ------- | --- | --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `pst`   | 0   | Past      | Always present                                                                                                                                               |
| `prs`   | 1   | Present   | Always present                                                                                                                                               |
| `ftr`   | 2   | Future    | Always present. Source of all song-level defaults                                                                                                            |
| `byd`   | 3   | Beyond    | Optional. Mutually exclusive with `etr`                                                                                                                      |
| `etr`   | 4   | Eternal   | Optional. Mutually exclusive with `byd`                                                                                                                      |
| `byd_2` | —   | Beyond    | App-defined **slot, not a class**. Last's second Beyond — classify as `byd`.                                                                                 |
| `err`   | —   | Error     | App-defined **slot, not a class**. An April Fools "Limited Time Error Track" — its own song in game, with one `ftr` chart — folded onto the parent song here |

The `pst`..`etr` int column is the **wire `difficulty` value** — see [[score-mapping|Score Mapping]] §2, which
independently confirms this table.

### Level encoding

```
stored = game_level * 2          (no "+" suffix)
stored = game_level * 2 + 1      ("+" suffix)

decode: game_level = stored // 2 ; is_plus = stored % 2 == 1
```

| Stored | Display | Meaning                           |
| ------ | ------- | --------------------------------- |
| `-1`   | `?`     | N/A — `err` difficulties only     |
| `0`    | `?`     | Chart exists, level not yet knwon |
| `14`   | `7`     |                                   |
| `15`   | `7+`    |                                   |
| `20`   | `10`    |                                   |
| `21`   | `10+`   |                                   |
| `24`   | `12`    |                                   |

### Chart constant (CC) encoding

Field name on the wire/DB is `rating` — **this is the chart's CC, not the player's PTT**
(different field on a different object; see [[potential|Potential]] and [[d-ptt-hidden-sentinel]]).

```
stored = chart_constant * 10
chart_constant = stored / 10.0
```

| Stored | Chart Constant | Meaning                                 |
| ------ | -------------- | --------------------------------------- |
| `-N`   | `abs(N / 10)`  | Removed charts, stored for preservation |
| `-1`   | `?`            | N/A — `err` difficulties only           |
| `0`    | `?`            | Value not yet known                     |
| `40`   | `4.0`          |                                         |
| `97`   | `9.7`          |                                         |
| `113`  | `11.3`         |                                         |
| `120`  | `12.0`         |                                         |

> [!note] Catalog CCs are FACT, not community estimates
> CCs in this catalog are copied directly from the game — they are not community-derived
> estimates and should never be treated as approximate. `arcaea-potential.md` §7 states this
> explicitly (owner, 2026-07-21): "CC is not the limiter" for higher-precision PTT display. Any
> page or comment hedging on CC precision predates this and is stale — do not reintroduce that
> framing. Sentinel values (`<=0`) mean *unknown/not yet revealed*, not *imprecise*.

### Sides

| ID | Name      |
|----|-----------|
| 0  | Light     |
| 1  | Conflict  |
| 2  | Colorless |
| 3  | Lephon    |

### Effective value resolution

```
effective.field = difficulty.field   if explicitly set on the difficulty
                   song default       otherwise
```

Overridable: `name_en`, `name_jp`, `artist`, `bpm`, `bpm_base`, `time`, `side`, `world_unlock`,
`remote_download`, `bg`, `date`, `version`, `jacket`, `jacket_designer`.

Non-overridable (always difficulty-specific, never inherited, never shown at song level):
`level`, `rating`, `note`, `chart_designer`.

### Artist/charter per-difficulty override

```
effective links for a chart = the chart's own link set   if <kind>_overridden
                               the song's link set        otherwise
```

Two independent boolean flags per chart: `artists_overridden`, `charters_overridden`. The flag —
not mere row presence — decides inheritance: an **empty overridden set is meaningful** (chart's
links explicitly unknown/none, distinct from "inherit the song"). Replacement is whole-set,
never additive. The `ftr` chart never overrides (it *is* the song default), so it has no
per-chart link/alias controls.

## Traps

- **Level/CC sentinel collision**: both `level` and `rating` use `0`=TBA and `-1`=err-only-`?`
  as *distinct* meanings on the *same* stored integer — a naive "sentinel means missing" decode
  conflates them. See [[d-level-cc-sentinel-values]].
- **`byd_2` arrives under a different `song_id`** on the wire (`"lasteternity"`, not `"last"`)
  with `difficulty: 3` (byd), not a `byd_2` wire value — a naive `(song_id, difficulty)` lookup
  misses it entirely. See [[score-mapping|Score Mapping]] and [[d-byd2-game-song-id-resolution]].
  Note the wire agrees with the model above: it sends `difficulty: 3`, **Beyond**, because there
  is no `byd_2` class to send.
- **`byd_2` read as a class** is the same trap one level up. A chart classifier that emits three
  extra classes instead of two shows players a category the game never gave them, and any
  same-class comparison (`is this chart the same difficulty as that one?`) answers "no" for
  Last's two Beyonds. Classify `byd_2` as `byd` everywhere; keep the slot distinct only where
  the *chart identity* matters, e.g. resolution and score mapping.
- **`name_en` is not unique** (Genesis, Quon both collide across two `song_id`s) — a
  same-name query must disambiguate, never guess the first match.
- **Pack display name is per-song**, not per-`pack_id` — two songs in the same pack can show
  different `pack_name`; the per-song value always wins.
- **Artist display string vs. relational links**: `songs.artist` (free-form, may be an alias or
  a collaboration-unit name) is independent of the `song_artists` junction (real IDs). Do not
  parse the display string to derive artist IDs.
- **Release-date offsets**: same-day releases are offset by seconds for ordering — `date`
  truncated to day precision gives the actual calendar date, not `date` itself.
- **`err` charts are hidden from broad search** and superseded in search by any later `byd`
  promotion of the same remix — see [[score-mapping|Score Mapping]] (`err` never appears on the wire at all).
  They also do not count as songs here even though the game ships them as songs, so a song
  count taken from this catalog and one taken from the game disagree by the number of error
  tracks.

## Source

[[arcaea-domain-reference]] — authoritative and more detailed than this page. See
[[arcaea-domain-reference]] (source page).
