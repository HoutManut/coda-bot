---
type: decision
status: active
date: 2026-07-27
reverses:
created: 2026-07-27
updated: 2026-07-27
tags: [decision, chardle, schema]
aliases: ["A Chardle mode is a shape of rows, not a class"]
---

# A Chardle mode is a shape of rows, not a class

> [!note] Partly superseded, 2026-07-27
> The core claim below — three tables, no mode column, a mode is a shape of rows — still
> holds and is strengthened. What changed the same day is the **count**: axis 2 turned out
> to separate only dailies from everything else, so free play and guild race were two
> names for one row shape. Four modes became three, and the daily-as-race consequence
> flipped from supported to forbidden. See [[h-chardle-boards-are-channel-owned]]. The
> original framing is preserved here because the reasoning that produced it is what made
> the collapse visible.

## Context

[[chardle|Chardle]] ships four modes at once: daily, freeplay, custom challenge, and
guild race. Four named modes reads as four game types, which invites a mode enum plus a
strategy object per mode — puzzle selection, session ownership, attempt accounting and
stats eligibility each dispatching on it.

They are not four game types. They vary on exactly two independent axes:

1. **How the puzzle row was created** — one per `puzzle_number` (daily), on demand
   (freeplay, race), or on demand with filters (custom).
2. **Who may guess into a session** — one user, or one channel.

Daily and race look maximally different and differ only in axis 2: daily is one puzzle
with N independent single-user sessions, race is one puzzle with one channel-owned
session. Nothing about the *game* differs.

Axis 2 was later found to hold **only two occupied cells, not four**: once anyone in a
channel may guess, the session must be looked up by channel, which is what free play
without an invoker lock also reduces to. That is [[h-chardle-boards-are-channel-owned]].

## Alternatives

| Option | Why not |
|---|---|
| `mode` enum + a strategy class per mode | Four classes to hold two booleans' worth of variation. Every new mode is a new class, and shared behaviour (guess resolution, feedback, expiry) has to be pulled back out into a base anyway |
| One table with nullable per-mode columns | Same rows, but nothing stops a daily row carrying custom filters, or a session owned by both a user and a channel. The invariants become service-layer etiquette instead of constraints |
| Separate tables per mode | Guess resolution and feedback are identical across all four; four copies of `chardle_guesses` guarantees they drift |

## Decision

Three tables — `chardle_puzzles`, `chardle_sessions`, `chardle_guesses` — and **no mode
column anywhere**. A mode is what a row looks like:

- `puzzle_number IS NOT NULL` ⇒ daily. Unique, so the sequence is the mode.
- `filters IS NOT NULL` ⇒ custom challenge ⇒ **stats-ineligible by construction**.
- `channel_id IS NOT NULL` ⇒ ~~race (shared co-op attempt pool)~~ **freeplay, whether or
  not anyone else is in the channel**; `discord_id IS NOT NULL` ⇒ daily. The xor
  `CHECK ((discord_id IS NULL) <> (channel_id IS NULL))` has been tightened to the
  equivalence `user-owned ⇔ daily` — [[h-chardle-boards-are-channel-owned]]. `channel_id`
  means **ownership** only; where a board's message actually sits is `board_channel_id`, a
  separate column, since a daily lives in a private thread it does not own.

Two things fall out for free rather than needing rules:

- **A daily board is identical for everyone**, because the clue column set is frozen on
  the *puzzle*, not rolled per session. The Tenniel prototype rolled columns in
  `Chardle.__init__` with `random`, which would have made a shared daily impossible. Only
  membership is frozen there — render order is a canonical constant, so two boards on the
  same puzzle agree column-for-column ([[chardle-clue-columns|Chardle — Clue Columns]]).
- **Custom challenges cannot farm stats**, because eligibility is read off `filters`
  rather than set by a flag someone must remember.

Schema detail lives in [[chardle-module|chardle (module)]] §State it owns.

## Consequences

- A further mode is a new row shape, not a new class — e.g. a weekly is
  `puzzle_number` on a second sequence.
- A shared channel board must serialise guesses with a per-session FIFO lock; a bounded
  attempt pool with concurrent writers double-counts otherwise.
- **~~"Play the daily as a race" is representable and opt-in~~ — now forbidden.** It is
  still *representable*, precisely because puzzle and session are separate rows, and that
  is exactly the problem: a channel-owned session pointing at the daily puzzle carries
  `discord_id IS NULL`, so `UNIQUE (puzzle_id, discord_id)` never binds and every
  participant could solve the daily collectively and then log a solo 1/6. Closed by the
  composite-FK equivalence in [[h-chardle-boards-are-channel-owned]]. Kept in this list
  because "representable but wrong" is the standing hazard of a schema that encodes modes
  as row shapes — the next combination has to be checked the same way.
- Anything that must differ per mode and is *not* expressible as a row shape is a signal
  this decision is being outgrown. Nothing in the current design is — though the reverse
  did happen: two row shapes turned out to be the same one.

## Enforced at

Not yet built. Target: `src/coda/chardle/` + a migration adding the three tables.
