---
type: question
status: open
blocks: ["[[tournaments|Tournaments]]", "song ownership chart-unlock display"]
source: 11-ownership-blob.md
created: 2026-07-21
updated: 2026-07-29
tags: [question, ownership, tournaments, unresearched]
aliases: ["What has to be settled before the static-picker ownership blob (handoff 11) can be built?"]
---

# What has to be settled before the static-picker ownership blob (handoff 11) can be built?

## Why it is open

**Second consumer as of 2026-07-23**: a proposed song-ownership display
(show which charts a user has actually unlocked, not just owns the song —
PST is always unlocked if owned, BYD/ETR are not) needs exactly item 2 below
answered, independent of Tournaments. Don't research this twice — resolving
item 2 unblocks both.

**Item 2 answered 2026-07-29**: the ownership model (three states, per-chart
unlock, passive derivation via score submission) is now designed — see
[[ownership|Ownership]]. Two sub-gaps spun off as their own questions rather
than closing this one outright: [[h-world-songs-id-mapping]] (wire-namespace
gap, now answered) and [[h-passive-unlock-model-unsettled]] (owner explicitly
unsure if score-row-as-evidence is the complete model, now narrowed but still
open). Items 1, 3, 4 below are unaffected and still open.

**A bigger fork surfaced 2026-07-29, upstream of items 1/3/4**: this entire
blob mechanism (static page → base64 → `/owned import`) was designed on the
premise that ownership is unreadable from the wire. That premise only holds
for **friend-path** players. Creds-path registration
(`register_by_credentials`, `src/coda/players/service.py:215-294`) stores the
player's own encrypted credentials and can call `/user/me` directly as that
player via `PlayerSessionProvider`/`PlayerCredentialAdapter`
(`src/coda/players/session.py`) — ownership is just a wire read for those
players, no blob needed. Whether the blob mechanism should exist at all, or
only as a friend-path fallback, is now the first thing to settle. **Owner
expects friend-path to be the majority registration path** at this project's
scale (small trusted friend group, but still a real bar to hand over a real
password) — so the blob is not a niche fallback, it's the mechanism most
players' ownership display would depend on. Exact scope (blob for
friend-path only vs. uniformly for everyone, even creds-path players who
could get a live read instead) is still **undecided** — not resolved either
way as of 2026-07-29. Not tournaments-first either: owner confirmed this
reopening is about the ownership/World-Mode display, not the tournament
layer — treat item 2 below as deferred, not gating.

**Item 1 answered 2026-07-29** (measured against the live catalog DB, not the
doc's memory-based estimate): 57 distinct packs, not ~110. Average 8.49
songs/pack, not 3–6. Exactly 4 packs need per-song (not per-pack) granularity,
not ~5: `single` (117 songs — each independently purchasable despite being
grouped under one pack id) and `extend`/`extend_2`/`extend_3` (~20 songs
each, per-song-unlock-window packs). No pack has exactly 1 song.

Handoff 11 is explicitly a **sketch from one conversation, not a design** —
the shape (static page → base64 blob → `/owned import`) is settled, but the
numbers behind it are estimates from memory, not measured, and its only
consumer ([[tournaments|Tournaments]] §9) is itself unbuilt. Four concrete unknowns are
named as gating anything getting built:

1. ~~**The real pack count and per-song granularity.**~~ **Answered** —
   see above: 57 packs, avg 8.49 songs/pack, 4 packs need per-song grain.
2. **Whether the tournament layer actually wants a per-player playable set**,
   and at what grain — song or chart. Difficulty availability (BYD/ETR
   unlocks specifically) is explicitly **not** covered by this sketch even if
   the rest is built.
3. **Where the static page lives and who regenerates `songs.json`** when the
   catalog changes — an unowned operational question, not a technical one.
4. **Reframed then decided, 2026-07-29.** There is a route that can give
   **per-chart score data we don't currently store** (a stronger unlock
   signal than passive score-row derivation, and independent of it) — but
   using it means calling it once per chart per player, which the owner
   flagged as a "should we spam this route" cost/abuse question, not a
   technical one. **Decided: not using it for now.** Stick to passive
   score-row derivation + the World-Mode BYD signal
   ([[h-world-songs-id-mapping]]) as the unlock-evidence sources. Revisit only
   if a real need shows up later. (Original framing — an uncaptured "tier-2
   owned-packs" field/route referenced in [[arcaea-auth-behavior]] — may or
   may not be this same route; moot for now since it's not being used.)

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

Not yet answered.
