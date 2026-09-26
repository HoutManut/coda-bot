---
type: domain
status: active
source: arcaea-domain-reference.md
verified: 2026-07-29
grade: A
created: 2026-07-21
updated: 2026-09-03
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
| 2  | Achromic  |
| 3  | Lephon    |
| 4  | Dark Lephon  |

### Alt appearance ("Inscribed")

Some Beyond charts carry lowiro's alternate skin — a different name and color for
the same chart, **not a difficulty class of its own**. Stored as `SongDifficulty.alt`
(boolean, default `false`), meaningful only on `byd`/`byd_2`. When set, every
render substitutes the alt name ("Inscribed"/"INS") and color (`0x0C2065`) for
the plain Beyond ones — see `catalog/colors.py:class_color` and
`catalog/labels.py:class_full`/`class_short`. All four Beyonds shipped in 7.0
(`dreadarea`, `rivenpilgrim`, `deinosphainein`, `cataclysmcry`) have it; toggled
per chart in the admin editor going forward, not derived from version.

Search takes it as *intent*, not as a class: the trailing tokens `ins` /
`inscribe` / `inscribed` in a raw `/song` query mean Beyond **and** narrow to the
alt-flagged chart (`catalog/search.py:_ALT_TOKENS`), so `last ins` picks one of
Last's two Beyonds where `last byd` can only offer both. A song with no
alt-flagged Beyond falls back to plain Beyond handling — an unset flag is a
catalog gap as often as a real plain chart. The `/song difficulty:` dropdown
stays class-only; "Inscribed" is not offered there.

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

## Ownership

`verified: 2026-09-03`, `grade: FACT (measured against one t3 account), OWNER-STATED (unlock rules)`

Full measurement, all 146 owner answers and the design calls that came out of them:
[[ownership-worksheet-2026-09-03]]. It supersedes [[handoff-11-ownership-blob|handoff 11]],
whose premise — that no ownership data exists on the wire — is wrong.

**A player's playable set is a union of independent grants, never a single field.** Nothing
in the catalog determines it: `pack_id` says where a song is *sold*, not whether a given
player has it, and `world_unlock` says a song is *obtainable* in world mode, not that it was
obtained.

### OWNED and UNLOCKED are two different facts

> *"we should have a whole new OWNED and UNLOCKED system"* — owner, 2026-09-03

This is the model everything below resolves into, and the reason `world_unlock` is
confusing: one boolean on `Song` carries two orthogonal facts at the wrong grain.

| | Question | Examples of what varies |
|---|---|---|
| **OWNED** | did this player *acquire* it? | bought the pack · bought the single · free (`base`) · free with another pack (`epilogue` with `finale`) |
| **UNLOCKED** | has this player satisfied the *in-game condition* to play it? | world-mode map · story progression · beginner mission · fragments (Eternal) |

**`playable = OWNED ∧ UNLOCKED`**, with `has_score` as proof of both. Every confusing case
in this section is one of the two being read as the other.

Both axes reach **chart grain**, not just song grain: a Beyond is OWNED with its pack while
being separately UNLOCKED. Both also reach **pack grain**: `epilogue` is a whole pack that is
acquired free and unlocked by story.

### What the wire reports

`GET /webapi/user/me` carries three arrays. It needs a live `sid`, so it exists on **t2 and
t3 only** — a t1 (friend-code) player has no path to any of it.

| Array | Grain | Maps onto | Meaning |
|---|---|---|---|
| `packs` | pack | `packs.pack_id`, **exactly** | packs bought |
| `singles` | song | `songs.song_id`, **exactly** | Memory Archive songs bought one at a time |
| `world_songs` | song **and chart** | `songs.song_id`; entries suffixed `3` are that song's **Beyond chart** | held, but not by buying a pack or a single |

Song ids match one-to-one in all three, with **no translation table** — 59/59 packs,
129/129 singles, 95/95 plain ids and 50/50 Beyond entries on the measured account. Catalog
coverage by derivation is **552/552**. So a credentialed player needs **no declaration at
song grain**; only Beyond does (below).

The `<song_id>3` suffix means chart-grain unlock state is on the wire, for Beyond only —
there is no equivalent for Eternal, and none is needed.

**`world_songs` is misnamed: it is everything else.** Not "unlocked in world mode" but
"held, and not accounted for by `packs` or `singles`" — a catch-all the wire fills from
unrelated routes. `chronologia` proves the read: bought after its free window closed, so it
sits in `singles` and **not** here. The array records *how you got it*, not *what it is*.

### Neither array may be read as a denial

**Buying a pack and earning its songs are alternative grants, and they overlap.** The
`extend_*` packs ("Extend Archive") release songs incrementally, free, through world mode;
buying the pack unlocks all of them at once. The measured account disagreed in **both**
directions: it owned `extend` and `extend_2` (20 songs each) while listing only 4 and 2 of
them in `world_songs`, and it listed all 20 of `extend_3` and all 16 of `extend_4` while
owning neither pack.

- **Pack ownership is sufficient, never necessary.** Never infer "does not own the pack ⇒
  cannot play the song".
- **`world_songs` absence is not evidence of a lock.** Positive signal only: present ⇒
  playable, absent ⇒ unknown.

### Beyond: 66 of 67 charts carry an unlock condition

Beyond is the only genuinely gated class — it cannot be opened by ordinary play. It is
**always OWNED with its pack or song** (no Beyond is sold separately) and separately
UNLOCKED:

| UNLOCKED by | Packs | Charts |
|---|---|---|
| a **world-mode map** | `alice`, `base`, `chunithm_append_2`, `core`, `extend`, `groovecoaster`, `mirai`, `nijuusei`, `observer_append_2`, `prelude`, `shiawase`, `single`, `wacca`, `yugamu`, `zettai` | 50 |
| **story progression** | `epilogue`, `finale`, `konzetsu`, `lephon`, `vs` | 16 |
| nothing | `undertale` | 1 |

**Exactly one Beyond in the game — Your Best Nightmare — is playable the moment you buy its
pack.** The split is clean per pack: no pack is partial, which is why the rule is recorded
per pack rather than per chart.

The two unlock values stay distinct rather than collapsing to "locked" because **world-mode
unlocks take time** — a player may simply not have got to it — whereas story is one-off
progression whose cost varies per chart (owner, 2026-09-03). Both mean the same thing to the
bot: **ask the player**. Neither is derivable; both land in `world_songs` when satisfied and
are silent when not.

`is_beyond_unlocked` on `/me` is a separate global flag — whether the player has access to
the Beyond tab at all — and is **not** per-chart.

`byd_2` on `last` comes with its first Beyond: same gate, not separately unlocked (owner).

### Eternal is not an ownership gate

109 songs carry an Eternal chart and no wire array reports their state — correctly, because
there is nothing to report. It behaves like Present or Future: normally locked, but opened
by an ordinary in-game action — spending fragments (a free currency) or clearing other
charts to a grade. No map, no story, no purchase.

**Owning the song is the whole condition.** `playable(etr) = playable(song)` everywhere.
Treat `etr` as playable wherever its song is, and never model it as a grant. An Eternal a
player has not opened is a few minutes of play away, not a thing they lack — which is also
why a tournament pool may draw Eternal freely (owner, 2026-09-03).

### There are no cross-pack grants

A song filed under one `pack_id` is never *given* by owning a different pack. The cases that
look like it are **ordinary world-mode unlocks whose map has a prerequisite** (owner,
2026-09-03): `guardina`'s map wants `dynamix`, `diein`'s wants `djmax`, `desive`'s wants five
other singles, and `acheron` and `chronologia` are plain world unlocks. So the catalog needs
no grant-edge field.

`epilogue` is the one real inter-pack edge, and it is an *acquisition* edge, not a grant of
songs: the pack comes free with `finale` and is then gated behind story.

For a t2/t3 read none of this matters — the wire resolves every route before we see it. It
is the **manual declaration** that has to cope, and it does so by asking **"can you play
this?"**, never "do you own this?". The player knows the answer to the first regardless of
which shape applies; nobody can answer "do you own five of these particular singles, and did
you then clear the map?".

### `world_unlock` is narrower than its name, and 18 rows are wrong

The flag means **"obtainable in world mode"** — nothing about purchase, and nothing about
whether a given player obtained it. It cannot express free-but-not-world-mode: `innocence`
is free via a beginner mission while sitting in the `single` pack, and correctly carries
`False` (owner, 2026-09-03).

18 rows are wrong — 7 unflagged in `extend_3`/`extend_4` (catalog staleness), 11 flagged that
should not be, three of them songs whose *Beyond* carries the unlock. Itemised, with the
resulting counts, in [[h-world-unlock-corrections]]. **Not yet applied.**

`song_difficulties.world_unlock` overrides the song value and **7 rows already use it**, all
`byd`, all `True` over a `False` song — 7 of the 50 world-earned Beyonds. So the schema
already reaches chart grain; it is only recorded for 14% of the cases that need it.

**`base` is free but not wholly given.** 36 of its 64 songs are world-unlockable; the
remaining 28 are available from the start. OWNED and UNLOCKED differ here too.

**Delisting removes access from everyone, buyers included** (owner, 2026-09-03): the song is
replaced in-game and nobody can reach it, so ownership need not model it. One song is
delisted today (`particlearts`), detected by the `_name_` cloak in
`catalog/search.py::is_delisted`.

### Where ownership comes from

| Player | Songs | Beyond charts |
|---|---|---|
| **t2 / t3** (credentialed) | derived from `/webapi/user/me`; no input, no blob | **asked** — the wire reports positively only, and 66 of 67 are gated |
| **t1** (friend code) | manual declaration, `playable = declared ∪ has_score` | same declaration |

Stored at **chart grain** — a row per `(player, song_difficulty_id)` — since Beyond unlocks
separately from its song and the wire already reports at that grain. The declaration surface
is **both** an inline Discord picker and a static page → blob import (owner, 2026-09-03).

**Built 2026-09-06, manual half only** — `/owned`, storing at chart grain in
`owned_charts`, with a pack picker and a Beyond page. See
[[ownership-module|ownership]] for the invariants. Not built: any read of
`/webapi/user/me` (so a credentialed player declares by hand exactly like a t1
player), and the static page → blob import.

**`has_score` turned out to carry most of the load.** A stored play proves its
whole pack outside the three that release song-by-song (`base`, `single`,
`extend_*`) — 25–32 of 61 packs on real accounts, before anyone is asked
anything. Note this sharpens the §Ownership rule rather than contradicting it: a
score is a *positive* signal, and absence still means nothing. `world_unlock` is
not consulted, because a world unlock inside a paid pack still needs that pack
(owner, 2026-09-06) — the map ships inside it.

Measured size of the manual surface, after the [[h-world-unlock-corrections|corrections]]:
**49 packs are one checkbox each** (229 songs), 14 packs need a checkbox *plus* per-song
answers, and the long tail is ~254 searchable song toggles — 120 world-unlockable songs
inside those 14 packs, plus all 134 individually-sold songs in `single`. The pack half fits
in one Discord message.

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
- **Pack ownership does not gate a song.** A pack can be bought *or* its songs earned free in
  world mode (`extend_*` especially), so neither signal implies the other and neither absence
  implies a lock. Deriving "cannot play" from either one is wrong in both directions — see
  §Ownership.
- **`Song.world_unlock` is not the unlock for that song's Beyond.** They are separate facts at
  separate grains, and three rows in the catalog conflate them today (`pragmatism`,
  `designant`, `axiumcrisis` — the *chart* is earned, the song is not). The chart-grain
  override `song_difficulties.world_unlock` is the right home, and is currently used for only
  7 of the 50 world-earned Beyonds. See [[h-world-unlock-corrections]].
- **`world_unlock` does not mean "free".** It means *obtainable in world mode* — so a song can
  be free and carry `False` (`innocence`, unlocked by a beginner mission). Reading the flag as
  a purchase question is wrong in both directions.
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

§Ownership comes from [[ownership-worksheet-2026-09-03]] (measurement + 146 owner answers,
2026-09-03), which outranks it there and supersedes [[handoff-11-ownership-blob|handoff 11]].
