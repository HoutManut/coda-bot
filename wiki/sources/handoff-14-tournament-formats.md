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
tags: [source, handoffs, tournaments, formats, unbuilt]
aliases: ["14 — tournament formats"]
---

# 14 — Tournament Formats

## Covers

The **formats layer**: registration, the four tournament types, seeding,
asynchronous match scheduling, no-shows, and the standings the non-elimination
formats produce.

**Depends on [[handoff-13-tournaments|handoff 13]] being built.** Everything
here sits on top of the match object and adds nothing beneath it. Build 13
first: a quick match exercises every table, query and surface this document
relies on, and none of them changes shape when this lands.

> [!note] Why this is a separate document
> The match is the invariant unit — **every format decomposes into matches** —
> so the seam between the two handoffs is a real one and not a filing
> convenience. Nothing below the tournament knows which format produced it. A
> format's entire job is upstream of a match starting and downstream of one
> finishing.

Decisions continue 13's numbering rather than restarting, so a reference to
"decision 29" means the same thing in both documents.

## What a format is

**A format decides exactly two things: which matches exist, and what a finished
match does next.** Nothing else about a tournament varies — the pool, pick/ban,
best-of, windows, ranking and the board are all the match's, and are identical
in every format.

| Format | Which matches exist | What a finished match does |
|---|---|---|
| `lobby` | **one**, holding every entrant | nothing — it *is* the tournament |
| `round_robin` | one per pair, `N(N-1)/2` | adds a win to the standings |
| `single_elim` | one per bracket node | feeds the winner forward; the loser is out |
| `double_elim` | winners + losers bracket nodes | feeds the winner forward **and** the loser sideways |

That table is the whole design. The rest of this document is what it takes to
make those four rows true.

## Locked decisions

43. **A format decides which matches exist and what a finished match does next,
    and nothing else.** Anything a format wants to change below that line is a
    change to [[handoff-13-tournaments|handoff 13]], and should be resisted.
44. **Four formats**: `single_elim`, `double_elim`, `round_robin`, `lobby`. The
    enum is closed; a fifth is a new decision, not a new row.
45. **A lobby is one match.** Everyone is a participant, there is no pick/ban,
    it plays N rounds off the generated pool, and points accumulate. This is the
    first pass's "server-wide event" made repeatable — not a new object.
46. **Brackets and round robin are asynchronous; lobby and quick match are
    synchronous.** A bracket match sits waiting for both players and is fired by
    the **instant start** button (decisions 32–33). Rounds *inside* a match stay
    synchronous and completely unchanged.
47. **Seeding is a random shuffle at registration close, shown on the board
    before the first match is playable.** Not registration order (which rewards
    typing fast and lets someone register late to dodge a seed) and not player
    rating — on tier 1 the bot can only infer a rating, and decision 12 already
    refused to let ratings decide anything competitive.
48. **Advancement is explicit data, never computed at read time.** Each match
    carries `winner_to_match_id` / `winner_to_slot` and, for double
    elimination, `loser_to_match_id` / `loser_to_slot`, written when the bracket
    is generated. Same instinct as [[h-no-orm-relationships]]: the graph is
    rows, and a bracket can be read in `psql`.
49. **A no-show forfeits; two no-shows stall.** At `play_by_ms`, one side Ready
    and the other never → the ready side takes the match and advances. Neither
    side Ready → the match **stalls** and is flagged for the organizer, never
    auto-voided. Silently emptying a branch of a bracket is worse than a stall
    someone can see and resolve.
50. **The registration roster and a match roster are different tables.**
    `tournament_entrants` is who signed up and carries the seed and the
    standings; `tournament_participants` is who is in one match. A bracket
    entrant appears in several matches and is eliminated from the tournament,
    not from a match.
51. **A tournament has a hub thread plus one thread per match.** The hub holds
    registration and the bracket board; each match gets its own thread off the
    home channel, named for its stage, and never reuses one (decision 20).
52. **Byes go to the top of the shuffle.** A field that is not a power of two is
    padded to `next_pow2(N)`; the first `next_pow2(N) - N` seeds get a bye,
    which is a match that closes the instant it is created.

## Schema

Two new tables, plus columns on `tournament_matches`.

### `tournaments`

| Column | Type | Notes |
|---|---|---|
| `id` | `Integer` PK | |
| `guild_id` | `BigInteger` not null | |
| `home_channel_id` | `BigInteger` not null | match threads hang off this |
| `hub_thread_id` | `BigInteger` not null | registration + the bracket board |
| `board_message_id` | `BigInteger` nullable | the bracket board, edited in place |
| `name` | `String(80)` not null | thread names derive from it |
| `format` | `tournament_format` enum | decision 44 |
| `state` | `tournament_state` enum | `registering` \| `running` \| `closed` \| `cancelled` |
| `best_of` | `SmallInteger` not null | authored onto every match |
| `pick_ban` | `Boolean` not null | authored onto every match |
| `scoring_rule` | `scoring_rule` enum | authored onto every round |
| `pool_level` | `String(16)` not null | the filter every match's pool is drawn with |
| `pool_class` | `difficulty_class` enum | |
| `lobby_rounds` | `SmallInteger` nullable | `lobby` only |
| `play_by_hours` | `SmallInteger` nullable | async formats only; sets `play_by_ms` |
| `creator_discord_id` | `BigInteger` not null | |
| `created_at` | `DateTime(tz)` | |

The five format-neutral fields (`best_of`, `pick_ban`, `scoring_rule`,
`pool_level`, `pool_class`) are **authored down onto each match at generation**,
never read up from the tournament at match time. A match must stay readable on
its own — that is the seam this whole split rests on.

### `tournament_entrants`

| Column | Type | Notes |
|---|---|---|
| `tournament_id` | FK `ondelete="CASCADE"` | |
| `arcaea_account_id` | FK `ondelete="RESTRICT"` | a roster is history |
| `seed` | `SmallInteger` nullable | written at registration close (decision 47) |
| `state` | `entrant_state` enum | `active` \| `eliminated` \| `champion` |
| `points` | `Integer` not null default 0 | `lobby` and `round_robin` standings |

`UNIQUE (tournament_id, arcaea_account_id)` — decision 11, one level up.

### Added to `tournament_matches`

| Column | Type | Notes |
|---|---|---|
| `bracket_side` | `bracket_side` enum nullable | `winners` \| `losers`. Elimination only |
| `bracket_round` | `SmallInteger` nullable | depth; drives the stage label |
| `winner_to_match_id` | FK self nullable | decision 48 |
| `winner_to_slot` | `SmallInteger` nullable | which `side_index` it lands in |
| `loser_to_match_id` | FK self nullable | `double_elim` only |
| `loser_to_slot` | `SmallInteger` nullable | |

And one value on the `match_state` enum: **`awaiting`**, meaning the slots are
not filled yet because a feeder match has not finished. Bracket-only; a quick
match never reaches it.

## Match lifecycle, extended

Handoff 13's machine gains one state in front of it:

```
awaiting ──both slots filled──> scheduled ──all Ready──> draft ──> pickban ──> playing ──> closed
   │                                │                                                        │
   │                                └── play_by_ms, one side Ready ──> closed (forfeit) ──────┤
   │                                └── play_by_ms, neither Ready ──> STALLED (organizer) ────┘
   └── fed by a bye ──> closed
```

| From | To | Trigger |
|---|---|---|
| `awaiting` | `scheduled` | the last feeder finishes and writes its participant in |
| `awaiting` | `closed` | it is a bye (decision 52) |
| `scheduled` | `draft` | every participant `Ready` — the instant start button |
| `scheduled` | `closed` | `play_by_ms`, exactly one side Ready → forfeit |
| `scheduled` | `scheduled` | `play_by_ms`, neither side Ready → stalled flag, organizer resolves |

`round_robin` and `lobby` matches are created straight into `scheduled` and
`draft` respectively — every participant is known at registration close, so
nothing feeds them.

**A stall is a flag, not a state.** `play_by_ms` is left in the past and the
board marks it; the organizer advances someone or cancels. Adding a sixth match
state for a condition that is entirely "a human must look at this" would put the
stall in the machine, where decision 35 says it does not belong.

## Tournament state machine

```
REGISTERING ──open──> RUNNING ──> CLOSED
     └──────── cancel ──────────> CANCELLED
```

| From | To | Trigger | Effect |
|---|---|---|---|
| `registering` | `running` | organizer, or the registration deadline | Freeze entrants. **Shuffle and write seeds.** Generate every match and the advancement graph. Open what is playable |
| `running` | `closed` | no match is unfinished | Mark the champion (elimination) or freeze the standings (round robin, lobby) |
| any | `cancelled` | organizer | Every match cancels; threads stay for the record |

Generation is **one transaction at registration close**, not incremental. Every
match row, every participant row that is known, and the whole advancement graph
are written together, so a crash mid-generation leaves no half-bracket and the
board never renders a partial structure.

## Standings

### Elimination

There are none — there is a champion. The board shows the bracket.

### Round robin

Rank by **matches won**, tie-break on rounds won, then head-to-head. The
head-to-head tie-break is exact for a pair and undefined for a three-way cycle;
a cycle is left as a displayed tie rather than broken arbitrarily.

### Lobby

**Points = the number of entrants you finished ahead of, plus one for playing.**
A no-score is 0. With 20 entrants first place scores 20, last place who actually
played scores 1.

No fixed points table, deliberately: a table has to be tuned to a field size and
is wrong at every other one, while this scales to any lobby and needs no
decision. It follows decision 5 exactly — a round is ranked on raw score and the
points are a pure function of that ranking, adding no second opinion about what
a play was worth.

Ties inside a round share the higher placing and both take those points.

## Surface

### Commands

| Command | Does |
|---|---|
| `/tournament create` | `name:`, `format:`, `bo:`, `bans:`, `rule:`, `level:`, `class:`, `rounds:`, `play_by:`. Opens the hub thread, posts the registration board |
| `/tournament register` / `withdraw` | While `registering` |
| `/tournament open` | Organizer or admin: close registration, seed, generate |
| `/tournament cancel` | Organizer or admin |
| `/tournament resolve` | Organizer: advance a side in a stalled match (decision 49) |

`create` carries every format option and needs no guild defaults — this is
decision 37's point exactly. The organizer is already filling in a form, so
options are free here in a way they are not on `/tournament quick`.

### Threads

The **hub thread** hangs off the home channel, named for the tournament, and
holds registration and the bracket board. Each **match thread** hangs off the
home channel too — not off the hub, because a thread cannot nest — named
`<name> · QF1 — alice vs bob`, and is announced in the hub with a link when it
becomes `scheduled`.

Visibility follows the tournament: a public tournament's threads are public.

## The bracket board

A second image, a second view, the same seam and the same fallback rules as
handoff 13's match board.

`TournamentView`: `name`, `format`, `state`, `entrants` (name, seed, state,
points), `matches` (stage label, both sides or empty slots, result, state,
`stalled: bool`, thread link), `standings` (round robin, lobby), `champion`.

Three shapes:

| Format | Shape |
|---|---|
| `single_elim` | a bracket tree, left to right by `bracket_round` |
| `double_elim` | two stacked trees, winners above losers, with the drop edges drawn |
| `round_robin` / `lobby` | a standings table; round robin adds the pairing grid |

**Width is the hard constraint here, not height.** A 16-entrant double
elimination bracket is five columns of winners plus eight rounds of losers, and
Discord will scale the whole image down to fit rather than let it scroll. Two
mitigations worth designing for from the start: render **one stage at a time**
with the current stage in full and the rest as a strip, or cap the drawn field
and link the hub's text for the remainder. This is the first surface in the bot
where the image genuinely may not fit, and it should shape the design rather
than be discovered late.

Everything else from handoff 13's §The match board applies unchanged: no viewer,
Arcaea names, two encodings, sentinel `?`, cache avatars or drop them.

## Derived, needs a nod

| Item | Derivation | Proposed |
|---|---|---|
| **Lobby points** | Decision 45 needs a rule and decision 5 forbids a second opinion on a play's worth | `entrants you beat + 1`; no-score 0 |
| **Round-robin tie-break** | Matches won will tie | rounds won, then head-to-head, then a displayed tie |
| **`play_by` default** | Decision 46 needs a number | 48 hours |
| **Registration deadline** | Optional; `open` can be manual | Manual by default, optional deadline on `create` |
| **Minimum field** | A 2-entrant bracket is a quick match with paperwork | Refuse a bracket under 4 entrants; refuse a lobby under 2 |

## Out of scope

- **Anything below the match.** Windows, validity, ranking, the pool, pick/ban,
  threads for a single match, the match board — all
  [[handoff-13-tournaments|handoff 13]].
- **Swiss, group stage into bracket, and seeded re-draws.** Decision 44 closes
  the enum; each of these is a new decision.
- **Cross-guild tournaments.** Everything is `guild_id`-scoped, per handoff 13
  decision 18.
- **Prizes, roles, or anything that writes to Discord beyond a thread and a
  message.**
