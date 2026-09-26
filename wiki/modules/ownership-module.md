---
type: module
status: active
path: src/coda/ownership/
created: 2026-09-06
updated: 2026-09-06
tags: [module, ownership, catalog, tournaments]
aliases: ["ownership/", "owned_charts", "/owned"]
---

# `ownership/` — what each player can play

Policy lives in [[catalog|Catalog]] §Ownership; this page is the layout and the
invariants the code holds. v1 is a **manual declaration only** — nothing here
reads `/webapi/user/me`, even for a credentialed player.

## Layout

| File | Holds |
|---|---|
| `service.py` | the store: the two predicates, the single write primitive, and every read |
| `picker.py` | catalog rows + declared state → tickable options; labelling and chunking. Pure, no I/O |
| `components.py` | the `own:` custom-id contract, build and parse together |
| `db/models/ownership.py` | `OwnedChart` |
| `extensions/owned.py` | the `/owned` command, its two pages, and the persistent listener |

## Storage is chart grain, and packs are not stored

One table, `owned_charts (arcaea_account_id, song_difficulty_id)`. A pack is a
**fan-out at write time, never a row** — which is what stops a later per-chart
answer needing a precedence rule against a coarser pack row that contradicts it.
This is design call 8.d in [[ownership-worksheet-2026-09-03]], reached directly
rather than migrated into.

A fully-declared account is ~1 800 rows (1 842 charts, 1 833 excluding `err`).

There are **no negation rows**. Presence is the whole meaning, and absence of
every row means *undeclared*, which is a third thing again — see
[[h-absent-declaration-is-unconstrained]].

## The predicate pair is the invariant

Two predicates, and the gap between them is deliberate:

```
_ownable()      = not err, not delisted          -- what a declaration may cover
_pack_granted() = _ownable() and not Beyond      -- what a pack tick GRANTS
```

A pack is **cleared over `_ownable`** so unticking takes its Beyond answers with
it, but **granted over `_pack_granted`** so ticking one never hands back a
Beyond. Written out, one menu's write is:

```
owned  = pack_granted(selected packs)
within = owned ∪ ownable(deselected packs)
```

Two failure modes this shape exists to prevent, both silent:

- Grant and clear over the same narrow set → unticking a pack leaves orphan
  Beyond rows the picker can no longer show and the pool filter still counts.
- Grant and clear over the same wide set → every pack menu re-write wipes the
  Beyond page.

**The pack checkmark counts `_pack_granted` too.** If the writer ever skips a
chart the counter includes, a whole-pack tick can never read as checked and the
picker looks broken with no error anywhere.

## The free pack rides along with the first real answer

`base` is off the picker but **not** out of ownership: `replace` grants
`FREE_PACK_IDS` alongside any write that adds something. Dropping it instead
would turn "not asked" into "cannot play" and strip 64 songs from every declared
player's pools.

It is granted on a *write*, never on merely opening `/owned` — otherwise looking
at the picker and closing it would silently constrain the player to the base
game. And its **20 Beyonds are still asked**: `base` is in the world-unlock list
like any other pack, so only its non-Beyond charts come free.

Unticking a pack leaves `base` in place (it is never inside a chunk's scope);
only `clear_all` removes it, which is what returns an account to unconstrained.

## A stored play proves its pack

`inferred_pack_ids` reads `play_scores`: you cannot score on a song you could not
reach, and outside three packs a song comes only with its pack. Measured against
real accounts, this settles **25–32 of the 61 packs** before anyone is asked
anything — one account's pick list drops from 61 to 29.

The exemption is **per pack and nothing else**: `base` (free), `single`
(individually sold) and `extend_*` (handed out incrementally through world mode)
release song-by-song, so a score inside one proves the song alone.

**`world_unlock` is deliberately not consulted.** A world-mode unlock inside a
paid pack still needs that pack bought, because the map ships inside it (owner,
2026-09-06) — `solitarydream` is world-earned and still proves Eternal Core.
Every song whose map has a *cross-pack* prerequisite (`guardina`, `diein`,
`desive`, `acheron`, `chronologia`) lives in `single` and is exempt already. Not
reading the flag also puts the [[h-world-unlock-corrections|18 stale rows]] out
of reach of ownership entirely.

Inference only ever **adds to** an existing declaration — it can never make an
undeclared account declared, or scores in three packs would read as a claim that
only three are owned. [[h-absent-declaration-is-unconstrained]] still decides
that.

## Proven is not a checkbox — on either page

`Option.locked` marks an answer that evidence already settled, and a locked
option **never reaches a menu**. Two things are locked, for one reason:

| Locked | Proven by |
|---|---|
| a pack | a score on any song that comes only with it (`inferred_pack_ids`) |
| a Beyond | a score on that very chart (`BeyondEntry.proven`) |

The reason is the same in both cases: `playable_chart_ids` unions plays in
unconditionally, so a played chart is playable whatever the menu says. Offering
it as a checkbox offers a choice that cannot be honoured — untick it and the row
deleted changes nothing, while the next render puts the tick straight back.

A *declared* answer stays unlocked: a claim can be retracted, a play cannot.

The locked ones leave the menus and are named in the body instead:

```
-# Already yours, from your scores: Black Fate · Eternal Core · …
```

Two alternatives were rejected. Leaving it in the menu ticked-by-default lets the
player untick it and watch it snap back on the next render, which reads as a bug —
Discord has no per-option disabled state. A whole *disabled* select menu does grey
out convincingly, but a disabled menu cannot be opened, so the names it holds
become unreachable and the player is told a count they cannot verify.

Named rather than counted for the same reason: "3 packs are yours" invites the
question of which, and nothing else in the view answers it. The list degrades to
`+N more` past `LOCKED_NOTE_BUDGET`.

`_pack_state` and `_beyond_state` in the extension are the only places that build
an option list and its menu chunks, so a menu index cannot mean different things
between drawing a message and clicking it — locked options are removed *before*
chunking, and the bulk buttons act on the chunks rather than the full list, so
`None` cannot try to take away a play.

## Beyond is asked, never granted

66 of 67 Beyonds need a world map or story progression that owning the pack says
nothing about, and the wire reports them positively only. So the second page
asks directly, over the Beyonds of songs already declared, prefilled from
`has_score`. Skipping the page leaves them unticked, which is the safe direction
for a pool filter.

The page covers Beyonds of songs **declared or inferred**, and a Beyond with a
`play_score` on that chart arrives ticked *and locked* (above) — so a player who
has been playing opens the page already correct, with only the genuinely open
questions left on it. Measured: one account has 23 Beyonds offered, 15 settled by
plays, 8 left to answer.

Every value on that page is the chart's **effective** one: 53 Beyonds override
`version` (so the spoiler check must be `chart_spoilered`, not `Song.version`)
and 18 charts override `name_en`, including both of Last's Beyonds — reading the
song row would show one name twice and leak a spoilered chart. `alt` renders as
"Inscribed" via `catalog/labels.class_full`.

`byd_2` comes with the first Beyond (owner) but is listed as its own option,
because its effective name is what distinguishes it.

## The picker

61 packs, minus whatever the player's scores already settled. Two are off the
picker permanently, for opposite reasons: `single`'s 134
individually-sold songs are a lie as one checkbox (`/owned song` covers them one
at a time), and `base` is free, so nobody needs asking. That is exactly three
25-option menus on one message, so there is no paging; the layout has room for
four before there would be.

Chunk membership is **recomputed at handle time** from the same deterministic
sort, so a pack that shifted chunks since the message was drawn is left alone
rather than cleared by a stale menu.

Pack labels come from `songs.pack_name`, not `packs.name` — the display name is
per-song and the pack table is stale for `extend_3`. 14 names are shared by 33
packs (`_append_N` splits), disambiguated by the suffix read off the id rather
than by invented numbering.

## Read by

`tournaments/pool.py::qualifying` applies `owned_by_all` **inside** the query
rather than at the call site, because song mode re-derives a round's chart set
from a second call (`match.py::_write_chart_set`) that would otherwise admit the
whole song.

## Known v1 limitations

- **Free-but-earned packs over-approximate.** `base` arriving whole, and any
  `extend_*` tick, marks every song in them playable — though 36 of `base`'s 64
  are world-unlocked and the `extend_*` packs release incrementally. `has_score`
  corrects the common cases; full correctness needs per-song answers inside the
  14 packs [[catalog|Catalog]] §Ownership names. `base` is the worst of these,
  because it is granted rather than chosen.
- **No wire sync.** t2/t3 ownership is exact on `/webapi/user/me` and is not read;
  the schema is what a later sync would write into.
- **`world_unlock` is untouched**, so the [[h-world-unlock-corrections|18 wrong
  rows]] block nothing here.
