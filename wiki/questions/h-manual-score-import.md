---
type: question
status: open
blocks: ["manual score import feature"]
source: conversation 2026-07-23
created: 2026-07-23
updated: 2026-07-23
tags: [question, scores, potential, unresearched]
aliases: ["What does manual score importing need before it can be built?"]
---

# What does manual score importing need before it can be built?

## Why it is open

Scope itself is unsettled: "manual import" was raised without specifying
whether it means a single hand-typed `/addscore`-style entry, or a bulk
import from an external source (e.g. an overlay tool's exported JSON/CSV).
The two need very different validation designs and should not be conflated
with [[h-backfill-worth-building|score-history backfill]] (handoff-10),
which is bot-driven historical pull via the wire API, not user-submitted data
— related concept, different trust model, different mechanism.

**Partially settled by [[h-t0-manual-tier-b30]]:** manual entries DO feed
b30, at least for the new **t0** tier (no account link at all) — a fake
manual entry only misleads its own owner, so no verification/marking
machinery is needed to guard against it. If a t0 user later links an
account, the wire data simply replaces the manual entries (a typo/stale
correction, see that decision). What it leaves open: whether
*linked* accounts also get a manual-import path, and all mechanics below.

## What would answer it

- Settle single-entry vs bulk-import scope first — changes everything below it.
- Decide storage shape: same `play_scores` table with an `is_manual`/`source`
  flag, or a separate table — check current schema in [[scores]] and [[db]]
  before designing new columns.
- Decide whether *linked*-account manual entries feed b30/r10/PTT the same way t0's do, or are handled differently since a linked account already has a wire-sourced number to reconcile against.
- Reuse existing chart-resolution validation ([[chart-resolution]],
  score-mapping's `byd_2`/`game_song_id` handling) for any submitted
  `(song, difficulty)` pair rather than writing new lookup logic.
- Decide self-service vs admin-only entry — given the <50-user scale
  constraint, self-service is more consistent with how the rest of the bot is scoped; don't build an approval workflow unless a concrete abuse case shows up.

## Current best guess

t0 (no link): manual entry feeds b30, no special marking needed — settled,
see [[h-t0-manual-tier-b30]]. Linked accounts: open, but the same
self-facing-tool reasoning likely applies. Single-entry vs bulk import:
leaning single-entry, not settled.

**2026-07-23**: the b30 *read* side no longer waits on any of this.
`B30Service.compute` ([[h-b30-cache-stores-sum]]) is source-agnostic — it
never branches on `play_scores.source`, so a future `'manual'` value slots in
next to `'friend'`/`'own'` with zero changes to `b30.py`. What's still open
here is purely the *write* side: how a manual row (and, prior to that, a t0
`ArcaeaAccount` row with no `arc_user_id`/`friend_code`) gets created at all.

## Answer

Not yet fully answered — see [[h-t0-manual-tier-b30]] for the part that is.
The b30-consumption half is answered ([[h-b30-cache-stores-sum]]); the
row-creation mechanics below are not.
