---
type: decision
status: active
date: 2026-07-27
reverses: h-chardle-puzzle-rows-not-modes (partial — the four-mode framing and the daily-as-race allowance)
created: 2026-07-27
updated: 2026-07-27
tags: [decision, chardle, schema, ux]
aliases: ["A Chardle board is owned by where it lives; only dailies are per-user"]
---
# A Chardle board is owned by where it lives; only dailies are per-user

## Context

[[h-chardle-puzzle-rows-not-modes]] shipped four modes on two axes, one of which was
"who may guess into a session — one user, or one channel". Free play was user-owned;
**guild race** was the channel-owned cell: one board, one shared attempt pool, co-op,
unlimited attempts, no stats.

Three problems surfaced when the race cell was examined on its own (design session,
2026-07-27):

1. **"Free" and "shared pool" contradict.** The page said race attempts were free *and*
   that race shared "one attempt pool ... one budget". An unbounded pool is not a budget:
   a co-op board with unlimited attempts cannot be lost, so it has no stakes and no
   terminal state except solving.
2. **Racing the daily was a stats loophole.** `UNIQUE (puzzle_id, discord_id)` guards
   solo dailies, but a race session carries `discord_id IS NULL`, so it never binds. A
   channel could co-op today's daily, see the answer, and every participant could then
   open their own solo daily and log a 1/6.
3. **Race and free play were the same mode.** Drop free play's invoker lock and the two
   become indistinguishable: free play's session is found by `discord_id` only because
   the guesser *is* the owner, so once anyone may guess, lookup must move to the channel
   and `discord_id` demotes to attribution — which `chardle_guesses.discord_id` already
   stores. The only remaining difference was whether `max_attempts` was set.

The owner then made the decisive observation: **from a player's seat the two boards are
identical** — same art, same guess flow, same columns. The only perceptible difference is
whether their guess is accepted, discoverable solely by trying and being rejected. Two
commands that render the same and differ by a hidden permission are not two modes.

## Alternatives

| Option | Why not |
|---|---|
| Keep both, make the board self-describing (header states owner + attempts) | Fixes the *appearance* but keeps two commands, a rejection path to write, and a mode table needing explanation — for a distinction the schema does not actually make |
| Keep race, drop free play | Loses the solo board entirely; a player in a busy channel has nowhere private to practise |
| Competitive race (one puzzle, N private sessions, first solve wins) | Considered and rejected by the owner. It is the daily with a start gun, and it moves "race" from the session onto the puzzle — a second schema shape for a mode nobody asked for |
| Finite shared budget, race kept as its own mode | Chosen briefly, then subsumed: the budget survives as `max_attempts`, but it never justified a mode of its own |

## Decision

**Every non-daily board is owned by its channel. Only dailies are owned by a user.**
Solo-ness comes from *where* the board is run, not from a permission check:

- **DM the bot** → the channel holds one human → the board is private. No lock needed.
- **Guild channel** → shared board, anyone may guess.
- **Own board inside a guild** → start a thread. A thread has its own channel id, so it
  is a separate board at no cost.

`race` is deleted as a concept. What was a race is `/chardle play` run somewhere with
other people in it. What was the shared attempt pool is `max_attempts` set on the puzzle.

Modes reduce to three: **daily**, **free play**, and **free play with filters** (custom).

### Schema

```sql
-- chardle_puzzles
is_daily bool GENERATED ALWAYS AS (puzzle_number IS NOT NULL) STORED,
UNIQUE (id, is_daily),
CHECK (puzzle_number IS NULL OR filters IS NULL)   -- a daily can never be filtered

-- chardle_sessions
is_daily bool NOT NULL,
channel_id       bigint,           -- OWNERSHIP: free play only, NULL on dailies
board_channel_id bigint NOT NULL,  -- TRANSPORT: thread / DM / channel the message lives in
FOREIGN KEY (puzzle_id, is_daily) REFERENCES chardle_puzzles (id, is_daily),
CHECK ((discord_id IS NOT NULL) = is_daily
   AND (channel_id IS NOT NULL) = NOT is_daily),
CHECK (channel_id IS NULL OR channel_id = board_channel_id),
UNIQUE (channel_id) WHERE state = 'playing'
```

The composite FK is what makes the equivalence checkable. `puzzle_number` lives on the
puzzle and `channel_id` on the session, so a plain `CHECK` cannot see across the two
tables; denormalising `is_daily` onto both and joining them through the FK brings the
fact into range of a constraint. This is the same instinct that produced the original
`CHECK ((discord_id IS NULL) <> (channel_id IS NULL))` — [[h-chardle-puzzle-rows-not-modes]]
explicitly rejected letting invariants become "service-layer etiquette".

That one constraint now does three jobs: it replaces the old xor, it forbids a channel
board from pointing at a daily puzzle (closing loophole 2), and it states the
user-owned ⇔ daily equivalence outright.

`UNIQUE (channel_id) WHERE state = 'playing'` gives one live free-play board per channel,
which in a DM *is* one board per user — the solo case needs no separate rule. Daily
sessions carry `channel_id IS NULL` and never contend with it, so several people can run
the daily in one channel, each with their own board.

### A daily is private, and that needs a second channel column

A daily is owned by a user but still has to be *posted somewhere*, and never in the open
channel. In a guild the bot opens a **private thread** and adds the player
(`create_thread` with `ChannelType.GUILD_PRIVATE_THREAD` + `add_thread_member`, permissions
`CREATE_PRIVATE_THREADS` and `SEND_MESSAGES_IN_THREADS`); in a DM the DM channel serves. The
thread is **reused per (guild, player)**, not created per puzzle — per-puzzle threads would
spend ~one thread per player per day against the guild's 1000-active-thread cap and scatter
a player's history across them. No new table: the thread id is the `board_channel_id` of
that player's most recent session in that guild, recreated if it has gone.

> [!warning] The "no new table" half of this was reversed on 2026-07-27
> Reuse was inferred from the `board_channel_id` of the player's most recent session in
> the guild. **That did not work** — the owner saw three threads across three tests. The
> inference has two failure modes the page did not anticipate: it returns nothing whenever
> the session history does not line up (a dev reset is enough), and it cannot tell a thread
> under the guild's Chardle channel from one under any other channel, so a guild that later
> sets a Chardle channel would strand every existing player outside it forever.
>
> The thread id now lives in **`chardle_player_threads (guild_id, discord_id) → thread_id`**,
> and `SessionService.last_board_channel` is deleted. `_reusable_thread` additionally
> validates `parent_id` and unarchives an archived thread before reusing it. Everything else
> below stands — the reuse *rule* (one thread per (guild, player)) is unchanged; only where
> the id is read from.

A thread *is* a channel, which collides with `channel_id` — the ownership key the CHECK
reserves. The two meanings split rather than overload:

- **`channel_id`** — who owns the board. Free play only; NULL on dailies, exactly as before.
- **`board_channel_id`** — where the message lives. Thread, DM, or (for free play) the
  owning channel itself.

`CHECK (channel_id IS NULL OR channel_id = board_channel_id)` states the free-play case: a
channel-owned board must live in the channel that owns it. Dailies are unconstrained here,
which is what lets one live in a thread without contending for that channel's
`UNIQUE (channel_id) WHERE state = 'playing'` slot.

The rejected alternative was **ephemeral dailies**. An interaction token dies after 15
minutes, so an ephemeral board cannot be edited across the hours a daily lives — it would
have to be re-rendered in full on every guess and would lose the reply input path entirely.

**The parent channel stays quiet.** `verified: 2026-07-27`, grade **FACT (Discord docs; no live
capture)** — the `THREAD_CREATED` system message (type 18) "is currently only sent in one case:
when a `PUBLIC_THREAD` is created from an older message", so a private thread announces nothing
in the channel it was opened from. Visibility matches: "You must be invited to the thread to be
able to view or participate in it, or be a moderator (`MANAGE_THREADS` permission)."
([Discord — Threads](https://docs.discord.com/developers/topics/threads).)

Privacy is not delegated to the thread. That `MANAGE_THREADS` clause is exactly why: a
moderator can see and join a private thread without being invited, so a daily still verifies
that the guesser **is** `session.discord_id` before accepting a guess. Location narrows the
audience; the check enforces it.

### Attempts

`max_attempts` is **null (free) by default** on a free-play puzzle, bounded by an explicit
`/chardle play attempts:<int>`. A bounded pool is shared across everyone in the channel
and the board can be **lost** when it empties — which is the only thing that made "shared
pool" meaningful.

Defaulting on whether the channel is a DM was rejected: it reintroduces a hidden mode,
which is the exact thing this decision removes. Unlike the daily's pinned 6, this number
is **not** a one-way door — no histogram is built over free-play results, so changing it
later orphans nothing ([[h-chardle-puzzle-number-not-date]]).

### Commands

`/chardle custom` should not exist either, by the same argument: custom is free play with
filters, so it is `/chardle play level:9 side:light`. A separate command would imply a
mode the schema does not have. Surface is `daily`, `play`, `guess`, `stats`, `help`.

## Consequences

- **Two people cannot each hold a board in one busy guild channel** without using threads.
  The invoker lock used to give them that. Accepted: in a channel where a shared board is
  the point, at <50 players, nobody is expected to want it. **`/chardle play thread:` now
  makes that one option rather than a manual step** (2026-07-27) — `none` / `public` /
  `private`, where a thread board owns its own channel id and so never contends for the
  parent's live-board slot.
- **The board must still say what it is.** Attempts remaining when bounded, at minimum.
  Collapse removes the *invisible* distinction; it does not by itself make the visible
  state legible. Renderer choice is [[h-chardle-board-rendering]].
- **`filters ⇒ stats-ineligible` went redundant.** Only dailies have stats and filters can
  only sit on a non-daily, so eligibility is just `puzzle_number IS NOT NULL`. The new
  `CHECK (puzzle_number IS NULL OR filters IS NULL)` keeps the redundancy enforced rather
  than assumed.
- **The per-session FIFO lock survives.** A shared channel board with a bounded pool has
  concurrent writers whatever the mode is called — same shape as the per-destination lock
  in `scores/poster.py`.
- **An abandoned board holds its channel's slot.** A *lost* board frees it for free, since
  the unique index only covers `state = 'playing'`, but a board nobody finishes needs
  `/chardle play end` plus an inactivity sweep. Whether that reuses `expires_at` (today
  documented as dailies-only) or sweeps on `started_at` age is unsettled.
- **A bounded board can be griefed** — one player can burn the channel's pool on junk
  guesses. Social problem at this scale; no mechanism. `/chardle play end` is narrower:
  the starter, or `MANAGE_MESSAGES`.
- **Threads are a permission dependency.** A guild that denies the bot
  `CREATE_PRIVATE_THREADS` falls back to DM, then to ephemeral. Worth surfacing in setup
  docs, since the failure is silent from the player's side — the daily simply arrives
  somewhere else.
- [[h-chardle-puzzle-rows-not-modes]]'s core claim is **strengthened, not overturned**:
  three tables, no mode column, a mode is a shape of rows. Collapse simply found that one
  of its four shapes was two names for one row.

## The Chardle channel had to stop moving inline boards (2026-07-27)

Iteration 2 routed **both** legs of `/chardle play` to the guild's Chardle channel when one
was set. One live board per channel then meant **one live inline board per guild**: every
`thread: none` board in the server contended for that single channel's slot, so a board
running in the Chardle channel made `/chardle play` answer "Busy" in every other channel.
Channel ownership only works if a board stays in the channel that owns it.

Resolved by splitting the two things the channel was doing:

- an **inline** board posts where the command was typed, any channel, one live slot each;
- a **thread** hangs off the Chardle channel from any invocation channel, and is **refused**
  when no channel is set rather than opened off the invoking channel.

`transport.resolve_daily` therefore takes `parent_channel_id: int | None`, and a `None`
parent means DM — checked before the reuse branch, which would otherwise compare a thread's
parent against `None` and call `create_thread(None, ...)`. Threads never contend for a slot
either way: a thread owns its own channel id.

## Enforced at

`src/coda/extensions/chardle.py` (`Play.invoke`, `_open_daily`) and
`src/coda/chardle/transport.py` (`resolve_daily`). The slot itself is
`uq_chardle_sessions_channel_live`, unique on `chardle_sessions.channel_id` where
`state = 'playing'` — and `ck_chardle_sessions_board_in_owner` pins `channel_id` to
`board_channel_id`, so a thread board occupies the thread's slot, not the parent's. The
pre-check is advisory; the `IntegrityError` catch is the race backstop.

## Related

[[chardle|Chardle]] · [[chardle-module|chardle (module)]] ·
[[h-chardle-puzzle-rows-not-modes]] · [[h-chardle-puzzle-number-not-date]] ·
[[h-chardle-board-rendering]]
