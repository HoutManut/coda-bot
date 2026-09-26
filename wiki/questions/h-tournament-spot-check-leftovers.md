---
type: question
status: open
blocks: [tournaments — nothing blocking; each item is independent]
source: spot check 2026-09-03 (handoff 13 review)
created: 2026-09-03
updated: 2026-09-03
tags: [question, tournaments]
aliases: ["What did the handoff 13 spot check leave unfixed?"]
---

# What did the handoff 13 spot check leave unfixed?

## Why it is open

The 2026-09-03 spot check of [[handoff-13-tournaments|handoff 13]] fixed two things and
filed the rest. Four of those became pages of their own because they need a decision; what
is left is the residue — small, independent, no decision required, collected here so they
are not rediscovered one at a time.

## Fixed on the day

**The sweep could die, and take tournaments with it.** `@loader.task` defaults to
`max_failures=1`, and lightbulb cancels a task *permanently* on its first failure
(`tasks.py:333`). One transient error would have ended every tournament for the life of the
process, silently. Now `max_failures=-1`, and `service.tick` advances each match inside its
own SAVEPOINT so one wedged match cannot abort the transaction the others share. Covered by
`TestSweepIsolation`.

**The option constants had no owner.** `RULE_CHOICES` and `VISIBILITY_CHOICES` were dead,
and the lists they duplicated were spelled out in the `/tournament quick` picker, the
`/config` enum and `defaults.py` separately. Now one table each in `tournaments/options.py`,
read by all three. It is a leaf because `defaults.py` imports `coda.settings` and
`coda.settings.__init__` imports `registry`, so the tables cannot live anywhere that
imports settings.

## The leftovers

### 1. `act` has no row lock

A pick/ban click landing on the same tick as `service._expire_turn` gives both paths the
same `match.turn_index`; both call `match_ops.act`, and both compute `spawn_round`'s
ordinal as `count + 1`. `uq_tournament_rounds_ordinal` catches it, so no data is corrupted
and the losing transaction rolls back — and since the sweep now survives failures, the
`IntegrityError` is survivable rather than fatal. A `with_for_update` on the match row in
`act` would close it properly.

### 2. `_handle_ready` has no state gate

It writes `ready_at` whatever the match state. The Ready button only renders during
`playing`, so this is reachable only from a stale board — which
[[h-tournament-sticky-board]] is about to make much rarer, and would eliminate.

### 3. `viewbuild.build` is an N+1

Two queries per pool entry (`_chart_ref`, `_song_title`), plus `standings` per round with a
`_chart_ref` per side, plus `service.wins` re-running `standings` over the same closed
rounds it already walked. Roughly 35–40 queries per board draw at Bo5, on a 5 s tick
whenever anything changes. Batching the chart/song lookups and letting `build` hand its
standings to `wins` would take most of it.

### 4. `HOME_TYPES` and the `channel` option disagree

`HOME_TYPES` admits `GUILD_TEXT` and `GUILD_NEWS`, but `Channel.channel` is declared
`channel_types=[GUILD_TEXT]`. An announcement channel is reachable through the "Use this
channel" button and not through the option.

### 5. A failed public thread orphans its anchor

`transport.open_thread` posts the anchor message *then* calls `create_message_thread`. The
anchor is what makes a public thread discoverable at all (Discord emits `THREAD_CREATED`
only for a public thread opened from an older message), so it has to come first — but if
the second call fails, the anchor is left in the home channel pointing at nothing.

### 6. `match.now_ms` may be a duplicate

Worth checking against `scores/` before it becomes three.

## Outside this module

`extensions/approvals.py` and `extensions/chardle.py` carry the same `max_failures`
exposure as the tournament sweep did — one failure cancels them permanently. Much lower
stakes at 5- and 30-minute ticks with no liveness riding on them, but they die just as
silently.

## What would answer it

Nothing to decide. Each item is a small independent fix; 2 is likely to vanish under
[[h-tournament-sticky-board]] and 1 is the only one with any subtlety.

## Answer

Unanswered.

## Related

[[tournaments-module|tournaments (module)]] · [[tournaments|Tournaments]] ·
[[h-tournament-sticky-board]] · [[h-tournament-pool-sizing]] ·
[[h-tournament-window-and-clock]] · [[h-tournament-one-match-per-thread]] ·
[[h-tournament-untracked-participants]]
