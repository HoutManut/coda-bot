---
type: question
status: answered
blocks: ["[[tournaments|Tournaments]]", "song ownership chart-unlock display"]
source: 11-ownership-blob.md
created: 2026-07-21
updated: 2026-09-03
tags: [question, ownership, tournaments, answered]
aliases: ["What has to be settled before the static-picker ownership blob (handoff 11) can be built?"]
---

# What has to be settled before the static-picker ownership blob (handoff 11) can be built?

## Why it is open

**Second consumer as of 2026-07-23**: a proposed song-ownership display
(show which charts a user has actually unlocked, not just owns the song —
PST is always unlocked if owned, BYD/ETR are not) needs exactly item 2 below
answered, independent of Tournaments. Don't research this twice — resolving
item 2 unblocks both.

Handoff 11 is explicitly a **sketch from one conversation, not a design** —
the shape (static page → base64 blob → `/owned import`) is settled, but the
numbers behind it are estimates from memory, not measured, and its only
consumer ([[tournaments|Tournaments]] §9) is itself unbuilt. Four concrete unknowns are
named as gating anything getting built:

1. **The real pack count and per-song granularity.** The doc estimates
   ~110 packs at 3–6 songs each, with roughly 5 packs needing per-song
   (not per-pack) granularity — unmeasured against the actual catalog.
2. **Whether the tournament layer actually wants a per-player playable set**,
   and at what grain — song or chart. Difficulty availability (BYD/ETR
   unlocks specifically) is explicitly **not** covered by this sketch even if
   the rest is built.
3. **Where the static page lives and who regenerates `songs.json`** when the
   catalog changes — an unowned operational question, not a technical one.
4. **The tier-2 owned-packs route is not yet captured** in
   [[arcaea-auth-behavior]] (Tier 2, not re-verified in this
   ingest) — its exact field/route and how its pack identifiers map onto
   catalog `pack_id`s (the doc predicts they "almost certainly do not match
   one-to-one") needs capturing and grading before anything reads it, even as
   the sketch's proposed negative-check-only cross-validation.

## What would answer it

Re-open the design discussion (the doc's own instruction: *"If this is ever
picked up, re-open the discussion first"*) and resolve the four items above
in order — items 1 and 3 are measurement/ops questions answerable without
code; item 2 depends on the tournament layer existing in some form first;
item 4 is a wire-capture task for whoever owns `arcaea-auth-behavior.md`.

## Current best guess

The shape (static page, no auth, append-only blob, store rows not the blob)
is the sketch's own best guess and is reasoned through in detail — see
[[handoff-11-ownership-blob]]. The four numbered items above have no guess
offered; they are named as measurement/decision gaps, not judgment calls.

## Answer

**Answered 2026-09-03** — see [[ownership-worksheet-2026-09-03]] for the measurement
and all 146 owner answers, and [[catalog|Catalog]] §Ownership for the settled model.

The question's framing was wrong, and so was handoff 11's. **The ownership data exists on
the wire.** `GET /webapi/user/me` carries `packs`, `singles` and `world_songs`, every id
maps onto the catalog exactly with no translation table, and catalog coverage by derivation
is 552/552. A credentialed player never needed a blob at song grain.

The four gating items, in order:

1. **Real pack count and per-song granularity — measured.** 63 packs, not ~110. After the
   [[h-world-unlock-corrections|flag corrections]], **49 packs are one checkbox each** (229
   songs) and **14** need per-song answers, not "roughly 5". The long tail is ~254
   searchable song toggles, most of it `single`'s 134 individually-sold songs.
2. **Does the tournament layer want a per-player playable set, and at what grain — yes,
   chart grain.** Intersect the roster's playable sets, as `pool.owned_by_all` already
   promises (owner, 2026-09-03). Storage is a row per `(player, song_difficulty_id)`.
   The sketch's explicit non-coverage of BYD/ETR is now the *most* important part: Eternal
   needs nothing (`playable(etr) = playable(song)`), and **Beyond needs everything** — 66
   of its 67 charts are gated and the wire reports them positively only.
3. **Where the static page lives and who regenerates `songs.json` — mostly moot.** The
   surface is **both** an inline Discord picker and a static page → blob import (owner,
   2026-09-03), and the inline half needs no hosting and no regeneration. The ops question
   survives only for the blob half, and only for t1 players.
4. **The tier-2 owned-packs route — captured.** It is `/webapi/user/me`, and the prediction
   that its identifiers "almost certainly do not match one-to-one" is **wrong**: they match
   exactly, in all three arrays. Graded FACT against one t3 account, 2026-09-03, in
   [[catalog|Catalog]] §Ownership.

**What replaced the blob as the spine**: the owner's OWNED / UNLOCKED split — acquisition
and in-game unlock are two orthogonal facts, both reaching chart *and* pack grain, and
`playable = OWNED ∧ UNLOCKED` with `has_score` as proof of both.

**What is still open**: the [[h-world-unlock-corrections|18 wrong `world_unlock` rows]] are
decided but unapplied.

**Built 2026-09-06** — the manual half, at chart grain, in `src/coda/ownership/` (see
[[ownership-module|ownership]]). `/owned` is a pack picker plus a Beyond page; storage is
`owned_charts`, a row per `(account, song_difficulty_id)`, with packs held as a write-time
fan-out rather than as rows. `pool.owned_by_all` reads it and is no longer a no-op.

Two of the four items above are now settled *by* code rather than by measurement: item 2's
chart grain is what shipped, and item 3's hosting question survives only for the blob half,
which is still unbuilt. **Item 1's per-song answers inside the 14 mixed packs and item 4's
wire derivation are both deliberately out of v1** — a credentialed player currently declares
by hand exactly like a t1 player, and the schema is what a later sync would write into.
