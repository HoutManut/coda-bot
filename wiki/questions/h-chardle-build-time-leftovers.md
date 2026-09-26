---
type: question
status: open
blocks: [chardle]
source: design session 2026-07-27 (edge-case sweep)
created: 2026-07-27
updated: 2026-07-28
tags: [question, chardle]
aliases: ["What is still unsettled in Chardle at build time?"]
---
# What is still unsettled in Chardle at build time?

## Why it is open

The 2026-07-27 edge-case sweep closed almost everything it turned up — those answers went
into [[chardle|Chardle]] and the decision pages rather than here. What is left is the
residue: items that cannot be settled in prose because they need a measurement, a number
picked from play, or a Discord behaviour confirmed against the real API. They are collected
in one page so they are not rediscovered one at a time during implementation.

Board rendering is deliberately *not* here — it is a design decision with its own page,
[[h-chardle-board-rendering]].

## The leftovers

### 1. ~~The inactivity sweep~~ — ANSWERED 2026-07-27

**`started_at` age, default 24 h**, as the scoped setting `chardle_abandon_hours`,
swept by a 30-minute `@loader.task` that closes expired dailies in the same pass.
The original text follows.

#### Original

An abandoned free-play board holds its channel's `UNIQUE (channel_id) WHERE state='playing'`
slot forever. `/chardle play end` covers the polite case; a sweep covers the rest. Unsettled:
whether it reuses `expires_at` (documented today as dailies-only) or sweeps on `started_at`
age, and what the age is. Carried over from [[h-chardle-boards-are-channel-owned]].

The daily side has a partial answer already — stale `playing` dailies are closed on
invocation of `/chardle daily`, so a missed sweep degrades rather than breaks
([[chardle-module|chardle (module)]] §Two input paths). Free play has no equivalent trigger,
because nothing re-invokes on a board nobody is playing.

### 2. `bpm` and `note` yellow thresholds

The only genuinely unsettled *numbers* in the clue table. Starting at ±20 BPM and ±150
notes, as scoped settings, and they need real boards to calibrate. Too wide and the column is
yellow forever; too narrow and it is red forever — both are the dead-column failure in
[[d-chardle-dead-clue-columns]] arriving by a different road.

### 3. ~~Do private threads announce themselves?~~ — ANSWERED 2026-07-27

**No.** Discord's own threads documentation: `THREAD_CREATED` (message type 18) "is currently
only sent in one case: when a `PUBLIC_THREAD` is created from an older message", and "You must
be invited to the thread to be able to view or participate in it, or be a moderator
(`MANAGE_THREADS` permission)."
([Discord — Threads](https://docs.discord.com/developers/topics/threads).) So a private thread
posts nothing in its parent channel and is invisible to everyone but its members and
moderators.

Grade **FACT (Discord docs; no live capture)** — documented, not observed from this bot. The
`MANAGE_THREADS` half is why the reply path still checks the guesser is the session owner; see
[[h-chardle-boards-are-channel-owned]] §A daily is private.

### 4. ~~The ephemeral fallback~~ — ANSWERED 2026-07-27

**Not built.** Transport is private thread → DM → an error naming what to enable.
The original text follows.

#### Original

Transport degrades private thread → DM → ephemeral. The ephemeral leg is the only one that
cannot edit its board (interaction tokens die after 15 minutes), so it re-renders in full on
every guess and has no reply path. Nobody has decided whether that is worth building or
whether a guild denying `CREATE_PRIVATE_THREADS` with the player's DMs closed should simply
be told no.

### 5. Two `chardle_timezone` defaults — ANSWERED 2026-07-28

Noticed 2026-07-27, never a bug in behaviour, and it drifted a second time before it was
closed: the `REGISTRY` key defaulted to `Asia/Bangkok` (`settings/registry.py`) while
`schedule.DEFAULT_ZONE` was `Asia/Phnom_Penh` (this page recorded it as `Asia/Ho_Chi_Minh`
— three spellings of UTC+7 across two files and one wiki page). `_zone()` returns the
registry value and `in_april_window()` reads the schedule one, so the two would diverge the
moment either zone moved its offset.

**Both are now `Asia/Bangkok`**, and since 2026-07-28 they are also the *same* literal:
`coda/utils/zones.py` owns `DEFAULT_ZONE` + `parse_zone`, `settings/registry.py` imports the
constant for the key's default and `chardle/schedule.py` imports both. The engine-at-import
problem that forced two literals is gone because `utils/zones` is pure — the registry never
had to be the thing `schedule` imported, only the zone name did. The key itself is now
`timezone`, not `chardle_timezone`: the same clock decides Chardle rollover and day/night
jacket art ([[h-owner-surface-is-run-terminal]] build, 2026-07-28).

### 6. Delisting mid-game is handled; deletion is not

An answer delisted after its puzzle was created stays winnable through
[[h-chardle-closest-match-always-costs]] §Rule 0. A *deleted* song is different: the FK is
`ON DELETE RESTRICT`, so the admin editor fails loudly instead. That is the intended
behaviour, but it means catalog deletion of anything that was ever a Chardle answer needs a
documented manual path (retire the puzzle first), which does not exist yet.

## What would answer it

**1, 3, 4 and 5 are answered.** 2 still needs play data — the windows ship as
`chardle_bpm_window` (20) and `chardle_note_window` (150) so they can be tuned
without a deploy. 6 remains an owner call.

## Current best guess

Sweep on `started_at` age with a generous window (days, not hours) — a free-play board has no
deadline semantics to borrow, and the constraint it holds is only a *convenience* lock on one
channel. Marked as a guess.

## Answer

Unanswered.

## Related

[[chardle|Chardle]] · [[chardle-module|chardle (module)]] ·
[[h-chardle-boards-are-channel-owned]] · [[h-chardle-closest-match-always-costs]] ·
[[d-chardle-dead-clue-columns]] · [[h-chardle-board-rendering]]
