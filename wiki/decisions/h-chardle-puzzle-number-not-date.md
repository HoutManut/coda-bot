---
type: decision
status: active
date: 2026-07-27
reverses:
created: 2026-07-27
updated: 2026-07-27
tags: [decision, chardle, timezone, stats]
aliases: ["Dailies are numbered globally; guild timezone moves only the unlock instant"]
---

# Dailies are numbered globally; guild timezone moves only the unlock instant

## Context

Two requirements for [[chardle|Chardle]]'s daily were chosen together and, stated
naively, contradict each other:

- **Per-guild rollover.** Each guild configures its own timezone, so the daily resets at
  a sane local hour rather than whenever UTC midnight happens to land.
- **Global per-user stats.** Streaks belong to the player, not to a guild, so solving in
  DMs or in any guild counts the same, and a guild leaderboard is a membership filter over
  global records.

If per-guild rollover means each guild gets a *different answer*, then a user in two
guilds has two dailies a day and a "global streak" is meaningless. The share string
breaks too — there is no puzzle both readers played.

## Alternatives

| Option | Why not |
|---|---|
| Fixed UTC midnight | Coherent, but the reset lands mid-afternoon or mid-sleep depending on where the playerbase is — which is the reason per-guild rollover was wanted |
| Per-guild puzzle *sequences* | Honest reading of "per-guild rollover", and it destroys both global stats and cross-guild sharing. Two guilds diverge onto different answers permanently |
| Per-user timezone | Same divergence problem, one level finer, plus a setting every player must configure before their first game |
| Streaks scoped per guild | Keeps rollover local, but a user in three guilds has three streaks, and playing in DMs advances none of them |

## Decision

**Number the puzzles; do not date them.**

1. One global sequence: Chardle #1, #2, #3 … Each number is one answer chart, everywhere.
2. A guild's configured IANA timezone sets **when** puzzle #N unlocks there — local 00:00
   **plus 4 hours**. It never changes **which** puzzle #N is.
3. **Streak = the longest run of consecutive solved `puzzle_number`.** Never calendar
   days. This is what makes the whole scheme timezone-independent: the streak is defined
   over the sequence, and the sequence is global.
4. Share strings read `Chardle #412 4/6` — comparable worldwide, which per-guild dates
   would have broken.
5. `/chardle daily` **in guild G serves G's current puzzle**; in DMs it serves the newest
   puzzle unlocked across the user's guilds. Solved is solved, wherever it was solved.

### Rollover and numbering

Rollover is **local 00:00 + 4 h**, not local midnight, so someone still up at 02:00 is
playing the day they think they are. It also lands clear of DST: transitions happen at
02:00–03:00 local, so 04:00 always exists on a spring-forward day. On a fall-back day it
exists twice — take the first.

The zone is IANA, per guild, defaulting to **GMT+7** (also the default when there is no
guild context at all).

```
puzzle_number(guild, t):
    local  = t in the guild's IANA zone        # DST-aware
    day    = (local - 4h).date()
    number = (day - EPOCH_DATE).days + 1
```

- `EPOCH_DATE` is config — the reference-calendar date of Chardle #1.
- Puzzle #N unlocks in guild G at local `04:00` on `EPOCH_DATE + (N-1) days`, stored in UTC.
- A session's `expires_at` is the unlock instant of **#N+1 in that guild**, stamped at
  session creation. Stamped, not computed on read, so changing the offset later cannot move
  a live board's deadline out from under it.
- April-1-ness is read off this arithmetic in the **default** zone, never a guild's, so it
  stays a property of the number itself — see [[h-chardle-err-is-an-event]].

**The number comes from the calendar, not from a counter.** Puzzle rows are still created
lazily — nobody plays, no row — but the number a row gets is the date arithmetic above, so a
day nobody played leaves a **gap** in the sequence. A counter would close that gap and
silently corrupt the streak: play Monday, nobody plays Tuesday through Thursday, play
Friday, and two "consecutive" numbers report a 2-day streak that never happened.

Lazy creation races. Two guilds crossing the same rollover second both insert #N;
`UNIQUE (puzzle_number)` admits one, and the loser must **re-read the winner's row** rather
than surface an error.

**A DM has no guild.** Rule 5 already picks *which* puzzle it serves — the newest unlocked
across the user's guilds — and the session inherits **that guild's** zone for its
`expires_at`. A user sharing no guild with the bot falls back to the default zone.

## Consequences

- A user in a UTC+14 guild and a UTC−11 guild has a ~25 h window where #N and #N+1 are
  both live. Rule 5 resolves it deterministically: the invocation's guild decides, and
  the DM case takes the newest.
- Playing early in one guild and then seeing the same puzzle "arrive" later in another is
  expected and correct. It shows as already solved.
- `chardle_sessions.guild_id` exists for attribution and leaderboard display only. **No
  stat may be computed from it** — that would silently reintroduce per-guild streaks.
- The daily's `max_attempts` is pinned at 6 for a related reason: a guess-distribution
  histogram over a varying denominator is incoherent, and changing the number later
  orphans every prior result. One-way door.
- A daily expires at *its guild's* rollover and scores as a loss, so a streak cannot be
  held open indefinitely. Free-play boards never expire on a clock — they hold their
  channel's one live-board slot until won, lost, or ended
  ([[h-chardle-boards-are-channel-owned]]).

## Enforced at

Not yet built. Target: `chardle_puzzles.puzzle_number` (unique, nullable) and a
`StatsService` that computes streaks over contiguous `puzzle_number`, never over dates —
see [[chardle-module|chardle (module)]].
