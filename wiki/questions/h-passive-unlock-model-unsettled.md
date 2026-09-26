---
type: question
status: open
blocks: ["[[tournaments|Tournaments]]", "[[ownership|Ownership]] chart-unlock tracking"]
source: conversation 2026-07-29
created: 2026-07-29
updated: 2026-07-29
tags: [question, ownership, tournaments, unresearched]
---
# Is "chart unlocked iff a score row exists for it" the complete unlock model, or does it need an explicit unlock table too?

## Why it is open

The owner confirmed unlock is passively derived — a submitted score is evidence a
chart was unlocked — but was explicitly **unsure** whether that derivation alone is
sufficient, or whether a separate persisted unlock flag/table is still needed
alongside it (e.g. to represent "unlocked but no score yet" for tournament pool
building, where a participant's playable set may need to be known *before* they've
played a chart).

## What would answer it

Design pass once [[tournaments|Tournaments]] needs a concrete playable-pool query —
figure out whether "has a score row" is queried at the right time for that use case,
or whether pool-building needs unlock state independent of score history.

## Current best guess

Score-row-as-evidence is the working default (see [[ownership|Ownership]] §Chart
unlock), but marked unsettled rather than final.

**Update 2026-07-29**: [[h-world-songs-id-mapping]] found that World Mode BYD grants
*are* wire-visible — a `world_songs` entry suffixed with `3` means that song's BYD chart
was unlocked via World Mode, independent of any score row. That's a second source of
"unlocked but no score yet" for the World-Mode-BYD case specifically, which is exactly
the gap this question raised for tournament pool building. It does not close the
question generally: non-World-Mode unlock paths (course rewards, memory-chapter gates,
clear-based unlocks) are still wire-invisible and still need either passive derivation
or an explicit table. Narrows the open surface; doesn't settle it.

## Answer

Not yet answered.
