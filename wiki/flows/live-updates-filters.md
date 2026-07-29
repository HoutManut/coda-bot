---
type: flow
status: active
entrypoint: "poster routing step 5 (filters.py) / storage on live_update_prefs, live_update_channels"
touches: [scores (filters), players (live.py), db (live_update_prefs, live_update_channels)]
created: 2026-07-29
updated: 2026-07-29
verified: 2026-07-28
grade: A
tags: [flow, live-updates, score-tracking, filters]
aliases: ["Live Updates Filters", "Live Updates — Filters"]
---

# Live Updates — Filters

Split out of [[live-updates|Live Updates (poster)]] 2026-07-29 (that page had grown past the
vault's 300-line soft threshold — see `meta/lint-report-2026-07-29.md`). Covers the trigger/gate
filter algebra and the storage columns that hold it. Poster routing/send mechanics live in
[[live-updates-poster|Live Updates — Poster]]; `/recent` duplicate suppression lives in
[[live-updates-suppression|Live Updates — Suppression]].

---

## Filters

### Triggers (OR)

A play is a candidate if **any** enabled trigger fires.

| Trigger | Fires when | Path |
|---|---|---|
| `all` | always | both |
| `pb` | strictly beats the account's best observed score on that chart | both |
| `bX` | `pb` **and** the chart's post-play rank ≤ X in the full ranking | both, resolved charts only |
| `pm` | `score >= PURE_MEMORY` (`utils/scoring.py:12`) | both |
| `fr` | `lost_count == 0` | **own only** |
| `grade_up` | the play's grade beats the previous best grade on that chart, and is ≥ the user's chosen floor grade | both |

Constraints that must survive into the implementation:

- **`pm` is score-derivable.** A Pure Memory is exactly `score >= 10_000_000`;
  no note counts needed, so it works identically on the friend path.
  `embed.py:109` already relies on this.
- **`fr` is own-path only** and cannot be made symmetric — the friend payload
  carries no `lost_count`. A friend-tier user who enables `fr` gets nothing,
  forever. Stated in the option's description (below), never discovered as silence.
- **`fr` is a superset of `pm`.** Every PM is also a full recall; enabling `fr`
  alone already posts PMs.
- **`bX` implies `pb`.** A play that does not beat the chart's best cannot move
  the ranking, which is built from best-per-chart (`b30.py:130-152`). Evaluate
  `pb` once and reuse. `rank ≤ X && pb` is exactly "raised your top-X sum".
- **`grade_up` implies `pb`** for the same reason — grade is monotone in score,
  so a higher grade needs a higher score.
- **PB is strict `>`.** An equal score is a distinct row under `uq_play_identity`
  (different `time_played`) but is not a new achievement.

### `grade_up` in detail

Grades in play: **AA** (`9_500_000`), **EX** (`9_800_000`), **EX+**
(`9_900_000`) — constants already exist at `utils/scoring.py:14-16`. Lower grades
are deliberately not offered.

The user picks a floor: `off | AA | EX | EX+`. The trigger fires when

```
grade(this score) > grade(previous best observed score on that chart)
AND grade(this score) >= chosen floor
```

So picking AA notifies on AA, EX and EX+ crossings; picking EX+ notifies only on
EX+ crossings. No previous play on the chart → previous grade is none → any play
at or above the floor fires. It never repeats on a chart, which is what makes it
a milestone rather than a running commentary — "any play at ≥ EX" would fire on
nearly every play a strong player makes and would swamp `pb` under OR.

Cost: **free**. The `pb` query already fetches the previous best score, and grade
is a pure function of score.

Needs one small addition: an ordered `Grade` in `utils/scoring.py` (enum +
`grade_of(score)`), since only bare score constants exist today. Store the user's
floor as that ordinal, not as a score threshold.

### Gates (AND)

Every enabled gate must pass, or nothing posts regardless of triggers.

| Gate | Set by | Passes when |
|---|---|---|
| `min_level` | the user | `song_difficulty.level >= min_level` |
| channel floor | a guild admin | see §The guild floor |

`level` is stored encoded, ×2 with +1 for a `+` suffix (`difficulty.py:38-39`),
so "10+ and above" is `min_level = 21`. Use `encode_level`/`decode_level`
(`utils/encoding.py:11,20`) at the command boundary; store and compare encoded.

**Why triggers and gates are different.** OR-ing everything makes "10+ only" a
*reason to post*, so a level-3 PM still posts — not what the phrase means.
AND-ing everything makes `pb` + `pm` mean "a PB that is also a PM", so selecting
two triggers usually produces silence. Triggers answer "is this worth telling
someone about"; gates answer "do I care about this chart at all". Keeping them
separate is also what makes the guild floor cheap: a floor is just more gates,
and gates compose by AND with no ambiguity.

### Evaluation order

Cheapest first, short-circuiting, per (play, linked user):

1. **Gates** — `min_level` and the channel floor need only the already-loaded
   chart row. A failed gate ends evaluation with zero queries.
2. `all` → candidate immediately.
3. `pm`, `fr` → in-memory field comparisons, free.
4. `pb` → one query, covered by the existing
   `ix_play_scores_account_chart_score` index (`play_score.py:52-58`). Returns
   the previous best score, which also settles `grade_up`.
5. `bX` → only if `pb` is true. `B30Service.compute(...)`, one scan of the
   account's rows.

Account-level facts (`is_pb`, `previous_grade`, `rank`) are computed lazily
**once per play** and shared across every linked user, so two users linking one
account never pay twice.

### The guild floor

A guild admin can raise the bar for its own allowlisted channels — **gates only**,
never triggers:

- `min_level` and `min_grade` columns on `live_update_channels`.
- Applied only when the destination is a channel. **DMs are never floored** —
  a user's own inbox is not a guild's business.
- AND-ed with the user's own gates; the effective bar is the stricter of the two.
- Not extended to triggers: intersecting two trigger sets can silently void a
  user's whole selection, and gates already deliver the "keep this channel for
  serious plays" intent.
- **Must be visible.** `/liveupdates status` shows the floor on the user's
  destination channel, so an unexplained silence is always explicable.

Loaded by a new `LiveUpdateService.floor_for(db, channel_id)` rather than by
widening `resolve_destination`'s return — one extra indexed read per channel post
is nothing at this scale, and the resolver's signature stays the poller's
entry point.

A de-allowlisted channel falls back to DM inside `resolve_destination`
(`live.py:129-136`), at which point the floor stops applying. Correct by
construction, no cleanup pass.

### Unresolved charts

A play whose `song_difficulty_id IS NULL` (a song shipped in-game before a
catalog seed — routine) behaves as follows:

| Filter | Behavior | Why |
|---|---|---|
| `pb` | evaluates, keyed on `(wire_song_id, wire_difficulty)` | wire identity is always present |
| `pm`, `fr`, `grade_up` | evaluate | score / `lost_count` alone |
| `bX` | **cannot fire** | no CC → no play rating → no rank. Not a policy choice |
| `min_level`, channel floor level | **fail closed** — block the post | policy choice, see below |

Fail-closed is a decision, not a consequence. Fail-open ("the bot's ignorance
shouldn't silence you") would void the gate on exactly the charts most likely to
be new and high-level. The cost is real and accepted: `reconcile` resolves the
chart later, but the post has already been skipped and `ingest` never re-offers
the play. **The one filter behavior worth revisiting after real use** — it is a
one-line flip.

---

## Storage

Columns on the existing `live_update_prefs`:

```
live_update_prefs (existing: discord_id PK, channel_id, enabled, updated_at)
+ post_all    BOOL     NOT NULL  server_default false
+ post_pb     BOOL     NOT NULL  server_default true
+ post_pm     BOOL     NOT NULL  server_default false
+ post_fr     BOOL     NOT NULL  server_default false
+ best_of     SMALLINT NULL      -- bX trigger; NULL = off
+ min_grade   SMALLINT NULL      -- grade_up floor, Grade ordinal; NULL = off
+ min_level   SMALLINT NULL      -- encoded level gate; NULL = off

live_update_channels
+ min_level   SMALLINT NULL      -- guild floor; NULL = none
+ min_grade   SMALLINT NULL      -- guild floor; NULL = none
```

Reasoning:

- **Not `REGISTRY`.** `ConfigKey.type` is either an enum tuple or one of
  `"str" | "bool" | "int"` (`settings/types.py:21`). A combinable set plus three
  numbers only fits as a hand-parsed CSV string, which forfeits Discord's own
  option validation and fails at post time instead of at set time.
- **Not a separate table.** The rows are 1:1 with `live_update_prefs` and
  meaningless without one. `resolve_destination` already loads that row
  (`live.py:122`), so the filters arrive in the same query at zero extra I/O per
  play. A second table buys a second query and a missing-row case for nothing.
- **Defaults carry the decision.** `post_pb` server-defaults true, so the
  migration gives every already-enabled user `pb` and `LiveUpdateService._upsert`
  needs no new code.

**Fix while in there:** `LiveUpdatePref.enabled` carries `default=True,
server_default="true"` (`live_update.py:51-53`), contradicting
`DEFAULT_ENABLED = False`. Harmless today only because `_upsert` passes `enabled`
explicitly (`live.py:142`). Align the server default to false in the same
migration.

---

## Related

[[live-updates|Live Updates (poster)]] · [[live-updates-poster|Live Updates — Poster]] ·
[[live-updates-suppression|Live Updates — Suppression]] ·
[[h-live-update-post-filters]], [[scores|scores (module)]]
