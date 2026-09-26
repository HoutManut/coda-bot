---
type: domain
status: active
source: conversation 2026-07-29
verified: 2026-07-29
grade: A
created: 2026-07-29
updated: 2026-07-29
tags: [domain, arcaea, ownership, catalog]
---
# Ownership

## Model

Three states, not two — this contradicts any page or note that treats ownership as a
binary owned/not-owned flag:

- **Not owned** — song never purchased.
- **Owned** — song purchased (directly, or via a pack), but individual charts on it may
  still be locked.
- **Unlocked** — a **per-chart** flag underneath an owned song. PST is always unlocked
  once the song is owned (except hidden/special songs); BYD/ETR frequently are not. Most owned songs fall into this
  "owned but chart-gated" bucket — it is the common case, not an edge case.
  **Some songs' extra unlock effort spans the whole song, not just BYD** — a minority of
  owned songs (hidden/special ones) still gate basic access behind an in-game condition,
  not just the harder charts. Don't assume "owned" ⇒ "PST at least is playable" holds
  universally; it's the common case, not a guarantee.

**Unlock method is untracked by design.** In-game unlock methods vary per chart and sometimes
depend on other songs being unlocked first (memory-chapter gates, clear-based unlocks,
etc.) — mechanism is out of scope for coda-bot. We never compute or verify unlock
state; we **trust the player's claim** and **passively derive** it: submitting a score
for a chart is itself the evidence that chart is unlocked. See §Traps for what this
does and doesn't settle.

## Ownership sources (wire)

`/user/me` carries three separate lists, no combined "owned songs" field:

| Field         | Contents                             | Resolves to song via                              |
| ------------- | ------------------------------------ | ------------------------------------------------- |
| `packs`       | pack ids owned                       | pack → songs join (existing catalog pack model)   |
| `singles`     | song ids purchased individually      | direct — already song ids                         |
| `world_songs` | song ids, or song id + trailing difficulty ordinal | direct; a trailing digit is a `DifficultyClass` ordinal (`3` = BYD, confirmed) meaning World Mode granted *that chart* specifically — see [[h-world-songs-id-mapping]] |

A song is owned if it appears via any of the three, **with one exception**: songs under
the `base` pack (the free starter catalog, 62 songs) are owned by every player
unconditionally and **never appear in `packs`, `singles`, or `world_songs` at all** — the
live capture confirms `base` is simply absent from the wire `packs` list even though the
account plainly owns every base song. Ownership resolution must special-case
`song.pack_id == "base"` as always-owned, not rely on wire-list presence for it. This is
why a World Mode BYD grant can show up as a standalone suffixed entry (`fairytale3`, no
bare `fairytale`) — `fairytale` is a `base`-pack song, so it has no plain `world_songs`
entry to pair with, not because the grant is unconditional (see §Chart unlock).

**Owned pack implies owned songs in
that pack — except for `single` and `extend_*` pack types**:

- `single` packs group songs that are each **purchasable separately** — owning the pack
  does not imply the grouping is the purchase unit; treat membership like any other
  pack normally would (this exception is about how the pack is *sold*, not a different
  resolution rule — flag if this reads as tautological once re-examined against wire
  data).
- `extend_*` packs roll songs out one at a time across updates, free for the first few
  weeks per song, then folded into a purchasable pack for anyone who missed the window
  or didn't want to grind World Mode for it. Owning the `extend_*` pack **does** imply
  owning every song in it, same as a normal pack — the exception is only that some of
  those songs may *also* be reachable for free (via World Mode) independent of the pack.

World Mode is a separate acquisition path: obtain certain songs at no paid-currency cost by
progressing a world map. Some world maps require an already-owned pack/single regardless,
so World Mode is not a strict "free path" — it can be gated behind the same purchases above.
A world map node can also grant a **specific chart** on an already-owned song, not just the
song itself — see below.

## Chart unlock


- **World Mode BYD grants are wire-visible.** A `world_songs` entry with a trailing `3`
  (the `DifficultyClass` ordinal for BYD) means World Mode unlocked that song's **BYD
  chart specifically**, via a separate map node from the song's own acquisition node.
  **Owning the song is a precondition to start that node** — you cannot begin the
  BYD-unlock map without already owning the song, from *any* source (base/free, single,
  pack, or a plain World Mode grant). So a standalone `X3` with no bare `X` in the same
  list (`fairytale3`, no `fairytale`) does **not** mean the grant is independent of
  ownership — it means the song's ownership came from a source other than a plain World
  Mode grant (here: `fairytale` is under the `base` pack, free/pre-owned for everyone, so
  it never gets its own `world_songs` entry — see the `base`-pack note below). Confirmed
  against a live `/user/me` capture (2026-07-29), both paired (`goodtek` + `goodtek3`)
  and standalone (`fairytale3`) cases present. **ETR (`4`) is never granted via World
  Mode** — confirmed, not just unobserved; ETR is unlocked through other means entirely
  (memory-chapter gates, etc.) that never carry onto the wire — same wire-invisible
  bucket as everything in the next point below. PST/PRS/FTR (`0`/`1`/`2`) also never get
  a `world_songs` suffix, but don't read that as "always auto-unlocked once owned" — per
  §Model, a minority of songs gate the whole song behind an in-game condition regardless
  of difficulty; that gap is just as wire-invisible as the ETR case, it's only usually
  small.
- **Everything else is still not wire-visible.** Course rewards, memory-chapter gates,
  clear-based unlocks, and BYD/ETR unlocks obtained any way other than a World Mode grant
  report nothing to `/user/me`. For those, coda-bot supports **both** access patterns
  depending on the consuming feature:
  - **Trust-only, no storage**: take the player's claim at face value, no persisted
    unlock record (e.g. simple display use cases).
  - **Passive derivation**: a chart is treated as unlocked once the player has a
    recorded score for it (the score row itself or a separate unlock
    table is undecided). This is the mechanism tournaments need to build a per-player playable pool
    (participants' unlocked charts), and it resolves item 2 of
    [[h-ownership-blob-open-before-building]].

Whether "passive derivation via score row" plus the World Mode BYD signal together form
the complete model, or an explicit unlock table is still needed for the remaining
non-world unlock methods, is **not settled** — see [[h-passive-unlock-model-unsettled]].

## Traps

- Don't treat "song owned" as "all charts playable" — BYD/ETR gating is the common
  case, not rare. A minority of hidden/special songs gate the *whole song*, not just
  BYD/ETR — don't assume PST is always safe either.
- Don't infer unlock from pack/single ownership — those only prove the **song** is owned,
  never chart-level state.
- `world_songs` **can** carry chart-level signal — a trailing `3` means BYD was unlocked
  via that world node specifically. Don't collapse it back to song-level ownership by
  stripping the digit and discarding what it meant.
- `single`/`extend_*` are the only two pack types where "owned pack → owned songs" needs
  a second look before assuming the normal pack-owns-everything rule applies verbatim.

## Source

Conversation, 2026-07-29 — no archived source doc; captured directly from the owner's
answers, then re-verified against a live `/user/me` capture (`assets/me_sample.json`,
gitignored) and the live catalog DB same day. `packs` (58/58) and `singles` (127/127)
match `pack_id`/`song_id` in the DB with zero misses; `world_songs` misses were exactly
the difficulty-ordinal-suffixed entries, zero stragglers. Owner states the sample
contains all possible owned-value shapes currently reachable in-game.
