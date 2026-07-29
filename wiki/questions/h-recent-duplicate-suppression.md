---
type: question
status: answered
blocks: []
source: 08-live-updates-poster.md
created: 2026-07-21
updated: 2026-07-24
tags: [question, live-updates, built, recent]
aliases: ["Should a staggered live update for a play `/recent` already showed be suppressed, or only delayed?"]
---

# Should a staggered live update for a play `/recent` already showed be suppressed, or only delayed?

> [!success] Built
> Built 2026-07-24 in `src/coda/scores/suppression.py`, marked in `extensions/recent.py`, checked in `scores/poster.py`.

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

**Answered 2026-07-24: suppress, not merely delay.** Design in
[[live-updates-suppression|Live Updates — Suppression]].

What tipped it is a fact the question above does not state: **`/recent` causes
the duplicate**. It calls `coordinator.request_refresh(key)`, which drives a real
poll cycle, which ingests the play, which produces the `new_plays` the poster
consumes. So the duplicate is not occasional — it follows *every* `/recent` that
surfaces a play the poller had not yet stored. "Under-suppress and every
`/recent` guarantees a visible duplicate" is exactly what happens.

**Marker key: `(destination, play_score_id)`**, in-memory, TTL 15 minutes,
pruned lazily. `destination` is a `channel_id` or `("dm", discord_id)`.

The question worried about keying: *per-channel? DM vs guild channel?* Both are
resolved by the poster sending **once per destination** rather than once per
linked Discord user (§5.5) — with one message per surface, "who requested it"
stops mattering and only "did this surface already show the play" does.
`/recent`'s success reply is public (`ctx.defer()` with no `ephemeral`), so a
channel that answered `/recent` genuinely showed the play to everyone watching,
co-linkers included. A DM destination carries its `discord_id` in the key, so one
user can never suppress another's DM.

Set in `/recent` before it responds, and only when `resolve_destination` agrees
the reply is going to the user's own live destination — so `/recent` run in a
different channel suppresses nothing.

**A rejected alternative worth recording**: "skip the poster on on-demand
cycles". It looks free — the poller already knows `periodic` — but `/recent` on a
friend-path account targets a BOT key covering *every friend on that bot
account*, so it would silently and permanently drop other players' updates.
`ingest` returns a play exactly once, ever, so nothing recovers it on a later
cycle.

The race (poster sends before the marker is set) is closed by the poster's
`INITIAL_DELAY` plus checking the marker immediately before send rather than at
enqueue time.
