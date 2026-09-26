---
type: source
status: active
path: "(none — authored directly in this session, not ingested from an archived doc)"
lines: 0
dated: "2026-09-02"
verified: 2026-09-02
supersedes: []
superseded_by: []
created: 2026-09-02
updated: 2026-09-02
tags: [source, handoffs, tournaments, quick-match, ui, built]
aliases: ["13 — quick match", "13 — tournaments"]
---

# 13 — Quick Match

## Covers

Implementation spec for **the match and everything under it** — the whole
tournament module except the formats layer, which is
[[handoff-14-tournament-formats|handoff 14]]. Build this first: a quick match
exercises every object, table, query and surface below, and handoff 14 adds a
layer on top without changing any of them.

**Locked decisions only** — every rule below is settled and may be built against
directly. Open questions,
rejected alternatives, and unbuilt formats are deliberately absent; they live in
[[tournaments|Tournaments]] and `questions/`. The one exception is
§[[#Derived, needs a nod|Derived, needs a nod]], which is mechanically forced by a
locked decision but has never been said out loud by the owner.

Depends on nothing unbuilt: the poll loop ([[score-poll-loop|Score Poll Loop]])
and `play_scores` ([[db]]) are shipped, and both are the module's only inputs.

> [!important] Split, 2026-09-02
> This handoff grew past the point where one document served it. It now covers
> the **match** and below: rounds, windows, validity, ranking, the pool,
> pick/ban, threads, the board, and waiting. The **tournament** layer —
> registration, formats (single/double elimination, round robin, lobby),
> seeding, async scheduling and no-shows — is
> [[handoff-14-tournament-formats|handoff 14]]. The split is at a real seam:
> every format decomposes into matches, so nothing in 14 changes anything here.

> [!important] Built 2026-09-02 — six deltas
> This handoff shipped as `src/coda/tournaments/`. Six things differ from the
> text below, and the text below is **not** updated in place — read it as the
> design, and [[tournaments-module]] as what exists.
>
> Owner rulings, 2026-09-02:
> 1. **Four `/config` keys, not two** (decision 38): `level`, `bans`,
>    `best_of`, `visibility`.
> 2. **`tournament_default_level` is a RANGE, and unset means ANY** — the
>    refusal in §"The two `/config` keys" is gone. "Any level" is a choice an
>    organizer may make, and the board prints it like every other filter.
> 3. **`tournament_default_class` deleted; `class:` is a REQUIRED option**
>    whose `any` value means a casual, song-mode match. A pool entry is then a
>    song, so `tournament_pool_charts` shipped as `tournament_pool_entries`
>    with a `song_id` and a nullable `song_difficulty_id`. The level band still
>    bounds the resolved set.
> 4. **The owned-by-all filter is always on and has no option** (decision 26):
>    you cannot play a chart you do not own. Still a no-op stub.
>
> Measured against the shipped code:
> 5. **Hot cadence is 15 s, not 5 s.** `PollSchedule` has one scalar interval,
>    `STAGGER` idles 3–12 s between keys, and the refresh budget is 2 per
>    `poll_interval` per key. See [[tournaments-module]] §The hot lane.
> 6. **No board debounce** (§The board message). The 5 s sweep already bounds
>    edit rate and cannot drop the final frame. The per-match lock survives.
>
> Two smaller corrections are noted inline: decision 8's sentinel, and decision
> 22's write timing.

> [!note] Second pass, 2026-09-02 — the surface
> The first pass settled scoring, windows and validity. This pass settled the
> **surface**: where a room lives (a thread, always), what a board looks like (a
> rendered image, not an embed table), and what that board is *of* — **match
> state**, meaning a chart pool with pick/ban marks and per-chart winners, not a
> leaderboard. That last point added an object the first pass did not have. See
> §[[#Object model|Object model]].

## Object model

The first pass had one object, the round. The board being a *match* board forces
three:

```
tournament          registration + a format that decides which matches exist
  └── match         a pool → pick/ban → best-of-N              A THREAD HOLDS THIS
        └── round   one chart set + one window                 THE FIRST PASS'S OBJECT
```

- A **round** is unchanged and still the only thing that touches `play_scores`:
  an eligible chart set plus a window, decisions 1–10.
- A **match** is what a thread contains and what the board renders. It owns the
  roster, the pool, the pick/ban sequence and the best-of count. It spawns
  rounds; it never reads a score itself.
- A **tournament** is a registration roster plus a **format**, and a format
  decides exactly two things: *which matches exist*, and *what a finished match
  does next*. Fully specified in [[handoff-14-tournament-formats|handoff 14]];
  this document treats it as the thing that may set `matches.tournament_id`.

**The match is the invariant unit — every format decomposes into matches.** A
large lobby is one match with everyone in it. Round robin is one match per pair.
A bracket is one match per node. This is why adding four formats does not
perturb the match or round layers at all: **nothing below the tournament knows
which format produced it**, which is exactly what makes this document
buildable on its own.

**A quick match is a match with no tournament.** That is the whole difference —
not a second code path, and not a flag that changes any rule. It is the same
object with `tournament_id IS NULL`, which is what makes decision 20's split
(reuse the thread / never reuse it) the *only* behavioural consequence of the
distinction.

## Locked decisions

### Scoring and windows (first pass)

1. **A round is an eligible chart set + a time window.** Not one chart.
2. **The module never calls the lowiro API.** It reads `play_scores` and
   declares hot windows. No HTTP, no `sid`, no `bot_account_id` anywhere in it
   ([[w-sid-confined-to-sessions]]).
3. **Validity** is set membership plus the window, and nothing else:
   `score.song_difficulty_id in round.chart_set and round.start <= score.time_played <= round.end`.
4. **Membership is on the resolved `song_difficulty_id`**, never `song_id`.
   Ingest resolves `(song_id, difficulty)` before this layer sees a row, which is
   what makes `byd_2` free ([[score-mapping|Score Mapping]]).
5. **Ranking is raw `score`. Ties break on earlier `time_played`.** No play
   rating, no CC, no clear bonus, on any tier ([[h-score-is-the-only-ranking-value]]).
6. **Every score inside the window counts** — any gauge, any clear type, any
   magnitude. The validity predicate never reads `clear_type`, `modifier`,
   `health`, or score magnitude ([[h-every-valid-score-counts]]).
7. **`scoring_rule` is a per-round parameter**: `first` (default) | `best`.
   `last` is not offered. A match authors the same rule onto every round it
   spawns; the column stays on the round, so this decision is untouched.
8. **Window duration** `clamp(2t, 200, 500)` seconds, `t` = **max** `time`
   across the chart set; `t = 0` resolves to **500** (the ceiling), never the
   floor. No catalog value clamps at either end today, so both bounds are
   guards and every real chart resolves to a plain `2t`.
   **Corrected at build time:** *one* unknown in the set takes the ceiling,
   rather than being outvoted by a known neighbour. `max({150, 0})` is 150, but
   a known 150 s chart says nothing about how long the unknown one runs, and
   whoever picks it would get a window shorter than their song. Song mode makes
   multi-chart sets the norm, so this stopped being a corner case.
9. **Two windows.** Validity `[start, end]` on `time_played`, never moves.
   Observation `[start, end + grace]` on wall clock.
10. **Roster freezes when the match leaves `draft`.** `deadline reached` is the
    only universal exit from a round.
11. **Roster entries are `arcaea_account_id`**, never `discord_id`. A duplicate
    `arcaea_account_id` is rejected at signup.
12. **The chart pool is an explicit organizer choice**, never derived from
    player ratings or catalog inference. Decision 26 refines *how* it is chosen
    without weakening this: a filter the organizer supplies is still the
    organizer choosing.
13. **A match is created as a room.** A server-wide event is the same object,
    guild-scoped and admin-gated — not a second system.
14. **A room is not tied to a bot account.** Participants may span any number.
15. **Cadence is a union across all open rounds**, never per-round.
16. **A round is tier-agnostic.** Every field rules 3/5/6 need is on the friend
    path.

### Surface (second pass, 2026-09-02)

17. **Every match lives in a thread, off one dedicated channel.** A guild sets a
    tournament home channel; every thread hangs off it. No match runs in a plain
    channel. A guild with no channel set is **refused**, never fallen back to
    the invoking channel — the exact failure
    [[h-chardle-boards-are-channel-owned]] §"The Chardle channel had to stop
    moving inline boards" had to fix after shipping it the other way.
18. **There is no DM leg. The module is guild-only.** `guild_id` is `NOT NULL`,
    reversing the first pass's `NULL = DM/private room`. Bots cannot open a
    thread in a DM and cannot create a group DM, so a DM room could hold neither
    the board nor a second player. Privacy comes from a *private thread*
    instead, which is strictly better here: **participants can talk to each
    other in it.** Everything about a match — lobby, pick/ban, boards, results,
    trash talk — happens in the one thread.
19. **Thread visibility is the privacy model, and nothing else gates reading.**
    `public` = any guild member may read; `private` = the bot adds each
    participant. There is no separate viewer permission and no ephemeral leg.
20. **A quick match reuses its crew's thread; a tournament match never reuses.**
    - **Quick match** — keyed on the exact roster. Hit → reuse. Miss → new
      thread. The thread accumulates one board per match and *is* that crew's
      head-to-head history.
    - **Tournament match** — always a fresh thread, named for its stage and
      pairing. A bracket match is a one-off by construction; folding it into a
      crew thread would bury it under unrelated quick matches.
21. **The reuse key is `(guild_id, sorted roster, visibility)`, exact.** One
    extra player, one fewer, or public-vs-private is a *different* thread. Order
    never matters: the key is sorted and deduped at write, so array equality is
    set equality.
22. **The key lives in a table, never inferred from the newest match.** That
    inference is precisely what failed for chardle dailies
    ([[h-chardle-boards-are-channel-owned]], warning callout): it returns nothing
    after any history gap, and it cannot tell a thread under the home channel
    from one under any other, so a guild that moves its channel strands every
    player outside it forever.
23. **Reuse revalidates three things before trusting a remembered thread** —
    it is a `GuildThreadChannel`, its `parent_id` is the *currently configured*
    home channel, and it is unarchived (unarchive if not). Any failure forgets
    the row and creates fresh. Same three checks as `chardle/transport.py:_reusable_thread`.
24. **The board is a rendered image**, one message per match, edited in place.
    Text is the fallback path only — missing **Attach Files**, or a render
    failure. It is not a second design.
25. **The board renders match state, not standings**: the chart pool, each entry
    carrying its pick/ban mark and, once played, its winner. A leaderboard is
    what the multi-player shape degenerates to, not what the board *is*.
26. **A pool is generated from organizer filters**, not typed chart by chart and
    not saved as named pools. Filters: **level**, **difficulty class**, and
    **owned by every participant** — the last one a no-op today and gated on the
    ownership blob ([[h-ownership-blob-open-before-building]],
    [[handoff-11-ownership-blob]]). Generation excludes spoilered charts
    (decision 30).
27. **Pick/ban is head-to-head only.** Two participants → alternating pick/ban.
    Three or more → **no pick/ban at all**; the generated pool *is* the round's
    chart set, one round, which is the casual song-mode shape the first pass
    already described. Snake order over 5 players was rejected: whoever bans
    last shapes the pool alone.
28. **A match is best-of-N over picked charts.** Picks become rounds in pick
    order; the single chart left unbanned and unpicked is the **decider** and
    plays last. Match won on rounds won.
29. **A pick/ban turn that expires auto-acts, at random from what remains.** The
    per-turn timer is the same "never wait on a human" rule as decision 10's
    deadline, applied one level up: a match always reaches its first window.
    Deterministic auto-act (first remaining in pool order) was rejected as
    guessable and therefore exploitable against an ordered pool. The board marks
    an auto action distinctly — an auto-ban reads differently from a chosen one.
30. **Pool generation excludes spoilered charts.** A pool names charts in a
    thread other people can read, so a spoilered chart in one is an *active*
    spoil, not an answer to a question. Chardle's answer picker is the only
    active-spoil path in the bot today and is already noted as the open leak in
    [[h-spoiler-is-a-render-mode]]; do not add a second. A round that lands on a
    spoilered chart some other way still renders blurred, per that decision.
31. **Live score visibility during `open` is out of scope for this pass.** v1
    draws a score on the board as soon as ingest observes it. Revisit when
    `best` mode is designed: a visible leader score turns a `best` window into
    target-chasing, which is a rules decision and not a rendering one. Under
    `first` it is inert — a rival's number cannot change a play that is already
    locked in.

### Waiting (second pass, 2026-09-02)

32. **Every wait ends early when the thing it waits for has happened. The
    timeout is only the backstop for a human who does not act.** This is
    decision 10's early `open -> grace` exit ("all participants scored, so stop
    waiting") generalised to every wait in the system:

    | Wait | Ends early on | Backstop |
    |---|---|---|
    | Pick/ban turn | the player acting | auto-act at random (decision 29) |
    | Round `open` | all scored, under `first` | `end_ms` |
    | Intermission between rounds | everyone Ready | the fixed intermission |
    | Match start (async formats) | everyone Ready — the **instant start** button | the play-by deadline, then forfeit (decision 35) |

33. **`Ready` is one primitive, not four.** A single per-participant flag on the
    board, cleared whenever a new wait begins, serves the intermission skip and
    the instant start alike. Anything that would otherwise be a "wait N seconds
    for people who are already here" gets the same button rather than its own.
34. **Timer lengths are constants in code, not configuration.** Turn,
    intermission and grace are module constants beside `DEAD_END_TTL` in
    `utils/render.py` and `LIVE_WIDTH` in `chardle/imaging/encode.py`. Decision
    32 is what makes this safe: nobody needs to tune a wait that ends the moment
    it is satisfied. **This reverses the first draft of this pass**, which put
    `tournament_turn_seconds` and `tournament_intermission_seconds` in the
    registry — tunable timeouts are what you build when you cannot end the wait
    early, and they are a worse answer to the same problem.
35. **"Never wait on a human" is scoped to *inside* a match.** Once a match
    starts, nothing waits on a person. **Whether an async match starts at all
    does** — that is what an async format is — so each such match carries a
    play-by deadline. One side Ready at the deadline and the other never →
    forfeit, the ready side advances. Neither side Ready → the match stalls and
    is flagged for the organizer, never auto-voided; emptying a branch of a
    bracket silently is worse than a stall someone can see.
    **A quick match is never async** — both players are in the thread already —
    so the `scheduled` state and `play_by_ms` exist here but are only reached by
    [[handoff-14-tournament-formats|handoff 14]]'s formats.

### Configurability (second pass, 2026-09-02)

36. **The configurable axis is the format, not the timings.** What a server
    wants to vary is *what kind of event this is* — bracket, double-elimination
    bracket, round robin, lobby, and whether banning happens at all — not how
    many seconds a countdown runs.
37. **Configuration lives where the choice is already being deliberate.** A
    quick match must be one option long (`with:`), so its format is fixed and
    its two gaps are filled by guild defaults. Creating a *tournament* is
    already a deliberate act with a form in front of it, so it carries its full
    format spec there and needs no guild defaults at all. This replaces the
    three-tier scheme drafted earlier: the tier is not a property of the value,
    it is a property of how much attention the user is already paying.
38. **Only two `/config` keys exist**, and both exist solely to keep
    `/tournament quick with:@bob` one option long. Everything else is an option
    on a surface where the user is already choosing things.
39. **No tournament setting is writable at `USER` scope.** A match is shared
    state: a per-user default scoring rule means two players in one match
    believe different rules apply, and the board can only draw one of them. The
    existing scope chain is *narrowed* here, not reused as-is.
40. **Anything that changes how you play is printed on the board**, and the
    converse holds — anything not on the board must not change how you play.
    With formats this matters more than it did with timers: the board states the
    format, the stage, and what a point means.
41. **A derived value is never independently configurable.** Pool size is a
    function of `best_of` (§Derived), so it gets no option: offering both would
    let someone configure a Bo5 with a three-chart pool. Same for bracket size,
    which is a function of the entrant count.
42. **There is no roster cap.** An earlier draft invented one; it was wrong the
    moment a lobby became a format. The board **truncates its rows**, the roster
    is not truncated, and the only real population bound is the friend-slot
    ladder ([[auth-and-sessions|Auth & Sessions]] §Friend-slot cap).

## Schema

Seven tables. No `relationship()` — explicit joins only ([[h-no-orm-relationships]]).
Register each in `db/models/__init__.py`; enums go in `db/enums.py` as native
Postgres enum types beside `clear_type_type`.

### `tournament_channels`

The guild's home channel. Mirrors `chardle_channels` exactly, including the
lesson that a moved channel must invalidate remembered threads rather than
strand them.

| Column | Type | Notes |
|---|---|---|
| `guild_id` | `BigInteger` PK | |
| `channel_id` | `BigInteger` not null | every thread hangs off this |
| `set_by` | `BigInteger` not null | attribution |
| `created_at` | `DateTime(tz)` | `server_default=func.now()` |

### `tournament_matches`

What a thread holds and the board renders.

| Column | Type | Notes |
|---|---|---|
| `id` | `Integer` PK | |
| `guild_id` | `BigInteger` **not null** | decision 18 |
| `home_channel_id` | `BigInteger` not null | the parent at creation; what reuse revalidates against |
| `thread_id` | `BigInteger` not null | where the match lives |
| `board_message_id` | `BigInteger` nullable | the one message edited in place |
| `visibility` | `thread_visibility` enum | `public` \| `private` |
| `tournament_id` | FK nullable | `NULL` = quick match. **The only difference between the two kinds** |
| `stage_label` | `String(32)` nullable | `QF1`, `Grand Final`. Tournament matches only |
| `pick_ban` | `Boolean` not null | decision 36 — banning is switchable off |
| `best_of` | `SmallInteger` not null | 1, 3, 5 |
| `state` | `match_state` enum | `scheduled` \| `draft` \| `pickban` \| `playing` \| `closed` \| `cancelled` |
| `play_by_ms` | `BigInteger` nullable | async deadline (decision 35). `NULL` on a quick match |
| `turn_index` | `SmallInteger` not null | position in the pick/ban sequence; `side_index = turn_index % 2` |
| `turn_deadline_ms` | `BigInteger` nullable | when the current turn auto-acts (decision 29) |
| `creator_discord_id` | `BigInteger` not null | attribution; not the roster |
| `admin_gated` | `Boolean` not null | `True` = server-wide event; transitions need the guild permission |
| `created_at` | `DateTime(tz)` | |

Index `(state, turn_deadline_ms)` — the auto-act sweep reads it, mirroring the
round table's `(state, end_ms)` deadline sweep.

### `tournament_threads`

Decision 22's table. Quick matches only — a tournament match writes no row.

| Column | Type | Notes |
|---|---|---|
| `guild_id` | `BigInteger` | |
| `roster_key` | `Integer[]` not null | sorted, deduped `arcaea_account_id`s |
| `visibility` | `thread_visibility` enum | part of the key (decision 21) |
| `thread_id` | `BigInteger` not null | |
| `updated_at` | `DateTime(tz)` | |

`UNIQUE (guild_id, roster_key, visibility)`. Postgres gives arrays a default
btree opclass, so this indexes and compares without a hash.

**An array, not a digest.** The key stays readable in `psql` and joins straight
back to `arcaea_accounts` when a thread has to be explained to someone. A
sha256 would be one byte-width smaller and completely opaque.

Written on **create only**. A reuse never rewrites `thread_id`; a failed
revalidation (decision 23) deletes the row and the create path writes a new one.

**Corrected at build time:** written at **roster freeze**, not at create. That
assumed a fixed roster, but `/tournament join` changes one while the match
drafts and the reuse key *is* the roster — so create *reads* the table to
decide reuse, and start *upserts* the final crew onto the thread. A thread
otherwise stays keyed to the crew that opened the room rather than the one that
played in it.

### `tournament_pool_charts`

The match's pool and its pick/ban state. Head-to-head matches only — decision 27
means a 3+ player match has no pool, just a chart set.

| Column | Type | Notes |
|---|---|---|
| `match_id` | FK -> `tournament_matches.id` `ondelete="CASCADE"` | |
| `song_difficulty_id` | FK -> `song_difficulties.id` `ondelete="RESTRICT"` | |
| `ordinal` | `SmallInteger` not null | stable display order on the board |
| `state` | `pool_entry_state` enum | `available` \| `banned` \| `picked` |
| `acted_by` | FK -> `arcaea_accounts.id` nullable | who banned or picked it |
| `acted_at` | `DateTime(tz)` nullable | |
| `auto` | `Boolean` not null default false | decision 29 — the board marks these |
| `round_id` | FK -> `tournament_rounds.id` nullable | set when a pick spawns its round |

`UNIQUE (match_id, song_difficulty_id)`, `UNIQUE (match_id, ordinal)`.

The decider is derivable, not stored: at the end of the sequence exactly one row
is still `available`, and it becomes the last round.

### `tournament_rounds`

Unchanged in meaning; reparented under the match, which now owns everything
Discord-facing.

| Column | Type | Notes |
|---|---|---|
| `id` | `Integer` PK | |
| `match_id` | FK -> `tournament_matches.id` `ondelete="CASCADE"` | |
| `ordinal` | `SmallInteger` not null | 1..N, pick order, decider last |
| `state` | `round_state` enum | `pending` \| `open` \| `grace` \| `closed` \| `cancelled` |
| `scoring_rule` | `scoring_rule` enum | `first` \| `best`, default `first` (decision 7) |
| `start_ms` | `BigInteger` nullable | validity window open, UTC ms. Set on `pending -> open` |
| `end_ms` | `BigInteger` nullable | `start_ms + duration`, computed at the same moment |
| `grace_ms` | `Integer` not null | observation slack past `end_ms` |
| `created_at` | `DateTime(tz)` | |

`UNIQUE (match_id, ordinal)`. Index `(state, end_ms)` — the cadence query and
the deadline sweep both read it.

`start_ms`/`end_ms` are `BigInteger` UTC ms to compare directly against
`play_scores.time_played` with no conversion at query time.

**`guild_id`, `channel_id`, `creator_discord_id`, `admin_gated` and `open_join`
moved to the match.** A round is now purely the scored object; nothing on it
knows what Discord is.

### `tournament_charts`

One round's eligible chart set. Unchanged.

| Column | Type | Notes |
|---|---|---|
| `round_id` | FK -> `tournament_rounds.id` `ondelete="CASCADE"` | |
| `song_difficulty_id` | FK -> `song_difficulties.id` `ondelete="RESTRICT"` | RESTRICT: a round's set must not silently lose a chart |

`UNIQUE (round_id, song_difficulty_id)`. A head-to-head round has exactly one
row, copied from the pool entry that was picked. A casual song-mode round has
one per difficulty of the song.

### `tournament_participants`

Roster, now at match level.

| Column | Type | Notes |
|---|---|---|
| `match_id` | FK -> `tournament_matches.id` `ondelete="CASCADE"` | |
| `arcaea_account_id` | FK -> `arcaea_accounts.id` `ondelete="RESTRICT"` | RESTRICT matches `play_scores` — a roster is history |
| `side_index` | `SmallInteger` not null | 0/1 for head-to-head; turn order and board side |
| `ready_at` | `DateTime(tz)` nullable | decision 33's one primitive. Cleared whenever a new wait begins |

`UNIQUE (match_id, arcaea_account_id)` — this constraint *is* decision 11.

`ready_at` has exactly one meaning — *this participant has said go for the
current wait* — which is what lets one column and one button serve both the
intermission skip and the instant start.

## Module layout

`src/coda/tournaments/`, mirroring `scores/`. Never imports `hikari` or
`coda.sessions` — except `render.py` and `imaging/`, which are Discord- and
Pillow-facing by nature and sit at the edge, the same split
`chardle/` already draws between its services and `transport.py`/`render.py`.

| File | Holds |
|---|---|
| `window.py` | `duration_for(times: Sequence[int]) -> int` — decision 8, pure, no I/O |
| `pool.py` | pool generation from filters — decision 26 |
| `pickban.py` | the sequence, whose turn it is, auto-act — decisions 27–29 |
| `match.py` | match CRUD, join/leave, state transitions, round spawning |
| `service.py` | round state transitions |
| `results.py` | the standings query — decisions 3/5/6 |
| `cadence.py` | the hot-account query — decision 15 |
| `views.py` | `MatchView` and friends — pure dataclasses, no I/O, no hikari |
| `render.py` | `MatchView -> Rendered`. Picks image or text |
| `imaging/` | Pillow compose. **Owner-designed** — see §The match board |
| `transport.py` | thread resolve/reuse/create. REST-only, no DB |
| `board.py` | posting and editing the one board message; the debounce and the lock |

`extensions/tournament.py` is the only lightbulb-aware file.

**`views.py` is the seam that matters.** Everything above it produces a pure
`MatchView`; everything below it draws. That is what lets the image be
redesigned without touching a query, and what lets the text fallback exist
without a second data path — the same seam `chardle.scoreboard.build` /
`chardle.render.scoreboard` already uses.

## The two queries

### Standings (`results.py`)

```sql
SELECT DISTINCT ON (ps.arcaea_account_id)
       ps.arcaea_account_id, ps.score, ps.time_played, ps.song_difficulty_id
FROM tournament_rounds r
JOIN tournament_participants tp ON tp.match_id = r.match_id
JOIN tournament_charts tc       ON tc.round_id = r.id
JOIN play_scores ps
  ON ps.arcaea_account_id = tp.arcaea_account_id
 AND ps.song_difficulty_id = tc.song_difficulty_id
 AND ps.time_played BETWEEN r.start_ms AND r.end_ms
WHERE r.id = :rid
ORDER BY ps.arcaea_account_id,
         -- scoring_rule = 'first': ps.time_played ASC
         -- scoring_rule = 'best' : ps.score DESC, ps.time_played ASC
```

Then rank the picked rows by `score DESC, time_played ASC`.

The query reads five columns and joins no CC. That is decisions 5 and 6 made
structural: there is no column in scope to filter or weight a play by.

A participant with no matching row resolves to "no score" — a `LEFT JOIN` from
`tournament_participants`, never an omission. The board draws that row.

### Cadence (`cadence.py`)

```sql
SELECT DISTINCT aa.bot_account_id
FROM tournament_rounds r
JOIN tournament_participants tp ON tp.match_id = r.match_id
JOIN arcaea_accounts aa         ON aa.id = tp.arcaea_account_id
WHERE r.state IN ('open', 'grace')
  AND aa.bot_account_id IS NOT NULL
```

One query across all rounds, unioned — never per-round. The poller consumes the
set; the tournament module does not know what it means.

## State machines

### Match

```
DRAFT ──┬── 2 players ──> PICKBAN ──> PLAYING ──> CLOSED
        └── 3+ players ─────────────> PLAYING ──> CLOSED
  │                 │                    │
  └── cancel ───────┴────────────────────┴──────> CANCELLED
```

| From | To | Trigger | Effect |
|---|---|---|---|
| `scheduled` | `draft` | every participant is `Ready` — the **instant start** button | Async formats only; a quick match is created in `draft` |
| `scheduled` | `closed` | `play_by_ms` passes with one side Ready | Forfeit; the ready side takes the match ([[handoff-14-tournament-formats\|handoff 14]]) |
| `draft` | `pickban` | organizer starts, roster is 2, `pick_ban` on | Freeze roster. Generate pool. Randomise first actor, set `turn_deadline_ms` |
| `draft` | `playing` | organizer starts, roster is 2, `pick_ban` **off** | Freeze roster. The generated pool is consumed in order as the rounds |
| `draft` | `playing` | organizer starts, roster is 3+ | Freeze roster. Pool becomes one round's chart set (decision 27). Open round 1 |
| `pickban` | `pickban` | a pick/ban lands, or `turn_deadline_ms` passes | Advance `turn_index`, reset the deadline. A pick spawns its round as `pending` |
| `pickban` | `playing` | sequence exhausted | The one `available` row becomes the decider round. Open round 1 |
| `playing` | `playing` | a round reaches `closed` | Open the next `pending` round when everyone is `Ready`, or when the intermission expires (decision 32) |
| `playing` | `closed` | a side reaches `ceil(best_of / 2)` wins, or no `pending` round is left | Remaining rounds render `unplayed`. Final board, full resolution |
| any | `cancelled` | organizer, or admin when `admin_gated` | Cadence query stops matching. Thread stays for the record |

### Round

Unchanged from the first pass, with `draft` renamed `pending` — a round is now
created by the match rather than authored by a human, so there is nothing to
draft.

| From | To | Trigger | Effect |
|---|---|---|---|
| `pending` | `open` | the match advances to it | `start_ms = now()`, `end_ms = start_ms + duration_for(...)`. Accounts go hot |
| `open` | `grace` | `now() >= end_ms`, **or** every participant has a valid score and `scoring_rule = 'first'` | Stop accepting new `time_played`; keep polling |
| `grace` | `closed` | `now() >= end_ms + grace_ms` | Result final and immutable. Accounts leave the hot set unless another round is open |

The early `open -> grace` exit applies only under `first`, where a further play
cannot change any result. Under `best` the round always runs to `end_ms`.

**Every transition is recomputable from the DB on restart** — round state plus
`start_ms`/`end_ms`, match state plus `turn_deadline_ms`. Nothing lives in
memory, which is also why every board button has to be stateless (see below).

## Discord surface

### The home channel

One command group, `/tournament`. Every thread hangs off the guild's home
channel; no channel set is a refusal naming the permission, in the shape of
`chardle/transport.py`'s `NO_THREAD` string, never a fallback.

| Command | Does |
|---|---|
| `quick` | Start a quick match. `with:`, `visibility:`, `bo:`, `level:`, `class:`, `rule:` |
| `join` / `leave` | While `draft` |
| `start` / `cancel` | Organizer, or admin when `admin_gated` |
| `board` | Re-post the board in the thread when the message is lost |
| `channel` | Admin: set or clear the guild's home channel |

Tournament creation and registration are a separate surface, not designed here.

### Threads

- **Public** — created *from an anchor message* in the home channel, so the
  channel shows the thread and anyone can find it. This is the only discovery
  mechanism v1 has and it is free.
- **Private** — created bare, `invitable=False`, participants added with
  `add_thread_member`. It **announces nothing** in the home channel: Discord
  only emits `THREAD_CREATED` for a public thread off an older message
  (verified, [[h-chardle-boards-are-channel-owned]]).
- **Privacy is not delegated to the thread.** `MANAGE_THREADS` lets a moderator
  read a private thread uninvited, so every pick/ban interaction still verifies
  the clicker is the participant whose turn it is. Location narrows the
  audience; the check enforces it. Same rule chardle applies to a daily board.
- **Naming** — `alice vs bob`, `alice +3` for a crew of five, and
  `QF1 — alice vs bob` for a tournament match. 100 chars, truncate the tail. A
  reused crew thread is **never renamed**: the name is the crew, and the crew is
  the key.
- **Archive** — `auto_archive_duration` 1440 for a quick-match crew thread
  (reused threads are unarchived on demand anyway) and 10080 for a tournament
  match, so a bracket in progress stays visible.

### The board message

**One message per match, edited in place, never reposted.** `board_message_id`
on the match. A lost message is recovered by `/tournament board`, not by an
automatic repost — a repost loop would fight the conversation the thread exists
to host (decision 18).

Two things write it, and both write the same message:

1. **Pick/ban clicks** — one edit per turn.
2. **Ingest** — a round is polled hot at 5s across N participants, so an
   undebounced board could edit several times a second.

So: **one `asyncio.Lock` per match, and a debounce that coalesces ingest edits to
at most one per ~5s, always rendering the latest state.** The lock is the FIFO
shape already used per destination in `scores/poster.py:342` — `asyncio.Lock`
releases waiters in order, so ordering is free.

**A final render is forced, undebounced, on every round close and on match
close.** A debounce that can drop the last frame is a bug, not an optimisation.

### Buttons

Pick/ban is a **string select** of the remaining charts under the board, not a
button row: a pool runs to 7 and a select holds 25, while five buttons do not.

**Custom ids are stateless** — `tourney:act:<match_id>` — and carry no round or
turn number. A match outlives any lightbulb `Menu` timeout and outlives
restarts, exactly as `chardle/sticky.py:PLAY_BUTTON_ID` does; the turn is read
from the DB on every interaction, never from the id.

Everything ships as a Components V2 container via `utils/render.py` and
`utils/container.py`, unchanged: the board image goes on the embed with
`set_image`, which `as_container` turns into a media gallery item, and the
select row rides inside the same container. **No new plumbing** — and a
spoilered chart blurs the whole container for free.

### Permissions

`CREATE_PUBLIC_THREADS`, `CREATE_PRIVATE_THREADS`, `SEND_MESSAGES_IN_THREADS`,
`ATTACH_FILES`, `MANAGE_THREADS` (to unarchive on reuse).

Missing `ATTACH_FILES` degrades to the text board — the one case decision 24's
fallback exists for. Missing a thread permission refuses and names it. Both
failures are silent from a player's side otherwise, so both belong in the
self-hosting docs.

## Configuration

### What is actually configurable

The axis is the **format**, not the timings (decision 36). Timer lengths are
constants precisely because decision 32 ends every wait the moment it is
satisfied — a tunable timeout is what you build when you *cannot* do that, and
it is a worse answer to the same problem.

| Choice | Where it is made | Why there |
|---|---|---|
| Format — bracket, double-elim, round robin, lobby | `/tournament create`, a deliberate form | [[handoff-14-tournament-formats\|handoff 14]] |
| `pick_ban` on/off | tournament form, or `/tournament quick` | changes the match shape; must be visible |
| `best_of` | tournament form, or `/tournament quick` | the board prints it |
| Pool filters — level, class | tournament form, or `/tournament quick` | the board prints them |
| Home channel | `/tournament channel`, a table | carries `set_by`; a config value would not |
| Turn / intermission / grace lengths | **nowhere — constants** | decision 34 |
| Roster cap | **nowhere — does not exist** | decision 42 |

### The two `/config` keys

Both exist for one reason: to keep `/tournament quick with:@bob` one option long
(decision 38). Both are `GUILD → GLOBAL`, neither is `USER`-writable
(decision 39).

| Key | Type | Default | Audience |
|---|---|---|---|
| `tournament_default_level` | `str` | `""` | user |
| `tournament_default_class` | `("pst","prs","ftr","byd","etr")` | `ftr` | user |

**A pool with no level filter is refused.** An unfiltered draw across 552 songs
spans PST 1 to BYD 12 and makes a garbage match, so `/tournament quick` refuses
when neither `level:` nor `tournament_default_level` is set, and names the fix.
That keeps decision 12 intact — the band is still an explicit organizer or admin
choice, never derived from player ratings — while decision 38 survives a
one-time guild setup: once an admin sets the band, `with:` really is the only
option anyone types.

### Per-match options

| Option | Unset resolves to |
|---|---|
| `with:` | **required** — the only one |
| `bo:` | `3` |
| `rule:` | `first` |
| `visibility:` | `private` |
| `bans:` | `on` |
| `level:` | `tournament_default_level`, else refuse |
| `class:` | `tournament_default_class` |

An omitted option is `None` and resolves once, in one helper — not a branch per
option. Only the two keys above reach `/config`; the rest resolve to a constant,
because a *default* and a *setting* are different things and only the second
earns a registry entry.

### What the registry needs first

**Prefer the tuple type over int wherever the option set is small.** `best_of`
is `("1","3","5")`: the registry's enum type is self-bounding and yields a
picker for free.

The `min`/`max` addition to `ConfigKey` drafted earlier is **no longer a
prerequisite** — decision 34 removed every int key this module wanted. It
remains a real gap (`chardle_bpm_window` and `chardle_abandon_hours` are
unbounded, and `parse.py` coerces an int and validates nothing), just not this
module's gap to close.

## The match board

**The image design is the owner's.** This section is the *contract* it draws
from and the constraints it has to live inside — not a layout.

### The seam

`views.py` builds a pure `MatchView`; `render.py` turns it into a `Rendered`
(`embed` + `file` + rows) and `imaging/` composes the picture. `render.py`
returns the text board when there is no `ATTACH_FILES` or the compose raised.
Nothing outside `imaging/` changes when the design changes.

### `MatchView`

| Field | Notes |
|---|---|
| `kind` | `quick` \| `tournament` |
| `stage_label` | `QF1`, `Grand Final`, or `None` |
| `best_of` | 1, 3, 5 |
| `scoring_rule` | `first` \| `best` — the board states it; it changes how a player plays |
| `state` | `draft` \| `pickban` \| `playing` \| `closed` \| `cancelled` |
| `sides` | ordered by `side_index` |
| `pool` | ordered by `ordinal` |
| `turn` | `Turn \| None` |
| `song_mode` | `True` when the chart set is several difficulties of one song |
| `winner_side` | index, or `None` |
| `now_ms` | so the renderer never calls the clock itself and a board is reproducible in a test |

`Side`: `arcaea_name`, `discord_id`, `avatar_url \| None`, `rounds_won`.

`Turn`: `side_index`, `action` (`ban` \| `pick`), `deadline_ms`.

`PoolEntry`: `chart`, `state` (`available` \| `banned` \| `picked` \| `playing`
\| `played` \| `unplayed`), `acted_by_side \| None`, `auto: bool`,
`round_ordinal \| None`, `result: RoundResult \| None`.

`ChartRef`: `title`, `artist`, `difficulty_class`, `level_display`,
`cc_display`, `jacket_path`, `side`, `spoilered`.

`RoundResult`: per-side `score \| None`, `time_played_ms \| None`,
`winner_side \| None`, `tied: bool`, and for song mode the `ChartRef` **each
side actually played** — in casual mode the players choose different
difficulties, so a result row that does not say which chart it measured is
unreadable.

### What the board must be able to draw

Six states, one layout:

| State | Must show |
|---|---|
| `draft` | Roster forming, format (`Bo3`, `first`), the filters the pool will use. No pool yet |
| `pickban` | Every pool entry with its mark; whose turn, which action, the countdown |
| `playing` | The live round's entry marked; its window countdown; scores as observed (decision 31); prior rounds resolved with winners |
| between rounds | Prior results, the intermission countdown to the next round |
| `closed` | Full scorecard, match winner, unplayed rounds marked as such |
| `cancelled` | Whatever was reached, marked dead |

And two shapes:

- **Head-to-head** — pool as a scorecard, two sides, `alice 1 — 1 bob`.
- **Three or more** — no pool and no bans; the chart list plus a standings
  block. This is the only shape where the board looks like a leaderboard.

### Constraints the design has to respect

- **No viewer.** One image is seen by everyone in the thread. There is no "you",
  no per-viewer highlight, and nothing ephemeral.
- **Names come from the Arcaea account**, not Discord — the roster is
  `arcaea_account_id` (decision 11). Discord mentions go in the message text
  *under* the board, where they can actually ping.
- **Height scales with the pool** (≤7 head-to-head) but with the *roster* in the
  3+ shape. Cap the drawn rows and render `and N more`; a 50-player event board
  must not be an unbounded image.
- **Sentinel `level`/`cc` render `?`**, never a decoded number
  ([[d-level-cc-sentinel-values]]). Same rule chardle's board follows.
- **CJK titles need the per-character font fallback** already written in
  `chardle/imaging/fonts.py`.
- **Avatars cost an HTTP fetch per side per render.** Cache on
  `(user_id, avatar_hash)` or leave them out — this is a design input, not an
  implementation detail to discover later.
- **Two encodings.** A live board is re-uploaded on every edit; a final board is
  uploaded once and is the one people screenshot. `chardle/imaging/encode.py`
  already draws this split (1200px q80 live, full q95 final) and should be
  **lifted to `coda/imaging/`** and shared rather than copied. `fonts.py` and
  `text.py` are the other two obvious lifts.
- **Spoiler blurs the whole container**, board included
  ([[h-spoiler-is-a-render-mode]]). Accepted: a round's chart is the round's
  identity, so there is nothing left to show once it is hidden. Decision 30
  keeps this rare.

## Derived, needs a nod

Forced by a locked decision above, but never stated by the owner:

| Item | Derivation | Proposed |
|---|---|---|
| **Pool size** | Decision 28 needs 2 bans, `best_of - 1` picks and 1 decider | `2 + (best_of - 1) + 1` → Bo1: 3, Bo3: 5, Bo5: 7 |
| **First actor** | Alternating needs a start, and a fixed one is an advantage | Random, shown on the board |
| **Intermission exists at all** | `playing -> playing` must not wait on a human (decision 10), but `2t` assumes a player is already at song select | A countdown between rounds, ended early by `Ready` (decisions 32–33) |
| **Pool with too few charts** | The filter can return fewer than the pool needs | Refuse at `/tournament quick`, naming the shortfall — never silently shrink the format |

The **constants** are the other half of this list: 60s turn, 60s intermission,
60s grace, and the `Bo3` / `first` / `private` / `bans on` defaults are
proposals, not measured values. Decision 34 makes them one line each to change,
and decision 32 makes them rarely reached — but they are what a server that
configures nothing actually plays under, so they are worth a look.

## Out of scope

- **The formats layer.** Registration, seeding, brackets, round robin, the
  lobby, async scheduling and no-shows are **designed**, in
  [[handoff-14-tournament-formats|handoff 14]] — not here. Locked in this
  document and relied on there: a tournament match gets its own thread, never
  reuses one, and is named for its stage (decision 20).
- **Song ownership as a validity or ranking input.** Unchanged from the first
  pass. Decision 26 reintroduces it only as a *pool generation filter*, and only
  as a future one — it is a no-op until the ownership blob exists
  ([[h-ownership-blob-open-before-building]]).
- **Any format ranking on accuracy, clear type, or gauge.** Decision 5 and
  [[h-every-valid-score-counts]].
- **A history command.** Decision 20 makes the crew thread the history surface;
  scrolling it is the feature.
