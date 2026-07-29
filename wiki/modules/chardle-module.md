---
type: module
status: active
path: src/coda/chardle/
purpose: Wordle-over-the-catalog minigame — puzzle generation, guess resolution, feedback, sessions, stats.
depends_on: [catalog, db, settings, extensions]
used_by: []
created: 2026-07-27
updated: 2026-07-28
tags: [module, chardle]
aliases: ["chardle (module)"]
---
# chardle (module)

> [!note] Built 2026-07-27
> Shipped close to this shape. Files: `columns.py`, `facts.py`, `feedback.py`,
> `tiers.py`, `schedule.py`, `puzzle.py`, `guess.py`, `session.py`,
> `transport.py`, `board.py`, `render.py`, `stats.py`, plus
> `extensions/chardle.py`. Two splits the page did not anticipate: **transport
> moved out of `SessionService`** into `transport.py` (Discord-facing, while the
> service stays DB-only), and **board assembly** sits in `board.py` between the
> services and the renderer. The ephemeral transport leg was **not built** — the
> chain is private thread → DM → refusal. Game rules live in [[chardle|Chardle]].
>
> The reply path needs the privileged **MESSAGE_CONTENT** intent, now requested in
> `bot.py` and required in the dev portal.
>
> **Filename note:** this page is `modules/chardle-module.md`, not `modules/chardle.md`,
> because Obsidian resolves wikilinks by filename and `domains/chardle.md` already claims
> that name. Link it as `[[chardle-module|chardle (module)]]`.

## Purpose

Owns the Chardle minigame end to end: choosing an answer chart, freezing a puzzle's clue
columns, resolving a typed guess to a chart, computing per-column feedback, persisting
sessions and guesses, and deriving streaks and distributions. It is a **pure catalog
consumer** — it never contacts lowiro.

## Layer rules

`chardle/` imports `catalog/`, `db/`, `settings/`. It **must not import `arcaea/` or
`sessions/`.** Chardle needs no wire access at all: every fact it compares (level, CC,
BPM, notes, pack, side, version, artist and charter links) is catalog data. That makes the
whole minigame playable with lowiro unreachable, and it is the reason the module can be
built and tested without a session pool or a bot account.

Guess resolution goes through `catalog.search.SearchService` — chardle owns **no** fuzzy
matching of its own. The prototype's hand-rolled `fuzzy_search(...)[:2]` is exactly what
that service replaces.

`include_hidden` is passed straight through from the puzzle's tier: **`False` everywhere
except an err puzzle**. That single flag is the whole mechanism keeping err charts
unguessable in ordinary modes — chardle adds no cloaking of its own.

## State it owns

Three tables. Mode is a *shape of rows*, not a class hierarchy — see
[[h-chardle-puzzle-rows-not-modes]].

### `chardle_puzzles`

| Column               | Notes                                                                                                                                                                                                                                                                                                      |                           |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------- |
| `id`                 |                                                                                                                                                                                                                                                                                                            |                           |
| `song_difficulty_id` | FK `song_difficulties`, `ON UPDATE CASCADE ON DELETE RESTRICT` — the answer                                                                                                                                                                                                                                |                           |
| `clue_columns`       | frozen clue set. Named `clue_columns`, not `columns`, to stay clear of SQLAlchemy's `Table.columns`. Frozen here, not per-session, so a daily board is identical for everyone. **Membership only** — render order is the canonical constant sequence, capped at 7 counting `title` ([[chardle-clue-columns | Chardle — Clue Columns]]) |
| `max_attempts`       | 6 for dailies, pinned; **derived for err** (`min(max(⌊N/2⌋,1),6)`, N counted at creation with `include_hidden=True`, → 3 today); null (free) by default on free play, bounded by `/chardle play attempts:<int>` ≥ 1. Per-puzzle, never a constant                                                          |                           |
| `puzzle_number`      | int, **unique, nullable**. Non-null ⇒ this is a daily                                                                                                                                                                                                                                                      |                           |
| `is_daily`           | `GENERATED ALWAYS AS (puzzle_number IS NOT NULL) STORED`, plus `UNIQUE (id, is_daily)` — exists only so sessions can reach the fact through a composite FK                                                                                                                                                 |                           |
| `tier`               | named tier the answer was drawn from. Also the err predicate (streak counts err, the histogram does not) and the gate for tier-specific columns                                                                                                                                                            |                           |
| `filters`            | jsonb, nullable. Non-null ⇒ custom challenge ⇒ **stats-ineligible**                                                                                                                                                                                                                                        |                           |
| `created_at`         |                                                                                                                                                                                                                                                                                                            |                           |

- `CHECK (puzzle_number IS NULL OR filters IS NULL)` — a daily can never be filtered.
- **`ON DELETE RESTRICT` on the answer FK is deliberate.** A puzzle is a historical record;
  cascading a song deletion into it would silently rewrite a past daily and orphan the
  streaks derived from it. RESTRICT makes the admin editor fail loudly instead — the right
  trade at <50 players. `ON UPDATE CASCADE` matches the repo's existing catalog FKs.

The answer is **stored, never re-derived**. A `hash(date) % len(songs)` scheme would let
the admin editor silently rewrite yesterday's puzzle the moment a song is added.

### `chardle_sessions`

| Column | Notes |
|---|---|
| `id` | |
| `puzzle_id` | FK, `ON DELETE CASCADE` |
| `discord_id` | nullable — **daily owner**. Non-null on dailies only |
| `channel_id` | nullable — free-play **owner**. Non-null on everything that is not a daily |
| `board_channel_id` | NOT NULL — **transport**: the private thread, DM, or channel the board message lives in. Equals `channel_id` for free play |
| `is_daily` | denormalised from the puzzle so the ownership rule is reachable by a `CHECK` |
| `guild_id` | nullable. Attribution only; stats do not depend on it |
| `state` | `playing` / `won` / `lost` |
| `message_id` | NOT NULL — the board message. **The reply-path lookup key**, and with `board_channel_id` the edit target |
| `expires_at` | nullable; set for dailies only, to the guild's next rollover |
| `started_at`, `finished_at` | |

- `FOREIGN KEY (puzzle_id, is_daily) REFERENCES chardle_puzzles (id, is_daily)` — ties the
  session's copy of the flag to the puzzle's, so it cannot lie.
- `CHECK ((discord_id IS NOT NULL) = is_daily AND (channel_id IS NOT NULL) = NOT is_daily)`
  — **user-owned ⇔ daily**, an equivalence, not a xor. It replaces the earlier
  `CHECK ((discord_id IS NULL) <> (channel_id IS NULL))` and simultaneously forbids a
  channel board from pointing at a daily puzzle. See
  [[h-chardle-boards-are-channel-owned]].
- `CHECK (channel_id IS NULL OR channel_id = board_channel_id)` — a channel-owned board must
  live in the channel that owns it. Dailies are unconstrained here, which is what lets one
  sit in a private thread without contending for that channel's live-board slot.
- `UNIQUE (puzzle_id, discord_id)` — one attempt per user per daily.
- `UNIQUE (channel_id) WHERE state = 'playing'` — one live free-play board per channel,
  which in a DM is one per user. Daily sessions have `channel_id IS NULL` and never
  contend, so several people can run the daily in one channel.

A **lost** board releases the channel slot for free, since the partial unique only covers
`playing`. An **abandoned** one does not, and needs `/chardle play end` plus an inactivity
sweep — whether that reuses `expires_at` or sweeps on `started_at` age is unsettled.

### `chardle_guesses`

| Column | Notes |
|---|---|
| `id` | |
| `session_id` | FK, `ON DELETE CASCADE` |
| `ordinal` | |
| `song_difficulty_id` | what the guess resolved to. `ON UPDATE CASCADE ON DELETE RESTRICT` — a guess row is history too |
| `discord_id` | who guessed — a shared channel board needs per-player attribution |
| `created_at` | |

- `UNIQUE (session_id, ordinal)`
- `UNIQUE (session_id, song_difficulty_id)` — duplicate-guess rejection enforced in the
  schema, not only in service code. This constraint does double duty: it is also the
  **cursor for ambiguity cycling**, since "next candidate not already on this board" is
  read off these rows rather than from any remembered query
  ([[h-chardle-closest-match-always-costs]] §Cycling).

**Feedback is recomputed, never stored.** It is a pure function of (guess chart, answer
chart, column), so storing it duplicates catalog data that the admin editor can edit
underneath it. The accepted cost is that a mid-game catalog edit retroactively rewrites
earlier rows on an open board — rare, and preferable to a board that disagrees with the
catalog.

**Stats are derived, not materialised.** Streak and distribution are queries over
`chardle_sessions`. At this instance's scale (<50 players) a stats table would be
denormalisation with no payoff.

## Public surface

| Symbol | File | What it does |
|---|---|---|
| `PuzzleService` | `puzzle.py` | draws an answer from a tier, freezes the column set, creates the row |
| `select_columns` | `columns.py` | rolls the puzzle's column set from the pool **and the drawn answer** — variance over known values, minus anything the answer itself lacks. Takes the answer positionally; see [[d-chardle-dead-clue-columns]] |
| `board.load_shared_names` | `board.py` | lowercased titles claimed by more than one song, read off the `effective()` name so per-difficulty renames count. Catalog-wide, so the scoreboard resolves it once and passes it into every player's `build` |
| `GuessService` | `guess.py` | resolves a typed guess: exact match against the answer first (wins through the delisted cloak), then candidates filtered to the puzzle's difficulty, then answer-preference, then closest candidate not already on the board (cycling), then appends the row |
| `feedback` | `feedback.py` | per-column green/yellow/red + arrow. Pure; no I/O |
| `SessionService` | `session.py` | open/lookup/expire sessions, per-session FIFO lock, board transport (thread → DM → ephemeral) |
| `StatsService` | `stats.py` | streak, distribution, guild leaderboard, share string |
| `ChardleChannelService` | `channels.py` | the guild's Chardle channel, its sticky pointer, and each player's remembered daily thread |
| `scoreboard.build` | `scoreboard.py` | today's daily as one guild sees it; resolves the bpm/note windows **per player**, not once (they are scoped settings even though their chains are `GLOBAL`-only today), but the catalog-wide `shared_names` once |
| `sticky.refresh` | `sticky.py` | posts or edits the scoreboard message, with the stateless Play button |
| `/chardle` | `extensions/chardle.py` | `daily`, `play`, `guess`, `end`, `stats`, `channel`, `help` |

Two tables arrived with iteration 2: **`chardle_channels`** (`guild_id` PK — one channel per
guild, plus the sticky message pointer, which is bot state rather than config and so is not a
`REGISTRY` key) and **`chardle_player_threads`** (`(guild_id, discord_id)` → `thread_id`).

`SessionService` takes ownership as a parameter rather than branching on a mode:

```
open_session(puzzle, owner=user | channel, max_attempts=None | int)
```

Transport is resolved separately from ownership. A **daily** board is posted to a private
thread the bot opens and adds the player to (`create_thread` with
`ChannelType.GUILD_PRIVATE_THREAD`, then `add_thread_member`; needs `CREATE_PRIVATE_THREADS`
+ `SEND_MESSAGES_IN_THREADS`), falling back to DM. The thread is **reused per (guild,
player)**, read from `chardle_player_threads` — the original scheme inferred it from the
player's most recent session and did not work, see [[h-chardle-boards-are-channel-owned]].
Reuse re-validates the channel is still a thread, still hangs off the current parent, and
unarchives it when Discord has archived it.

The parent is **always** the guild's Chardle channel, never the invoking one:
`resolve_daily` takes `parent_channel_id: int | None`, and `None` — a guild that has set no
channel — is a DM, decided before the reuse branch, which would otherwise compare the
thread's parent against `None` and fall through to `create_thread(None, ...)`. `/chardle play
thread:` refuses outright in that state. Inline free-play boards ignore the Chardle channel
entirely and post where the command was typed.

A parent the player cannot *view* is treated as no parent: `_reachable(app, channel_id,
member)` wraps `utils.permissions.can_view`, so `start_daily` takes a `member` and hands
`resolve_daily` a `None` parent rather than opening an unreachable thread. `_no_transport`
then separates the three ways a daily can end up homeless — no channel, an invisible one, or
a thread that failed — because only the last is fixed by granting thread permissions.

`/chardle channel` asks the other half at config time via `everyone_can_view`, and
`_restricted_note` turns a definite False into an appended warning on both the set and show
replies. Warning rather than refusal is deliberate: see
[[chardle-discord-surface|Chardle — Discord Surface]] §The Chardle channel.

`transport.py` **never touches the database**: `resolve_daily` returns
`Resolved(destination, created)` and the extension writes the row, the same way `session.py`
stays DB-only. Free-play boards post where they are played, or in a thread when
`/chardle play thread:` asks for one.

There is no `race` command and no `custom` command. A shared board is `play` run in a
channel with other people in it; a custom challenge is `play` with filter options
(`/chardle play level:9 side:light`). Both would otherwise imply modes the schema does not
have — [[h-chardle-boards-are-channel-owned]].

## Two input paths, both stateless

**Slash + autocomplete** — `/chardle guess song:<autocomplete>`, autocomplete backed by
`SearchService.candidate_songs`. Smart, candidate comes from the play context but allow obviously wrong answer for strategic guesses. The session is looked up **by channel**, except for dailies, which are looked up by user. Nothing lives in memory.

**Reply-to-message** — a *global* `MessageCreateEvent` listener reads
`message.referenced_message.id` and looks it up against `chardle_sessions.message_id`.
This is deliberately **not** `wait_for`. Replace it with a table lookup is what makes games survive a restart.

The reply path needs an **ownership guard that no constraint can supply**: a message id
identifies a board, not a player. On a **daily** session, accept the guess only if the author
**is** `session.discord_id` — otherwise anyone who can see the board message (a moderator who
joined the private thread) guesses into someone else's daily. Channel-owned boards take
guesses from anyone, which is the whole point of them.

Reject silently on a finished board. A reply into a `won`/`lost`/expired session is ignored on
the reply path and answered ephemerally on the slash path — a bot that argues with every stray
reply in a busy channel is worse than one that says nothing.

**Stale sessions are closed on invocation, not only by the sweep.** `/chardle daily` first
expires any of the caller's `playing` dailies whose puzzle has already rolled over; otherwise a
missed sweep leaves yesterday's board answering today's command.

A shared channel board needs a **per-session FIFO lock** — the same shape as the
live-updates poster's per-destination lock in `scores/poster.py`. Two people guessing
simultaneously into a bounded pool must serialise, or the budget double-counts.

## Related

[[chardle|Chardle]] · [[catalog|Catalog]] · [[db|db (module)]] ·
[[h-chardle-puzzle-rows-not-modes]] · [[h-chardle-boards-are-channel-owned]] ·
[[h-chardle-closest-match-always-costs]] ·
[[h-chardle-puzzle-number-not-date]] · [[h-chardle-extra-pool-hides-class]] ·
[[h-chardle-err-is-an-event]] · [[d-chardle-dead-clue-columns]] ·
[[h-chardle-board-rendering]] · [[h-chardle-build-time-leftovers]]
