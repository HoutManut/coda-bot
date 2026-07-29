---
type: question
status: open
blocks: ["[[tournaments|Tournaments]]", "song ownership chart-unlock display"]
source: 11-ownership-blob.md
created: 2026-07-21
updated: 2026-07-23
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

Not yet answered.
