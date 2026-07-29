---
type: question
status: open
blocks: []
source: 08-live-updates-poster.md
created: 2026-07-21
updated: 2026-07-21
tags: [question, live-updates, recent, unbuilt]
aliases: ["Should a staggered live update for a play `/recent` already showed be suppressed, or only delayed?"]
---

# Should a staggered live update for a play `/recent` already showed be suppressed, or only delayed?

## Why it is open

`/recent` jumps the queue by construction: it answers its own interaction
immediately, and the poster's own per-destination stagger means any live
update for that same play naturally lands after the `/recent` reply with no
extra mechanism needed. That much is settled.

What is explicitly *not* decided is whether that trailing live update should
still be sent at all. The user has already seen the score via `/recent`;
posting it again to the same channel moments later reads as a duplicate. But
suppressing it needs a rule for "already shown to this destination" that
does not exist yet — and applying it wrong either way is a real cost: over-
suppress and a live update silently vanishes when `/recent` was run in a
*different* channel than the one the update was headed to; under-suppress
and every `/recent` invocation guarantees a visible duplicate shortly after.

## What would answer it

A decision, not a build: pick delay-only (simpler, occasional visible
duplicate) or delay-plus-suppress (needs a short-lived "just showed this in
this destination" marker, keyed by destination + play identity, that the
poster consults before sending). If suppression is chosen, decide the marker's
lifetime and exactly what it keys on (per-channel? per-user DM vs. guild
channel are different destinations for the same account).

## Current best guess

None ventured — the source flags it as open rather than defaulting to either
behavior.

## Answer

Not yet answered.
