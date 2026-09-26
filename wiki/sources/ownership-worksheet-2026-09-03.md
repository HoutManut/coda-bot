---
type: source
status: active
path: (no file — a published worksheet artifact, answered in-conversation)
lines:
dated: 2026-09-03
verified: 2026-09-03
supersedes: ["handoff-11-ownership-blob.md"]
superseded_by: []
created: 2026-09-03
updated: 2026-09-03
tags: [source, ownership, catalog, tournaments, arcaea]
aliases: ["Ownership Worksheet", "Ownership findings 2026-09-03"]
---

# Ownership worksheet — measurement + owner answers (2026-09-03)

## Covers

The complete input to the ownership design. Two halves:

1. **Measured** — the whole catalog (63 packs, 552 songs, 1840 charts) diffed against one
   real `GET /webapi/user/me` payload for a t3 account (2026-09-03).
2. **Owner-stated** — 146 answers to a worksheet built from that diff, plus four
   follow-up rulings that resolved every contradiction the answers contained.

Authoritative on: what the wire reports and at what grain, how Beyond charts actually
unlock, what `Song.world_unlock` really contains, and the shape of a manual declaration.
It **supersedes [[handoff-11-ownership-blob|handoff 11]] wholesale** — see §Contradicts.

The worksheet itself is a published artifact:
`https://claude.ai/code/artifact/a922f478-56de-4a54-83ed-a4643cb9bda8`

## Key claims

### The wire answers song-grain ownership completely, for t2/t3

`/webapi/user/me` carries `packs`, `singles` and `world_songs`. Every id in all three maps
onto the catalog **exactly**, with no translation table — 59/59 packs, 129/129 singles,
95/95 plain `world_songs` ids, and 50/50 `<song_id>3` Beyond entries. Coverage of the
552-song catalog by derivation is **552/552** (after the three defects in §Catalog defects
were fixed).

- Grade: **FACT**, one account, one day.
- Consequence: a credentialed player needs **no declaration at song grain**. This is the
  single largest correction to handoff 11, which assumed the data did not exist.

### `world_songs` is misnamed: it is "everything else"

Not "unlocked in world mode" — **"held, and not accounted for by `packs` or `singles`"**.
Five `single`-pack songs the account held without buying arrived by different routes and
all landed in the same array. `chronologia` proves the read the other way: bought after its
free window closed, so it sits in `singles` and **not** in `world_songs`. The array records
*how you got it*, not *what it is*.

### Buying and earning are alternative grants, and both signals lie by omission

The `extend_*` packs release songs incrementally and free through world mode; buying the
pack unlocks them all at once. The measured account disagreed in **both directions**:

| | measured |
|---|---|
| owns `extend` / `extend_2` (20 songs each) | only 4 and 2 listed in `world_songs` |
| owns neither `extend_3` nor `extend_4` | all 20 and all 16 listed in `world_songs` |

So **pack ownership is sufficient, never necessary**, and **absence from `world_songs` is
not a lock**. Neither array may be read as a denial.

### Beyond: 66 of 67 charts carry an unlock condition

This is the finding that reshaped the design. The worksheet asked for a per-pack "BYD rule"
and got `included` for six packs; §4 then ruled 16 of those same charts `story`. That read
as a contradiction. The owner's ruling (2026-09-03) is that **it is not one — they are two
independent axes**:

| Axis | Values | What it decides |
|---|---|---|
| **Acquisition** | with the pack / with the song | whether money is involved. For Beyond it is *always* "with its pack or song" — no Beyond is sold separately. |
| **Unlock** | none / `world` / `story` | what must be done in-game before it can be played |

`included` was answering the acquisition axis; `story` was answering the unlock axis. Both
are true of the same chart. Resolved per pack:

| Unlock | Packs | Beyond charts |
|---|---|---|
| `world` | `alice`, `base`, `chunithm_append_2`, `core`, `extend`, `groovecoaster`, `mirai`, `nijuusei`, `observer_append_2`, `prelude`, `shiawase`, `single`, `wacca`, `yugamu`, `zettai` | 50 |
| `story` | `epilogue`, `finale`, `konzetsu`, `lephon`, `vs` | 16 |
| none | `undertale` | 1 |

**Exactly one Beyond chart in the game — Your Best Nightmare — is playable the moment you
buy its pack.** Everything else has to be earned.

Owner's ruling on why the two unlock values stay distinct rather than collapsing to
"locked": *"world mode unlocks takes time so thats why we separate it. there are some
hard/long story unlock process but thats why we ask per chart."* Both mean **ask the
player**; the distinction is descriptive, and per-chart asking is required because the cost
of a story unlock varies.

- Grade: **OWNER-STATED**. The `world`/`story` split is not observable on the wire — both
  land in `world_songs` when satisfied, and both are silent when not.

### Unlock conditions exist at pack grain too

`epilogue` (Silent Answer) is not bought: it comes free with `finale`, and the **whole pack
is gated behind story progression** (owner, 2026-09-03). So the unlock axis is not
Beyond-only, and a pack is not always a purchase. The worksheet's `bundle` kind — "only
sold inside a larger bundle" — was the wrong shape for it; what `epilogue` needs is a
*granted-by* edge plus a pack-grain unlock condition.

### Eternal is not a gate at all

109 songs carry an Eternal chart and no wire array reports their state — correctly, because
there is nothing to report. Eternal behaves like Present or Future: normally locked, opened
by an ordinary in-game action (spending fragments, a free currency; or clearing other charts
to a grade). No map, no story, no purchase. **Owning the song is the whole condition**, so
`playable(etr) = playable(song)` everywhere.

This *removes* work: no Eternal column in the pack table, no per-pack rule, no per-song
exception list, nothing for a manual declaration to ask.

Tournament policy on it (owner, 2026-09-03): **draw Eternal into pools freely.** The unlock
is cheap and every participant can do it.

### There are no cross-pack grants

The worksheet claimed `guardina` was granted by owning `dynamix`, and `diein` by owning
`djmax`, and built a whole "the catalog cannot express cross-pack grants" section on it.
**That premise is wrong** (owner, 2026-09-03): *"acheron, guardina, diein and chronologia
are world unlock. just that their world mode map requires other pack/songs."*

They are ordinary world-mode unlocks whose **map** has a prerequisite. Nothing is granted by
owning something else. `desive` is the same shape with a count as its prerequisite (five
other singles open its map, which then has to be played).

Consequence: the catalog needs no grant-edge field, and a manual declaration needs no
special handling. Asking *"can you play this?"* dissolves every one of these shapes,
because the player simply knows.

### `Song.world_unlock` is 18 rows wrong, and means something narrower than its name

The flag means **"obtainable in world mode"** — nothing about purchase, and nothing about
whether a given player obtained it. It does not cover free-but-not-world-mode songs:
`innocence` is free via a beginner mission while sitting in the `single` pack, and carries
`False` (owner, 2026-09-03: the point of raising it was *"that it doesnt require purchase
while being in the single pack"* — the flag has no way to say that).

The 18 wrong rows are itemised in [[h-world-unlock-corrections]]. Two clusters:

- **7 songs unflagged that should be flagged** — `extend_3` and `extend_4` release
  incrementally and the catalog never caught up. The owner confirmed **all 20** of
  `extend_3` and **all 16** of `extend_4` are world-unlockable (`extend_4` is still
  filling — *"will be 20 by the end"*).
- **11 songs flagged that should not be** — across `core`, `lephon`, `rei`, `yugamu`, `vs`
  and `single`.

### The chart-grain flag is already half-used, inconsistently

`song_difficulties.world_unlock` overrides the song value, and **7 rows already carry it**
— `inkarusi`, `libertas`, `viciousheroism`, `heavenlycaress`, `einherjar`, `eccentrictale`,
`snowwhite`, all `byd`, all `True` over a `False` song. Those are 7 of the 50 world-earned
Beyonds; the other 43 have no such row. So chart-grain unlock state is *expressible today*
and is being recorded for 14% of the cases that need it. Purely inconsistent seed data —
but it does show the schema already reaches the right grain.

### Manual declaration: the measured shape

After the corrections in [[h-world-unlock-corrections]] are applied:

| | before (worksheet) | after (corrected) |
|---|---|---|
| packs with no world-unlockable song — one checkbox each | 46 | **49** |
| songs in those packs | 210 | **229** |
| packs needing a checkbox *plus* per-song answers | 17 | **14** |
| world-unlockable songs inside them | 129 | **125** |
| individually-sold songs in `single` | 134 | 134 |
| **searchable song toggles** | 263 | **254** |

(The worksheet's 263 also double-counted `single`'s flagged songs, which get toggled as
singles regardless; the honest before-figure was 255.)

So the whole manual surface is **49 pack checkboxes plus ~254 searchable song toggles**,
plus the Beyond asks. The pack half fits in one Discord message.

### Catalog defects found and fixed on 2026-09-03

Backup taken first (`backups/coda-songs-20260903-120601.dump`).

- `waltzforlorelei` and `mvurbd` carried `pack_id = "Rotaeno Collaboration"` — the pack's
  display *name* used as an id, beside a real `rotaeno` row. Both repointed at `rotaeno`;
  the duplicate pack row deleted. It was the only pack pair where one id was a display
  name; every other shared name is a legitimate `_append_N` split.
- `remindthesouls` sat in `single` while its `pack_name` said `"Arcaea"` — the lone
  dissenter among 135 rows. Moved to `base`.
- Derived coverage went 549/552 → **552/552**.
- Side effect: this fixed [[chardle]], whose pack clue compares `pack_id` — the five
  Rotaeno songs had been scoring as two different packs.

### Smaller rulings

| Question | Owner answer (2026-09-03) |
|---|---|
| `byd_2` on `last` | Comes with the first Beyond — same gate, not separately unlocked. Both are `story` via `epilogue`. |
| The 7 `err` charts | **Not in scope** for ownership at all. |
| Delisted songs | Ownership does **not** survive. *"completely removed. it was replaced ingame and no one can access it anymore"* — buyers lose access too, so there is nothing to model. Exactly one song is delisted today (`particlearts`), detected by the `_name_` cloak in `catalog/search.py::is_delisted`. |
| `extend_3` name | Stale. Should be **"Extend Archive 3"** (stored: "World Extend 3"). |
| `extend_4` name | **Correct as stored** — "World Extent 4" is the live name; do not rename. (Consistent with the pack still filling: packs appear to be renamed to "Extend Archive N" once complete. *Inference, not stated.*) |
| `base` free-but-not-given | 36 of 64 songs are world-unlockable. Deferred into the OWNED/UNLOCKED model below rather than answered. |
| Other `/me` fields | `world_unlocks`, `cores`, `curr_available_maps`, `memory_boost_tickets`, `banners`, `user_missions` — *"unrelated"*. All empty on the measured account; none carry ownership. |

### The design calls

| # | Question | Answer |
|---|---|---|
| 8.a | Song-grain ownership, t2/t3 | **Derived from `/webapi/user/me`.** No user input, no declaration, no blob. |
| 8.a2 | Beyond, the class the wire reports only positively | **Ask the player.** Not a catalog-side rule. |
| 8.b | Friend-code-only (t1) player | **Manual declaration**, plus `playable = declared ∪ has_score`. |
| 8.c | Declaration surface | **Both** — inline Discord *and* a static page → blob import. |
| 8.d | Storage grain | **Chart** — a row per `(player, song_difficulty_id)`. |
| 8.e | Does the tournament pool filter want this? | **Yes** — intersect the roster's playable sets, exactly as `pool.owned_by_all` promises. |

Two things to hold together when reading these:

- **8.a and 8.a2 are not in tension.** 8.a is scoped to *song* grain. Beyond is chart grain,
  and 66 of its 67 charts are gated, so it needs input from **everyone** — credentialed
  players included, not just t1.
- **8.a2 does not make the per-pack Beyond table dead.** The table still says *which* charts
  to ask about, and `world` vs `story` still shapes how the question reads.

### The one directive `§8` never asked for

> *"we should have a whole new OWNED and UNLOCKED system"* — owner, 2026-09-03

This is the spine of the design, and it is the correct diagnosis of why `world_unlock` is a
mess: one boolean on `Song` is carrying two orthogonal facts at the wrong grain —

- **OWNED** — did this player acquire it (bought the pack, bought the single, or got it free)?
- **UNLOCKED** — has this player satisfied the in-game condition to play it (world map,
  story, beginner mission, fragments)?

Every confusing case in this document is one of the two being read as the other. Pack
ownership sufficient-not-necessary is OWNED. Beyond `world`/`story` is UNLOCKED. `base`
being free but not wholly given is *"OWNED, partly UNLOCKED"*. `innocence` free-via-mission
is *"OWNED without purchase, UNLOCKED by a mission"*. And **playable = OWNED ∧ UNLOCKED**,
with `has_score` as proof of both.

## Contradicts / reversed by

**Reverses [[handoff-11-ownership-blob|handoff 11]] on its central premise.** Handoff 11
assumed no ownership data existed on the wire and designed a static page → base64 blob →
`/owned import` around that absence. The data exists and is exact for t2/t3. The blob
survives only as *one of two* surfaces for t1 players (8.c), not as the mechanism. Its
numbers were estimates from memory (~110 packs at 3–6 songs); measured, it is 63 packs and
the distribution is nothing like that.

**Reverses this page's own worksheet in three places**, all recorded above: the "cross-pack
grants" section (premise wrong), the "`included` Beyonds are safe" claim (16 of 17 are
story-gated), and the claim that every one of the 17 missing Beyonds was playable by pack
ownership.

**Narrows [[tournaments|Tournaments]] §Traps.** "Song ownership is out of scope as a
validity or ranking input" (owner, 2026-07-17) still holds for *ranking*; 8.e makes it an
active *pool* filter rather than a permanent no-op.

**Does not touch** [[score-mapping|Score Mapping]] or [[potential|Potential]] — ownership is
a read-side filter and never affects how a played score resolves or rates.

## Feeds

[[catalog|Catalog]] §Ownership · [[h-ownership-blob-open-before-building]] (answered) ·
[[h-world-unlock-corrections]] · [[tournaments|Tournaments]] §Traps ·
[[handoff-11-ownership-blob]] (superseded)
