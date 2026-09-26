---
type: domain
status: active
source: arcaea-tournament-layer.md
verified: 2026-09-02
created: 2026-07-21
updated: 2026-09-06
tags: [domain, arcaea, tournaments, ui]
---

# Tournaments

**Status: the match layer is BUILT** (2026-09-02, [[tournaments-module|the
module page]]). `src/coda/tournaments/`, seven tables, and `/tournament` ship
[[handoff-13-tournaments|handoff 13]]. The **formats** layer
([[handoff-14-tournament-formats|handoff 14]]) is not built: brackets, round
robin, the lobby, registration and async scheduling do not exist, and the
columns reserved for them (`tournament_id`, `stage_label`, `scheduled`,
`play_by_ms`, `admin_gated`) are written by nothing.

Four owner rulings on 2026-09-02 changed the shipped design away from handoff
13, all in one direction — **a quick match should be worth configuring, and
casual play is a first-class option rather than an accident**:

| Delta | Handoff said | Shipped |
|---|---|---|
| `/config` keys | exactly two (`level`, `class`) | **four**: `level`, `bans`, `best_of`, `visibility` |
| Level | a single band; unset ⇒ **refuse the match** | a **range**; unset ⇒ **any level** |
| Class | a config key, default `ftr` | **removed from config**; a **required** option whose `any` value means a **casual, song-mode match** |
| Ownership filter | an option, gated on the ownership blob | **always on**, no option — you cannot play a chart you do not own. **Live since 2026-09-06** |

Two further deltas came from measuring the design against the shipped poller
rather than from the owner, and are recorded in [[tournaments-module]]: the hot
cadence is **15 s, not 5 s**, and the board's **debounce dissolved into the
sweep tick**.

> [!important] The spec is handoffs 13 and 14, not this page
> Two design passes have landed. The first (2026-07-17) settled scoring,
> validity and windows — everything below that is not marked otherwise. The
> second (2026-09-02) settled the **surface**, and added an object this page
> did not have: a **match** between the tournament and the round, and a
> **formats** layer above it. Where this page disagrees with either handoff, the
> handoff wins; they are the newer source and carry the schema.
>
> The spec is split at the match, which is the invariant unit:
> [[handoff-13-tournaments|handoff 13]] is the **match and everything under it**
> (build it first — a quick match exercises all of it), and
> [[handoff-14-tournament-formats|handoff 14]] is the **formats layer** —
> registration, brackets, round robin, lobby, seeding, async scheduling.
>
> Two first-pass claims were **reversed** by the second pass and are corrected
> in place below: a room could live in a DM (§Starting a match), and song
> ownership was unconditionally out of scope (§Traps).

## Model

A tournament round is an **eligible chart set + a time window**, scored by
reading rows the poller already wrote for an unrelated reason. **The tournament layer never
calls the lowiro API.** It does exactly two things:

1. **Declares hot windows** — tells the poller which accounts to poll faster, because a round is open.
2. **Reads `play_scores`**, filtered by chart set, roster, and time range.

The poller already fetches `/webapi/friend/me` for every friend on a bot
account — participants and non-participants alike, since the endpoint has no
way to request a subset. A round's scores are already arriving in the ingest
stream; a tournament-specific fetch would be a second request for bytes
already received. This makes the module testable by inserting score rows —
no HTTP, no session/`bot_account_id` awareness anywhere in it. See [[score-poll-loop|Score Poll Loop]].

### Three objects, not one (second pass, 2026-09-02)

The first pass had only the round. Deciding that the board renders **match
state** — a chart pool carrying pick/ban marks and per-chart winners — forced a
layer above it, because a pool spans several rounds and cannot be a property of
any one of them:

```
tournament   multi-round event, registration, bracket   (not designed)
  └── match  a pool → pick/ban → best-of-N              a thread holds this
        └── round   one chart set + one window          everything on this page
```

Everything this page says about validity, windows, ranking and cadence is about
the **round**, and is unchanged. What moved is ownership of the Discord-facing
state: the roster, the pool, the pick/ban sequence and the best-of count belong
to the match. A round no longer knows what a guild is.

**A quick match is a match with no tournament** — `tournament_id IS NULL`, not a
second code path. The only behaviour that turns on it is thread reuse
(§Starting a match).

Two formats follow from roster size, and they are the same object:

| Roster | Pick/ban | Chart set |
|---|---|---|
| 2 | two bans up front, then **one pick per round**; the survivor is the decider | one chart per round, from the pool |
| 3+ | none | the generated pool **is** the round's chart set, one round |

The 3+ shape is the casual song-mode round this page already described. Pick/ban
was confined to head-to-head deliberately: with five players and six charts,
whoever bans last shapes the pool alone. Banning is also switchable off outright.

#### Picks are interleaved, not drafted (owner, 2026-09-05)

Only the **bans** run up front. Each pick is served **between rounds** — ban,
ban, pick, play, pick, play — with the decider reserved for last. The shipped
build drafted the whole card before round one, which is the CS2 map-veto shape;
this is the osu! shape, and osu! is the convention every rhythm-game tournament
scene copies.

The argument is that a draft made up front throws away the only information a
pick could answer. A Bo7 asked for six picks back to back, all six decided at
0-0, so the player who was 1-3 down could never pick their way back — and six
60-second turns ran before a note was played. Interleaving also stops a match
decided 4-0 from having drafted the two charts nobody plays.

The **pool size is unchanged** (`2 + (best_of - 1) + 1`) — the worst case is
still every round being played. What changed is only *when* a turn is asked
for, so `pickban.py` is untouched: the sequence is still one flat list and the
next turn is still position `turn_index` in it. See
[[tournaments-module#Interleaved picks]].

Multiple ban phases were considered with it and **rejected**. The one
conventional shape for more banning is CS's `ban ban → pick pick → ban ban →
decider`, and its second ban round only exists because there is a pick *phase*
to sandwich it around. Once picks move into the breaks there is nothing left to
sandwich, and a ban between rounds would be banning charts that may never come
up.

#### The rest comes before the pick (owner, 2026-09-06)

The gap between two rounds runs **result → rest → pick → play**. The pick is the
last thing that happens before the chart is revealed and the window opens.

The interleaved build above served the turn on the *result* and let the 60 s
pick run concurrently with the 300 s rest, measuring the rest from the previous
round's close either way. That cost no wall clock — the turn fit inside the rest
with four minutes to spare — but it put the gap's last ask *before* its wait: a
player picked their chart, and then a fresh "hit **Ready** to go sooner" line
appeared. Tested on a third-party player, who **picked and then waited**,
expecting to play. They never pressed it.

Ordering beat wall clock. Two smaller things fell out of the same evidence: a
picker could have their chart taken by `pickban.auto_pick` while they were still
reading the result, and `prompts._break` justified its deliberate no-ping with
"the result beat lands at the same instant and has already pinged both sides" —
false since 2026-09-05, because the break line no longer landed with the result.
Both are gone: the turn clock now starts when the player is actually being
asked, and the rest's prompt is once again simultaneous with the result beat.

What it costs: the worst case gap grows from 300 s to 300 + 60 — a rest nobody
skips followed by a turn nobody answers. Engaged play is unchanged or faster,
because the Ready flags that ended the rest are **not** cleared when the turn is
served, so the sweep after the pick opens the round instead of asking again. See
[[tournaments-module#Rest, then pick]].

### A format decides two things, and only two

Because the match is the invariant unit, a tournament format has a very small
job: **which matches exist, and what a finished match does next.** Nothing below
the tournament knows which format produced it.

| Format | Which matches exist | What a finished match does |
|---|---|---|
| `lobby` | **one**, holding every entrant | nothing — it *is* the tournament |
| `round_robin` | one per pair, `N(N-1)/2` | adds a win to the standings |
| `single_elim` | one per bracket node | feeds the winner forward; the loser is out |
| `double_elim` | winners + losers nodes | feeds the winner forward **and** the loser sideways |

A **lobby** is the first pass's "server-wide event" made repeatable: one match
holding everyone, no pick/ban, N rounds off the pool, points accumulating.

**Brackets and round robin are asynchronous** — 8-player round robin is 28
matches and cannot run in one sitting — so a bracket match waits for both
players and is fired by an instant-start button. Rounds *inside* a match stay
synchronous and unchanged. Full spec in
[[handoff-14-tournament-formats|handoff 14]].

## Encoding

### Score validity

A round declares an **eligible chart set**, not a single chart. Two
independent parameters, never conflated:

| Parameter | What it decides |
|---|---|
| `chart_set` | which plays are eligible |
| ranking | how eligible plays are compared — **always raw `score`**, see [[h-score-is-the-only-ranking-value]] |

With a one-chart set the two questions have the same answer, which is why the
original single-chart design could fold them together. Song mode separates
them.

```
valid(score, round) =
      score.song_difficulty_id in round.chart_set
  and round.start <= score.time_played <= round.end
```

Membership is on the **resolved** `song_difficulty_id`, never `song_id` — the
wire gives `(song_id, difficulty)` and ingest resolves that pair to a catalog
row before the tournament layer sees it. That is also what makes `byd_2` free
(see [[score-mapping|Score Mapping]]).

The set is what distinguishes the formats:

| Format | `chart_set` | Difficulty chosen by |
|---|---|---|
| Standard | one difficulty | the organizer |
| Casual (song mode) | every difficulty of one song | **the player** |

**Song mode is `class: any`** (owner, 2026-09-02, built the same day). It is
the one option that decides what kind of match this is, so it is typed every
time and never inherited from a guild default. A pool entry is then a **song**
rather than a chart — `tournament_pool_entries.song_difficulty_id IS NULL` —
and the round's chart set is resolved at round-spawn time from the match's
stored filters.

**The level band still bounds a casual set.** A lv9–10 match must not be
winnable by posting 10,000,000 on a PST 4, so a song's set is the difficulties
that pass the band, not all of them; a song with none in band is never drawn at
all. With no band set it is genuinely every difficulty, which is the fully
casual shape. This keeps the band as *the* balancing lever the section below
describes, rather than making it decorative in the mode that needs it most.

Casual mode mirrors the game's own multiplayer room: the room picks a song and
each player picks their own difficulty. Ranking does not change — a PST
9,900,000 and an FTR 9,900,000 are the same number and tie. This is intended,
not an approximation being tolerated.

**The chart set is always an explicit organizer choice.** It is never derived
from player ratings, from song ownership, or from any catalog inference — see
[[h-no-catalog-inferred-ownership]]. Since a lower difficulty is generally the
easier place to post a high score, pool selection is *the* balancing lever in
song mode: an organizer who wants the difficulty choice to be a real decision
picks charts of comparable CC. An organizer running a genuinely casual round
does not have to care.

`time_played` is **server-assigned**, UTC milliseconds, at submission — a
moved device clock cannot forge window membership (graded, verified
2026-07-17 against [[arcaea-auth-behavior]] §7.3). This is what makes
"played inside the window" a real guarantee, not an honour system. The only remaining skew is the bot's clock vs lowiro's server clock — both presumably NTP-synced; see [[h-tournament-clock-skew]].

**Two windows, not one:**

| Window | Applies to | Range |
|---|---|---|
| Validity | `time_played` | `[start, end]` — never moves |
| Observation | wall clock | `[start, end + grace]` — the grace is a **backstop** |

Polling is discrete, so a play at `end - 1s` may not be *seen* until after
`end`. Keep polling through the grace period; keep accepting only
`time_played <= end`.

The observation window ends the moment there is nothing left to observe: under
`first`, a full set of scores. See [[#The round clock]].

### The window duration

**Flat 300 s** (`WINDOW_SECONDS`), built 2026-09-03. Not derived from chart length,
and not clamped: `clamp(2t, 200s, 500s)`, `duration_for`, `chart_times` and **decision
8's `t = 0` sentinel rule** were all deleted with it — they existed only to size a
window that is no longer sized. See [[h-tournament-window-and-clock]].

It can be flat because it is rarely spent. Under `first`, `_maybe_close_window` exits
the moment both sides have scored, so 300 s is a **forfeit timeout**, not a budget.
Polling starts at window **open**, not `start + t` — a hard-gauge loss submits its
score seconds in ([[scoring|Scoring]] §5), so a valid score can land almost immediately.

> [!warning] "Forfeit timeout, not a budget" is wrong — it is a reroll budget
> `all_scored` needs BOTH sides, so an honest opponent's submission closes nothing — a
> player who keeps quitting (and so keeps submitting nothing) holds the window open to
> `end_ms` alone. At `t = 150 s` that is roughly three retries, aimed at a target the
> board is publishing live. Opened 2026-09-04, no fix built:
> [[h-tournament-quit-rerolls-first]].

**The early exit is unconditional.** A full set of scores is a result nothing can
change, so the window shuts on it. This used to be gated on the `first` rule; with
`best` retired ([[h-first-score-is-the-only-rule]]) there is no other case to gate
against, and the flat window no longer owes anyone an explanation for being flat.

### The round clock

```
window  ≤300s   validity: only time_played inside [start_ms, end_ms] counts.
                SHUTS EARLY once everyone has scored
grace    ≤60s   observation slack — polling is discrete, so a play at end - 1s
                may not be SEEN until after end. Board: "Looking for scores…".
                Under `first` it too ends the moment every score is in, which
                is usually the same instant the window shut
result          the round is decided. BEAT: a new message naming who took it
break    300s   a rest to read the result in, and the only slack a match has.
                Skippable the moment everyone is Ready
reveal          the next chart is named. BEAT: a new message, both sides pinged
                — and start_ms is this instant
```

**The reveal is the only "go" a match needs.** A chart is not announced until its break
ends, so a player cannot act before the window opens, and there is no soft start,
no leniency and no gap in which a play lands nowhere. It is also what stops **chart
banking**: charts are knowable before their round opens — the whole card at once
without pick/ban, and the decider once the last pick lands — so any anchor earlier
than the reveal would let a player put a score on a later round's chart during an
earlier one, fatally under `first`, where the banked play would be the first inside
the window and would lock in. Interleaving the picks shrinks how far ahead a chart
can be known but does not remove it, and the mitigation is the same either way.

`start_ms`/`end_ms` are still set together and **never move**.

**The break is 300 s, and it is the only slack in a match.** Raised from 60 s on
2026-09-04: a window ends the instant both sides have scored, so a Bo3 on a
one-minute break ran three charts effectively back to back. It costs nobody
anything, because it is skipped the moment both sides are Ready — a long
skippable rest is strictly better than a short compulsory one.

**The break is a rest, not a navigation budget.** It runs from `closed_at` — the
moment the scores are gathered and the round is decided — because there is no result
to read before then. `closed_at` is the round's stored `closed_ms`, falling back to
`end_ms + grace_ms` while it is still gathering: the sum is the deadline a live round
is heading for, never the moment it lands on.

> [!warning] Fixed 2026-09-04 — the early exit used to buy nothing
> Both early exits fed a `closed_at` derived from the fixed `end_ms`, so a round where
> both sides scored at 3½ minutes still decided at `end_ms + grace_ms` and the next one
> still opened 60 s after *that*. The board simply swapped its countdown for
> "Looking for scores…" and sat on a result it already had — 2½ minutes of it in the
> live test of match 1134. Grace now ends on `all_scored` as well, and the real close
> is stored (`tournament_rounds.closed_ms`) so the break is measured from it. The old name (`INTERMISSION_SECONDS`)
and its stated reason ("the 2t window assumes a player is already at song select") were
both retired: 300 s contains song-select time outright.

### The first score counts — not a parameter

```
each player's FIRST valid score in the window. Nothing else is offered.
```

**Retired 2026-09-05: `best` is gone**, along with the `scoring_rule` column,
the `rule:` option and the enum — see [[h-first-score-is-the-only-rule]].
`last`-counts was never offered either (instant exit is arbitrary; nobody asked
for it). A round has one rule, the board prints it, and there is no mode to
choose.

| | The rule |
|---|---|
| Counts | each player's first valid score in the window |
| Retrying | pointless *if you finish* — a **quit submits nothing** ⚠️ |
| Instant exit on all-scored | provably lossless |
| The 300 s window is | a **~3-reroll budget** ⚠️ (intended: a forfeit timeout) |
| Hard-gauge loss | **locks in** ⚠️ |

⚠️ **First does not mean one attempt.** It binds the first *submitted* score, and a
quit submits nothing — so the window is a retry budget, aimed at the score an open
round already shows on the board. Unfixed, and no window length fixes it:
[[h-tournament-quit-rerolls-first]].

⚠️ **Hard gauge is a trap, and the player's own choice.** A hard-gauge loss
submits its score seconds in ([[scoring|Scoring]] §5), so it is the player's first
valid score inside the window: it counts and it locks in. Normal and easy gauge
cannot do this — HP hitting 0 costs nothing on those gauges, so the play always
runs to completion. **Hard gauge is strictly self-harming and normal gauge is
strictly safe** — this is a rule to tell players, not a bug to fix.

**It is not something to filter, on any tier.** A hard death and a very bad
complete play produce the same thing — a low number inside the window — and
both are real scores. Discarding either one would hand back a free reroll,
which is the one thing this rule exists to prevent. See
[[h-every-valid-score-counts]]; tier 1 losing `clear_type`/`modifier` costs
this rule nothing, because the rule never wanted those fields.

### State machines

Two, since the second pass. The match machine drives the round machine and never
reads a score; the round machine is unchanged except that `DRAFT` is renamed
`PENDING` — a round is now created by its match rather than authored by a human,
so there is nothing to draft.

```
match:  DRAFT ──everyone Ready──┬── 2 players ──> PICKBAN ⇄ PLAYING ──> CLOSED
                               └── 3+ players ────────────────> PLAYING ──> CLOSED
                          └────── cancel ──────────────> CANCELLED

round:  PENDING ──open──> OPEN ──┬── all participants scored ──> GRACE ──> CLOSED
                                 └── deadline reached ────────> GRACE ──> CLOSED
  │                                  │
  └──cancel──> CANCELLED             └──cancel──> CANCELLED
```

**Leaving `DRAFT` needs unanimous consent, not the organizer's word.** A quick
match opens a thread *at* someone who never asked for it, so the roster is an
invitation until each side answers it — and a match started against an absent
player is a forfeit dressed up as a game. Every participant hits **Ready** (the
same primitive as the break skip, [[#First: stop waiting, rather than tuning the wait]]);
the match starts on the last answer. `/tournament start` runs the *same* check
and is the way to retry a start that failed, never a way around the roster.
Joining clears every confirmation — what the others agreed to was a different
roster.

This is the one wait with **no backstop**, deliberately: the answer to a match
nobody confirms is `/tournament cancel`, because starting one player short is
worse than not starting.

**`PICKBAN` is re-entered, not passed through.** A match leaves it for `PLAYING`
after every pick and comes back once that round is closed, for as long as the
sequence still owes a turn and nobody has won yet. Two consequences fall out of
that: a gap where every round is closed and none is pending is *not* the end of
a match (reading it as one closes a Bo3 at 1-0), and a match in `PICKBAN` can
still owe the result beat for the round that just ended — the tick that closes a
round is usually the same one that hands the next pick back.

**The pick costs the gap between rounds nothing.** The break still runs from the
previous round's close, so the turn happens *inside* it rather than on top of
it, and a pick that takes the full minute leaves four of the five.

**The same "never wait on a human" rule applies one level up.** A pick/ban turn
has a deadline like a round does, and on expiry the bot bans or picks **at
random** from what remains, so a match always reaches its first window. Random
rather than deterministic: a forced action chosen by pool order is guessable in
advance, and therefore exploitable against a pool the organizer ordered. The
board marks an auto action distinctly — an auto-ban reads differently from a
chosen one.

A match ends the moment a side reaches `ceil(best_of / 2)` wins; the remaining
rounds are never opened and render as `unplayed`.

| State | Meaning |
|---|---|
| `DRAFT` | Chart picked, roster forming. Not polled |
| `OPEN` | Validity window live, accounts hot. **Roster frozen** |
| `GRACE` | No longer accepting new `time_played`; still observing |
| `CLOSED` | Results final and immutable |
| `CANCELLED` | Cadence query stops matching it |

`deadline reached` is the **only universal exit** — a participant who never
plays resolves to "no score" at `end`. There must be no path where the
machine waits on a human; early exit (all-scored) is an optimization on top
of the deadline, never a replacement. Roster freezes at `OPEN` — joining
mid-round means an unequal window. Everything lives in the DB; on restart the
poller recomputes cadence from window times, nothing is lost.

### Cadence (policy set here, mechanism owned by the API layer)

- An open round makes every account holding one of its participants **hot**.
- Cadence is a **union across all open rounds** — never per-round.
- Hot is cheap: tournaments read the **friend path**, one request covers up to
  10 participants. Three hot accounts at 5s ≈ 36 req/min. Hot needs no
  rationing; the global limiter still caps total throughput.

| Format | Cadence is | Why |
|---|---|---|
| Single attempt | a **latency** knob | `recent_score` is sticky — the play waits to be found |
| Multi-attempt | a **fidelity** knob | each attempt overwrites the last |

### Tiers

**Since ranking is raw `score` and nothing else ([[h-score-is-the-only-ranking-value]]),
a round is tier-agnostic.** Every field a round needs — `song_id`,
`difficulty`, `score`, `time_played` — is present on the friend path, and the
tie-break (`earlier time_played`) is too. Mixing tiers in one bracket is
therefore safe, and the "do not mix tiers" rule below applies only to the
detail formats, which the score-only rule currently rules out. The rest of
this section is kept as the cost analysis for any future format that would
need own-path fields; it is not a live constraint on the formats described
above.

Tournaments are **mainly score-based** (owner decision, 2026-07-17), so the
friend path is primary and batches.

| Tournament kind | Minimum tier | Cost |
|---|---|---|
| Score-based | any | friend path, batched: ~1 request per bot account per cycle |
| Detail (accuracy, clear type, gauge) | **tier 2+** | 1 request per participant per cycle. Cannot batch, at any price |

**Detail tournaments cannot be centralized onto a bot account** — reading a
credentialed user through a bot's friend list returns tier-1 data anyway (the
five friend-only fields are a property of the endpoint, not the user). Moving
players onto a shared account to batch polling destroys the exact data being
collected.

**Do not mix tiers in one bracket.** A score-based round tolerates it (numbers
are comparable, ambiguity invisible); anything scored on *how* a play was
earned cannot score a tier-1 entrant at all. Declare a minimum tier at
signup. On tier 1 a hard-gauge death is indistinguishable from a low score —
`clear_type`/`modifier` are own-path only.

## Starting a match

A match is created as a **room**: any user opens one, invites or lets others
join while it is `DRAFT`, and the roster freezes when it leaves. A server-wide
event is not a second system — it is a room that is guild-scoped, open-join, and
whose state transitions are admin-gated. Validity, the state machines, cadence
and results are written once and shared.

### `open` is who may play; `visibility` is who may read

`/tournament quick` invites exactly one person, with `with`. A roster past two
— the 3+ shape §"Two formats follow from roster size" describes — is reached by
`/tournament join`, gated on the match's **`open` flag**.

Two flags, because they answer two questions, and collapsing them would make
every public match joinable by anyone watching:

| Flag | Question | Default | Read where |
|---|---|---|---|
| `visibility` | who may **read** the thread | `public` | thread creation, once |
| `open_join` | who may **play** | `false` | `/tournament join`, while `draft` |

`open` is off by default because a quick match is an invitation to one person,
and a third player arriving unasked is not the match those two agreed to. It has
no `/config` default, for the reason song mode has none: an open room and a
closed one are different matches, not one match configured differently, so it is
typed when it is wanted. `visibility` flipped to `public` (2026-09-05) — a room
nobody can look into cannot be joined, cheered at, or found again by anyone but
the two people in it, and privacy is still one option away.

The flag is only consulted while the match is `draft`; the roster freezes when
it leaves, so nothing has to un-gate later.

Two Discord users may link one Arcaea account, and a side is ranked by that
account's scores, so an opponent resolving to an account already on the roster is
**refused**: rostering it twice would hand both sides the same score every round.

### A roster change is a message, not just a redraw

Joining and leaving each post a line into the thread (`announce.joined` /
`announce.left`). They carry no stamp, unlike a round's beats: they report a
command that just ran, so there is nothing to re-derive and nothing owed if the
post fails. The board is one message, always overwritten, so it can show the
roster but never the *order things happened in* — the lines are what make the
thread a timeline of who turned up.

Joining already cleared every confirmation (§"Leaving `DRAFT` needs unanimous
consent"), but nobody was told: the start prompt's key was the constant
`"start"`, so `_reprompt` saw no change and left the old Ready button scrolled
somewhere above. The key is now `start:<roster size>`, so a join retires that
message and posts a fresh one pinging everyone. Consent is per-roster, and the
ask is re-issued whenever the roster it was given for stops existing.

This mirrors [[h-chardle-boards-are-channel-owned]]: solo-ness and scope come
from *where* a thing runs, not from a hidden permission check on an otherwise
identical surface.

### A match lives in a thread, and only in a thread

Second pass, 2026-09-02. Every match runs in a thread off the guild's dedicated
tournament channel. A guild with no channel set is **refused** — never fallen
back to the invoking channel, which is the exact mistake
[[h-chardle-boards-are-channel-owned]] §"The Chardle channel had to stop moving
inline boards" had to fix after shipping it the other way.

> [!warning] Reverses the first pass: there is no DM room
> The first pass allowed `guild_id NULL` = a DM/private room. **Deleted.** A bot
> cannot open a thread in a DM and cannot create a group DM, so a DM room could
> hold neither the board nor a second player. Privacy is a **private thread**
> instead, which is strictly better here: participants can talk to each other in
> it. Lobby, pick/ban, boards, results and trash talk all happen in the one
> place. The module is guild-only.

Visibility is the whole privacy model — `public` is readable by the guild,
`private` has the bot add each participant — and nothing else gates reading a
match. Privacy is not *delegated* to the thread, though: `MANAGE_THREADS` lets a
moderator read a private thread uninvited, so a pick/ban interaction still
verifies the clicker is the participant whose turn it is. Location narrows the
audience; the check enforces it. Same rule a chardle daily board applies.

### The crew thread is the history

A **quick match reuses its crew's thread**, keyed on the exact roster:
`(guild_id, sorted arcaea_account_ids, visibility)`. One extra player, one
fewer, or public-vs-private is a *different* thread. A hit unarchives and
reuses; a miss opens a new one. The thread then accumulates one board per match
and **is** that crew's head-to-head history — which is why there is no history
command and no results table.

A **tournament match never reuses**. A bracket match is a one-off by
construction, and folding it into a crew thread would bury it under unrelated
quick matches; it gets a fresh thread named for its stage and pairing.

The reuse key lives in a **table**, never inferred from the newest match. That
inference is precisely what failed for chardle dailies — it returns nothing
after any history gap, and it cannot tell a thread under the tournament channel
from one under any other, so a guild that moves its channel strands every player
outside it forever. Reuse revalidates the same three things
`chardle/transport.py:_reusable_thread` does: it is a thread, its parent is the
*currently configured* channel, and it is unarchived.

### A room is not tied to a bot account

**Rooms may span any number of bot accounts, and this needs no special
handling.** The friend link is a property of the *player*, not the round:
`pool.place()` writes `ArcaeaAccount.bot_account_id` once, `poll_key()` returns
`(BOT, bot_account_id)` for the sweep, and the tournament layer reads
`play_scores` by roster + chart set + window without ever seeing a
`bot_account_id` (see [[w-sid-confined-to-sessions]]).

So `max_friend` is **not** a per-room cap. A player consumes one slot once,
globally, and then joins unlimited rounds forever — the friend link is "a
one-time placement, not a move" (see Traps below). What the slot ladder bounds
is the total observable player population (plan 10 per account, ~5 accounts,
≈50 players — [[auth-and-sessions|Auth & Sessions]] §Friend-slot cap), not how
many rounds may be open.

The one genuine per-round cost is **cadence fan-out**, and it scales with
participant *scatter* rather than round count: an open round makes hot every
account holding one of its participants, so four co-located players make one
account hot while the same four spread across four accounts make four hot for
the same round. `place()` is greedy first-with-capacity and cannot know who
will play together, and re-placing costs a delete + add against the live
friend list. Measure this before capping anything.

### What the thread says, and what it asks

Three kinds of message live in a match thread.

| | What it is | How it is written |
|---|---|---|
| **Board** | the match: format, score, pool, phase, every clock, and the pick/ban menu | ONE message, an embed, edited in place |
| **Beat** | a moment: a chart revealed, a round decided | a NEW plain message, posted once, stamped on the round |
| **Prompt** | one line for a new wait, plus the button that answers it | a NEW plain message, posted once per wait |

**Controls split by what they are about.** The **pick/ban menu** is on the board,
because what it chooses from is the pool printed directly above it. Both
**Ready** buttons are on the prompt, because a Ready is an answer to a question
that was just asked out loud, and a question and its answer belong on one
message.

What an edit cannot do is get **noticed** — Discord does not notify on one — so
a wait that lands on a person says so out loud:

```
<@a> <@b>, hit **Ready** and the match starts.        [Ready]
<@smol>, your **ban**.
Round 2 in 5 minutes. Hit **Ready** to go sooner.     [Ready]
```

One line each. No countdown on the turn line, no ready marks, no repeat of what
was just banned — the board has all of it. **Not every wait gets one**: an open
window already has its reveal beat. The break gets one but **no ping**, because
the result beat lands at the same instant and has already pinged everybody.

**No prompt is left standing as an unanswered ask.** When its wait ends the
message is settled, and `prompts.resolved` decides how:

| Wait | Ends as |
|---|---|
| `turn:{i}` | **rewritten into what happened** — `**Smol-Don** banned **Grievous Lady** FTR 11 (11.4)`, or `(timed out)` on an auto-act |
| `start`, `break:{n}` | **deleted** — what they carried was a button and a countdown, and neither has a true form once the wait is over |

Components come off either way: a button that no longer works is worse than no
button, and the line it sat on is now a statement. A pick or a ban is a fact the
thread wants to keep, so rewriting the line that asked for it costs no message
and leaves the pick/ban phase reading as the log it always wanted to be:

```
**Smol-Don** banned **Grievous Lady** FTR 11 (11.4)
**Marut** banned **Fracture Ray** FTR 11 (11.5) (timed out)
**Marut** picked **Testify** FTR 11+ (11.9)
**Smol-Don** picked **Pentiment** FTR 10+ (10.9)
```

A start or break line resolves to nothing worth a sentence — the turn line and
the reveal beat follow within seconds and say it better — so those simply go.

Which action a `turn:{i}` line reports is found by **when it happened**, never by
pool order (that is the board's order): turns are strictly sequential, so the
nth action *is* turn n. The decider is excluded for free — it is assigned rather
than acted, so it carries no `acted_at`.

**A prompt is keyed by its wait, never by having witnessed a transition** — the
same property that makes beats restart-safe. `prompts.current(view)` returns the
wait (`start`, `turn:{index}`, `break:{ordinal}`, or nothing) and `board.refresh`
compares it against `tournament_matches.prompt_key`, saying nothing at all while
it is unchanged. That is what makes it safe on every tick and after every click,
and why a restart mid-match says nothing twice. The key is stored only once the
message has landed, so a failed post is still owed on the next pass.

Beats are posted **before** boards are redrawn, so a break can never invite the
next round in the message above the one saying who won the last.

**A result beat names the difficulty in song mode**, exactly as the board's
result row does — the two sides pick their own class there, so `9'207'427` and
`9'786'458` may not be comparable at all and the bare numbers say nothing. It
also puts the **winner's score first**, which the board has no reason to do and
this sentence does: *"Yaboytaro takes round 1, 09'786'458 on FTR to 09'207'427
on FTR"* reads as Yaboytaro having scored the first number. A draw keeps the
board's side order, having no winner to lead with.

> [!info] Placement was tried three ways, 2026-09-04
> Controls on the board alone: players missed them. Every wait carrying its own
> control *and* its own countdown: the thread became unreadable. What was
> actually wrong was **notification**, not placement — so the split above is by
> what a control is *about*, and everything a message would duplicate from the
> board was cut.

## Configuration

### First: stop waiting, rather than tuning the wait

The instinct to make timers configurable is the wrong instinct here. **Every
wait ends early when the thing it waits for has happened; the timeout is only
the backstop for a human who does not act.** That is decision 10's early
`open → grace` exit ("all participants scored, so stop waiting") generalised:

| Wait | Ends early on | Backstop |
|---|---|---|
| Match start | everyone Ready — button, or a word in the thread | **none**: cancel it |
| Pick/ban turn | the player acting | auto-act at random |
| Round `open` | all scored, under `first` | `end_ms` |
| Round `grace` | all scored, under `first` | `end_ms + grace_ms` |
| Break between rounds | everyone Ready — button, or a word in the thread | `BREAK_SECONDS` |
| Match start (async formats) | everyone Ready — the **instant start** button | the play-by deadline, then forfeit |

`Ready` is **one primitive**, not four: a per-participant flag, cleared whenever
a new wait begins, serving the match-start gate, the break skip and the instant
start alike. It has **two surfaces** — the button, and a word typed in the
thread (`ready`, `r`, `gg`, `go`, `next`, `+`, …), matched whole so *"ready in a
sec"* and *"gg ez"* do not count. Both are accepted only while drafting or
during a break: outside those there is nothing to be ready for, and a flag set
mid-window would survive into the next break and skip a rest nobody asked to
skip. The window check runs on the *click*, not on whether a button was
rendered — a retired prompt does not recall a click already in flight.

So **turn, break and grace lengths are constants in code**, beside
`DEAD_END_TTL` in `utils/render.py` and `LIVE_WIDTH` in
`chardle/imaging/encode.py`. A tunable timeout is what you build when you cannot
end the wait early, and it is a worse answer to the same problem.

One consequence worth stating: "never wait on a human" is scoped to *inside* a
match. Once a match starts, nothing waits on a person. Whether an **async** match
starts at all does — that is what async means — so those carry a play-by
deadline, and a single no-show forfeits while a double no-show stalls for the
organizer rather than silently emptying a branch of the bracket.

### What is actually configurable: the format

| Choice | Where it is made |
|---|---|
| Format — bracket, double-elim, round robin, lobby | `/tournament create`, a deliberate form |
| `pick_ban` on/off, `best_of`, pool filters | that form, or `/tournament quick` |
| Home channel | `/tournament channel`, a table (it carries `set_by`) |
| Timer lengths | **nowhere — constants** |
| Roster cap | **nowhere — there isn't one**; the board truncates rows instead |

**Configuration lives where the choice is already being deliberate.** A quick
match must be one option long, so its format is fixed and its two gaps are
filled by guild defaults. Creating a tournament is already a deliberate act with
a form in front of it, so it carries the full format spec there and needs no
guild defaults at all. The tier is not a property of the value — it is a
property of how much attention the user is already paying.

> [!warning] Superseded at build time, 2026-09-02
> This became **four** keys, not two, and `tournament_default_class` is not one
> of them — see the delta table at the top. `bans`, `best_of` and `visibility`
> joined `level`; the difficulty class became a **required** option because
> `ftr` versus `any` decides whether the match is competitive or casual, which
> is not a thing to inherit silently from a server setting.

The keys are `tournament_default_level`, `tournament_default_bans`,
`tournament_default_best_of` and `tournament_default_visibility`, all existing
solely so that `/tournament quick with:@bob class:ftr` stays short after a
one-time guild setup. None is `USER`-writable: a match is shared state, and a
per-user default would mean two players in one match believe different rules
apply while the board can only draw one of them.

Two rules bound the rest:

- **Anything that changes how you play is printed on the board**, and anything
  not on the board must not change how you play. With formats this matters more
  than it did with timers: the board states the format, the stage, and what a
  point means.
- **A derived value never gets its own option.** Pool size is a function of
  `best_of` **and whether the match bans** — head-to-head with bans it is
  `2 + (best_of - 1) + 1`, and without them it is `best_of`, because nothing is
  thrown away; bracket size is a function of the entrant count. Offering any of
  them lets someone configure a Bo5 with a three-chart pool.

## Traps

| Case | Handling |
|---|---|
| Ties | Earlier `time_played` wins on every tier |
| Shared Arcaea accounts | Roster entries are `ArcaeaAccount`, not `discord_id` — reject a duplicate `arcaea_account_id` at signup |
| Credential-only participants (no friend link) | In nobody's `/friend/me` → own request per cycle. Ensure a friend link exists at signup for score rounds (a one-time placement, not a move) |
| Non-participants in the payload | `/friend/me` returns everyone on the account — filter for the round but **still ingest the rest** |
| Concurrent rounds sharing a chart | One play can satisfy two rounds. Harmless, but decide it rather than discover it |
| `byd_2` | Free — resolution happens in ingest before the tournament layer sees a row; comparing resolved chart IDs just works. See [[score-mapping\|Score Mapping]] and [[d-byd2-game-song-id-resolution|the `game_song_id` trap]] |
| Participant never plays | Resolves to "no score" at deadline; never blocks the state machine |
| Filters that cannot fill a pool | Refused at `/tournament quick`, before a thread is opened. A shortfall found later (the catalog moved) is posted **in the thread** and clears every Ready — never ephemerally to the last clicker, who is not the only person waiting |

**Song ownership is out of scope as a validity or ranking input, and always
will be.** `pack_id` and `Song.world_unlock` do **not** determine whether a song
is free/owned for a given player (owner decision, 2026-07-17) — a correct model
needs a manual per-player list that does not exist yet. See
[[ownership-worksheet-2026-09-03]] for what a correct model looks like, measured
and answered — it supersedes [[handoff-11-ownership-blob|the ownership-blob
sketch]] (handoff 11), whose premise that no such data exists is wrong.

> [!note] Narrowed by the second pass: it returns as a *pool* filter
> A generated pool filters on level, difficulty class, and **owned by every
> participant** (owner, 2026-09-02). That last filter is a no-op today and stays
> one until the ownership blob exists. It does not weaken the rule above: it
> decides which charts are *offered*, never whether a played score counts or how
> it ranks. Those remain decided by set membership and the window, and nothing
> else.
>
> **Built as always-on, with no option** (owner, 2026-09-02): a player cannot
> play a chart they do not own, so this is a property of a valid pool rather
> than a preference. `pool.owned_by_all` is on the pipeline returning its input
> unchanged, so the day the blob lands, one function body changes and no caller
> does.

> [!note] Confirmed and unblocked 2026-09-03 — the data exists
> The stub is no longer waiting on a blob that may never be built. Asked directly
> whether the pool filter wants a per-player playable set, the owner's answer was
> **yes — intersect the roster's playable sets, exactly as the stub promises**
> (owner, 2026-09-03). And the input largely exists already: `/webapi/user/me`
> derives song-grain ownership **exactly** for every credentialed (t2/t3) player,
> with no declaration at all. See [[ownership-worksheet-2026-09-03]] and
> [[catalog|Catalog]] §Ownership.
>
> Two things the filter must respect when it stops being a no-op:
>
> - **Absence is never a denial.** Neither `packs` nor `world_songs` may be read as
>   "cannot play" — pack ownership is sufficient but not necessary, and
>   `world_songs` is a positive signal only. A filter that treats unknown as
>   unowned will silently strip charts every participant can play.
> - **Beyond is the exception, and it is large.** 66 of 67 Beyond charts carry an
>   unlock condition that no signal reports negatively, so a Beyond's playability
>   comes from a declaration plus `has_score`, not from ownership. Eternal needs
>   nothing: `playable(etr) = playable(song)`, and pools may draw Eternal freely
>   (owner, 2026-09-03).
>
> The rule above is unchanged: this decides which charts are *offered*, never
> whether a played score counts or how it ranks.

> [!note] Built 2026-09-06 — `owned_by_all` is no longer a no-op
> It intersects the roster's playable sets from the `/owned` declaration
> ([[ownership-module|ownership]]), unioned with `has_score`, and filters the
> chart list on the result. Three things to know before reading a pool:
>
> - **An undeclared participant is skipped, not treated as owning nothing** —
>   [[h-absent-declaration-is-unconstrained]]. Precision rises with adoption
>   instead of gating on it, and a roster where nobody has declared draws exactly
>   as it did before.
> - **The filter lives inside `qualifying`, not at its call site.** In song mode a
>   song enters the pool because *one* of its charts is playable, and the round's
>   chart set is rebuilt by a second call from `match.py::_write_chart_set` —
>   which would otherwise admit the whole song, Beyond included.
> - **Beyond is only playable once declared on the `/owned` Beyond page** (or
>   proven by `has_score`). A pack tick never grants it, so pools skew away from
>   Beyond until players answer that page. That is the intended direction: a pool
>   missing a chart costs one option, a pool containing an unplayable one costs
>   the match.

## Source

[[handoff-13-tournaments|Handoff 13]] (the match and below — build first) and
[[handoff-14-tournament-formats|handoff 14]] (the formats layer) are the current
spec and outrank both this page and the source below: schema, module layout,
state tables, the Discord surface, the board contracts and the config keys all
live there.

[[arcaea-tournament-layer]] — the first pass, more detailed than
this page on scoring. Filed as [[arcaea-tournament-layer]]. Status 2026-07-17: **design
only, nothing built.** Its scoring-rule *parameter* is retired
([[h-first-score-is-the-only-rule]]); the one
genuinely open item is `time_played` trust, and that is resolved (§2 above —
verified against `arcaea-auth-behavior.md` §7.3, so it is not actually open,
just worth restating as the whole integrity model).

Depends on [[score-poll-loop|Score Poll Loop]] (built, Tier 2) for its one integration point
(the hot-cadence query) and on the [[db]] `play_scores` table (built) for its
only data source.

## Deferred after the 2026-09-03 spot check

Two of these are owner rulings that change policy on this page, not just code:
[[h-tournament-window-and-clock]] (the 5-minute window above, plus the fact that
nothing announces an open round) and [[h-tournament-untracked-participants]]
(tracking must **not** gate a match). The other four are
[[h-tournament-sticky-board]], [[h-tournament-one-match-per-thread]],
[[h-tournament-pool-sizing]] and [[h-tournament-spot-check-leftovers]].
