---
type: source
status: active
path: 11-ownership-blob.md
lines: 155
dated: "2026-07-21"
verified: 2026-07-21
supersedes: []
superseded_by: []
created: 2026-07-21
updated: 2026-07-21
tags: [source, handoffs, ownership, tournaments, unresearched]
aliases: ["11 — Ownership declaration via a static picker + pasted blob"]
---

# 11 — Ownership declaration via a static picker + pasted blob

## Covers

A sketch (not a design) for how a tournament song pool could know which
charts each participant can actually play, given lowiro reports owned packs
on tier 2 but **never** reports unlocked state, and reports nothing at all on
the friend path. Directly answers the gap [[tournaments|Tournaments]] §9 names as "out of
scope." **Status: sketch from one conversation, not a design — re-open the
discussion before building.**

## Key claims

- A fully static page (no backend, no auth) encodes a pack/song selection
  into a ~32-char base64 blob, pasted into `/owned import <blob>`. No auth is
  correct here, not a shortcut — the blob is a self-declarative claim that
  proves nothing and is never treated as proof, same reasoning as the
  friend-code path.
- The blob is **transport only** — store the decoded rows, never the blob
  string, so a future layout change (a pack promoted to granular, a reorder)
  cannot retroactively corrupt stored data.
- The pack/song list must be **append-only** on the wire, mirroring the DTO
  sentinel-drift failure class named in `CLAUDE.md` §Security: wrong,
  plausible, and silent if broken.
- `playable = declared ∪ has_score` — a played chart is proof by itself, so
  the blob only has to be right about owned-but-never-played charts. The
  tier-2 pack read is a **negative check** only (flag a declared pack the
  player doesn't own), never a positive union term, since owned-but-locked is
  exactly the case the blob exists for.
- The question the picker should ask is **"can you play this?"**, not
  **"do you own this?"** — for tournament pools that dissolves the
  unlock-vs-own gap at pick time instead of reconstructing it later.
- Numbers cited (pack count ~110, granular-pack list ~5 packs / ~60 songs)
  are **explicitly estimates from memory, not measured**.

## Contradicts / reversed by

None — this is new-territory design, not a reversal of an existing doc. It
does flag that the tier-2 owned-packs route is **not yet captured** in
[[arcaea-auth-behavior]] (Tier 2, outside this ingest) and asks for
that before anything here is built.

## Feeds

[[tournaments|Tournaments]] §9, [[h-ownership-blob-open-before-building]]
