---
type: domain
status: active
source: arcaea-tournament-layer.md
verified: 2026-07-17
created: 2026-07-21
updated: 2026-07-21
tags: [domain, arcaea, tournaments, unbuilt]
---

# Tournaments

**Status: NOT BUILT.** Design only, nothing implemented as of the source doc
(2026-07-17). This page is the policy layer over score data that already
exists (`play_scores`, filling since the poller landed 2026-07-21 — see
[[db]]). No tournament-specific code, tables, or commands exist in
`src/coda/` today.

## Model

A tournament round is a **chart + a time window**, scored by reading rows the
poller already wrote for an unrelated reason. **The tournament layer never
calls the lowiro API.** It does exactly two things:

1. **Declares hot windows** — tells the poller which accounts to poll faster,
   because a round is open.
2. **Reads `play_scores`**, filtered by chart and time range.

The poller already fetches `/webapi/friend/me` for every friend on a bot
account — participants and non-participants alike, since the endpoint has no
way to request a subset. A round's scores are already arriving in the ingest
stream; a tournament-specific fetch would be a second request for bytes
already received. This makes the module testable by inserting score rows —
no HTTP, no session/`bot_account_id` awareness anywhere in it. See [[Score Poll Loop]].

## Encoding

### Score validity

```
valid(score, round) =
      score.difficulty_id == round.chart_id
  and round.start <= score.time_played <= round.end
```

Must compare `difficulty_id`, not `song_id` — the same song at PST vs FTR is a
different, trivially easier chart, and the wire gives `(song_id, difficulty)`
where both fields must match.

`time_played` is **server-assigned**, UTC milliseconds, at submission — a
moved device clock cannot forge window membership (graded, verified
2026-07-17 against [[arcaea-auth-behavior]] §7.3). This is what makes
"played inside the window" a real guarantee, not an honour system. The only
remaining skew is the bot's clock vs lowiro's server clock — both presumably
NTP-synced; see [[h-tournament-clock-skew]].

**Two windows, not one:**

| Window | Applies to | Range |
|---|---|---|
| Validity | `time_played` | `[start, end]` — never moves |
| Observation | wall clock | `[start, end + grace]` |

Polling is discrete, so a play at `end - 1s` may not be *seen* until after
`end`. Keep polling through the grace period; keep accepting only
`time_played <= end`.

### The window duration

`duration = clamp(2t, 100s, 5m)`, where `t` = song length from
`songs.time`/`song_difficulties.time` (catalog inheritance rule — see
[[db]]). `t = 0` is an unknown sentinel and floors to 100s regardless.

| `t` | Window |
|---|---|
| `0` / unknown | 100s (floor) |
| `60` | 120s |
| `200` | 300s (ceiling bites) |

Polling starts at window **open**, not `start + t` — a hard-gauge loss submits
its score seconds in ([[Scoring]] §5), so a valid score can land almost
immediately.

`2t` is **not** two attempts — real attempt cost is `t + overhead` (song
select, load, results screen; call it 20–40s). At `t=120, D=240, o=30`:
`floor(240/150) = 1` attempt. The 5m ceiling makes attempt budget inconsistent
across rounds (a 100s song gets ~1.3 attempts, a 200s song gets ~1.0); cap on
*attempts* rather than wall-clock if that matters, or accept long songs are
one-shot. See [[h-tournament-attempt-overhead]].

### Scoring rule — a per-tournament parameter

```
scoring_rule: "first" | "best"        DEFAULT: "first"
```

Both ship. `last`-counts is **not** offered (instant exit is arbitrary; nobody
asked for it). See [[h-tournament-scoring-rule-parameter]] for the decision
writeup.

| | `first` (default) | `best` |
|---|---|---|
| Counts | each player's first valid score | each player's highest valid score |
| Retrying | pointless | strictly free |
| Instant exit on all-scored | provably lossless | legitimate, but a rule (denies improvement) |
| The `2t` window is | a forfeit timeout | a real attempt budget |
| Hard-gauge loss | **locks in** ⚠️ | recoverable — just retry |

⚠️ **Under `first`, hard gauge is a trap and the player's own choice.** A
hard-gauge loss submits its score seconds in ([[Scoring]] §5); under `first`
that death is the player's first valid score inside the window, so it counts
and locks in. Normal and easy gauge cannot do this — HP hitting 0 costs
nothing on those gauges, so the play always runs to completion. **Under
`first`, hard gauge is strictly self-harming and normal gauge is strictly
safe** — this is a rule to tell players, not a bug to fix. It cannot be
enforced on tier 1 (`modifier` is own-path only, §7 below) — detectable after
the fact on tier 2+, not preventable.

Under `best`, speed converts into attempts: retrying is free, so everyone
retries until the slowest player posts their first score. Fast players earn
extra tries — state it in the rules.

### State machine

```
DRAFT ──open──> OPEN ──┬── all participants scored ──> GRACE ──> CLOSED
                       └── deadline reached ────────> GRACE ──> CLOSED
  │                        │
  └──cancel──> CANCELLED   └──cancel──> CANCELLED
```

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

## Traps

| Case | Handling |
|---|---|
| Ties | Earlier `time_played` wins on every tier |
| Shared Arcaea accounts | Roster entries are `ArcaeaAccount`, not `discord_id` — reject a duplicate `arcaea_account_id` at signup |
| Credential-only participants (no friend link) | In nobody's `/friend/me` → own request per cycle. Ensure a friend link exists at signup for score rounds (a one-time placement, not a move) |
| Non-participants in the payload | `/friend/me` returns everyone on the account — filter for the round but **still ingest the rest** |
| Concurrent rounds sharing a chart | One play can satisfy two rounds. Harmless, but decide it rather than discover it |
| `byd_2` | Free — resolution happens in ingest before the tournament layer sees a row; comparing resolved chart IDs just works. See [[Score Mapping]] and [[d-byd2-game-song-id-resolution|the `game_song_id` trap]] |
| Participant never plays | Resolves to "no score" at deadline; never blocks the state machine |

**Song ownership is explicitly OUT OF SCOPE.** `pack_id` and `Song.world_unlock`
do **not** determine whether a song is free/owned for a given player (owner
decision, 2026-07-17) — a correct model needs a manual per-player list that
does not exist yet. See [[h-ownership-blob-open-before-building]] and
[[handoff-11-ownership-blob|the ownership-blob sketch]] (handoff 11,
sketch only, not designed) for the closest thing to a plan.

## Source

[[arcaea-tournament-layer]] — authoritative and more detailed than
this page. Filed as [[arcaea-tournament-layer]]. Status 2026-07-17: **design
only, nothing built.** The scoring rule is settled as a parameter; the one
genuinely open item is `time_played` trust, and that is resolved (§2 above —
verified against `arcaea-auth-behavior.md` §7.3, so it is not actually open,
just worth restating as the whole integrity model).

Depends on [[Score Poll Loop]] (built, Tier 2) for its one integration point
(the hot-cadence query) and on the [[db]] `play_scores` table (built) for its
only data source.
