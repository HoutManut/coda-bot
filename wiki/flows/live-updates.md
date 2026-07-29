---
type: flow
status: active
entrypoint: "poller._store -> poster.submit -> poster.run"
touches: [scores (poller/embed/filters/poster/suppression), players (live.py), db (play_scores, live_update_channels, live_update_prefs, player_links)]
created: 2026-07-21
updated: 2026-07-29
verified: 2026-07-28
grade: A
tags: [flow, live-updates, score-tracking, filters]
aliases: ["Live Updates (poster)", "Live Updates"]
---

# Live Updates (poster)

**Status: BUILT** (2026-07-24), to this design. Score tracking is now complete
end to end: poller (both read paths) → storage → chart resolution + reconcile →
`/recent`, b30, and now a Discord message.

This page is the design, settled in a design session on 2026-07-24 and shipped
the same day. It answers the two questions that blocked the work:
[[h-live-update-post-filters]] and [[h-recent-duplicate-suppression]]. §11 (below)
records where the shipped code differs from what was designed.

> [!note] Split 2026-07-29
> This page passed the vault's 300-line soft threshold (`meta/lint-report-2026-07-29.md`)
> and was split into three sub-pages: [[live-updates-filters|Live Updates — Filters]]
> (trigger/gate algebra + storage columns), [[live-updates-poster|Live Updates — Poster]]
> (hand-off, task lifecycle, routing, ordering/stagger, attribution), and
> [[live-updates-suppression|Live Updates — Suppression]] (`/recent` duplicate marker,
> set/check rules). This page keeps the constraining facts, decisions, copy rules, command
> surface, failure modes, and build/settlement history.

> [!info] The opt-in side predates the poster
> A user could already be `enabled=True` with a destination before the poster
> existed: `/liveupdates on|channel`, or the post-registration welcome embed's
> inline button (see [[registration|Registration]]). Those prefs are now read.
> The migration gives every such user `post_pb=true`, so they get personal
> bests and nothing else until they run `/liveupdates filters`.

---

## 1. Facts that constrain the design

Two of these reverse premises the question pages were written on.

**`play_scores` is a sample, not a log.** `/friend/me` and `/user/me` each return
only the *single most recent* play (`poller.py:219`, `poller.py:248`). Plays made
between two polls are never fetched and never can be — the wire exposes no
history. Everything downstream inherits it: a "personal best" is a best *among
observed plays*, a b30 rise is a rise in *observed* b30, and no filter may be
described to users as complete (§7).

**No individual can be flooded; a shared channel can burst.** The unit that
bounds volume is the **player**, not the poll key. One `/friend/me` returns a
play per friend (`poller.py:217-221`), so a bot key can yield many plays at once
— but any one *account* surfaces at most its single latest play per cycle of the
key covering it, deduped across both read paths by `uq_play_identity`. With
`POLL_INTERVAL` at 90 s (`config.py:70`) plus per-key jitter, a user's own feed
tops out near 40 messages/hour and realistically yields far fewer.

A **channel** that K users point at aggregates them, so one cycle can put up to K
posts there. That is real, and it is what the per-destination stagger
([[live-updates-poster|Live Updates — Poster]] §Ordering and stagger) and the guild floor
([[live-updates-filters|Live Updates — Filters]] §The guild floor) exist to handle — not a
reason to restrict what any individual may ask for.

[[h-live-update-post-filters]] frames the whole problem as anti-flood; that
framing is wrong at the level it matters. The real question is *what is worth a
message*, which is a per-user preference, not a bot-wide noise budget.

**`/recent`'s success reply is public.** It calls `await ctx.defer()` with no
`ephemeral` flag (`recent.py:91`), and a deferred response fixes its flags at
defer time. Everyone in the channel sees the play. Only the two pre-defer error
paths are ephemeral.

**`/recent` *causes* the duplicate it is accused of.** It calls
`coordinator.request_refresh(key)` (`recent.py:96`), which drives a real poll
cycle, which ingests the play, which produces the `new_plays` the poster
consumes. Whenever `/recent` surfaces a play the poller had not yet stored, a
live update for that exact play follows. Common case, not corner case. See
[[live-updates-suppression|Live Updates — Suppression]] for the fix.

**"Skip the poster on on-demand cycles" is a trap.** `/recent` targets the OWN key
when the account has a valid credential, otherwise the BOT key holding it
(`recent.py:155-171`). A bot key covers *every friend on that bot account*, so
suppressing a whole on-demand cycle would silently and permanently drop other
players' updates — `ingest` returns a play exactly once, ever
(`service.py:101-107`), so a dropped post is unrecoverable. Suppression must be
scoped to the requester.

**A play can belong to more than one Discord user.** `PlayerLink` is many-to-one
onto `ArcaeaAccount`. Filters and destinations are per *Discord user*, evaluated
once per (play, linked user) pair — while the account-level facts behind them
(is this a PB, previous grade, rank) are computed once per play and reused.

---

## 2. Decisions

| Question | Decision |
|---|---|
| Filter algebra | **Triggers OR-ed, gates AND-ed** over the result |
| Triggers (v1) | `all`, `pb`, `bX`, `pm`, `fr`, `grade_up` |
| Gates (v1) | `min_level` (user), plus a per-channel guild floor |
| Default on first enable | `pb` only |
| Where filters live | **Columns on `live_update_prefs`** — not `REGISTRY`, not a new table |
| Live updates default | unchanged: `DEFAULT_ENABLED = False` (`live.py:26`) |
| `/recent` duplicate | **Suppress**, keyed `(destination, play_score_id)` |
| b30 aggregate in a post | **Never printed.** Filter input only |
| Unresolved chart vs a level gate | **Fail closed** — no level known, no post |

Full detail on each: [[live-updates-filters|Live Updates — Filters]] (filters + storage),
[[live-updates-poster|Live Updates — Poster]] (poster mechanics),
[[live-updates-suppression|Live Updates — Suppression]] (`/recent` dedup).

---

## 7. Copy rules (non-negotiable)

- **Never promise completeness.** Not "every PB", but "personal bests I see".
  `/liveupdates status` carries one plain line: the bot checks every few minutes
  and only ever sees your latest play, so some plays are never seen (§1).
- **`fr`'s description says it needs an own login.** A friend-tier user enabling
  it must learn that from the command, not from silence.
- **A guild floor on the user's destination is shown in `/liveupdates status`.**
  A gate someone else set must never be an unexplained silence.
- **The b30 aggregate is never printed in a live post** — filter input only. This
  sidesteps the hidden-player leak entirely: a player who hides their PTT must
  not have our estimate of their standing posted to a channel. The **per-chart**
  play-rating line stays (`embed.py:93`) — it is derivable from a public score
  plus a public CC and is not the aggregate. See [[potential|Potential]].

---

## 8. Command surface

Extend `src/coda/extensions/liveupdates.py` (existing: `allow`, `disallow`,
`channel`, `on`, `off`, `status`).

**`/liveupdates filters`** — every option optional; omitted means unchanged;
invoked with no options at all, it shows the current set instead of writing.

| Option | Type | Notes |
|---|---|---|
| `all` | bool | Every play I see |
| `pb` | bool | Personal bests |
| `pm` | bool | Pure Memory |
| `fr` | bool | Full Recall — **own-login accounts only** |
| `grade_up` | choice | `off` / `AA` / `EX` / `EX+` — first time reaching that grade on a chart |
| `best_of` | int 1–100 | Plays that land in your top X. `0` = off |
| `min_level` | choice | `off`, `9`, `9+`, `10`, `10+`, `11`, … → `encode_level` |

**`/liveupdates floor`** — admin only (`_is_admin`, `liveupdates.py:71`), sets
`min_level` / `min_grade` on one allowlisted channel of the invoking guild.

Discord's own option types do the validation, which is the whole reason this is
not in `REGISTRY` — see [[live-updates-filters|Live Updates — Filters]] §Storage.

---

## 9. Failure modes

| Failure | Surfaces at | Result |
|---|---|---|
| DMs closed / bot blocked | `send_dm` | Returns `None`, already logged. One post dropped, task unaffected |
| Channel deleted, or send perms lost | `create_message` | try/except per post; log and move on. Never crash the task, never block other destinations |
| Channel de-allowlisted | `resolve_destination` | Already falls back to DM (`live.py:129-136`); the guild floor stops applying with it |
| Account with no `PlayerLink` | poster routing | Silent skip — nobody to notify |
| Discord identity unresolvable (no owner link, or fetch fails) | poster author line | Degrades to the Arcaea in-game name, then to no author line. Never blocks or drops the post |
| Friend-path play (thin data) | embed | Renders from wire identity + score; the pure/far/lost line is omitted entirely, never partially (`embed.py:94-95`) |
| Unresolved chart | embed | Falls back to the raw wire id + difficulty colour with a note (`embed.py:33`). Still posts — unless a level gate is set (see [[live-updates-filters|Live Updates — Filters]] §Unresolved charts) |
| Poster wedged | `put_nowait` | Queue fills, plays dropped with a log. Poll loop never blocks |
| Restart mid-window | — | Queued plays are lost (already ingested, never re-offered); suppression markers reset |

---

## 10. Out of scope for v1

- **Per-destination filters** ("everything to my DM, only b30 to the channel").
  One destination per user exists today; this implies multi-destination support.
- **Clear-type triggers** (hard clear, first clear). Own-path only, and
  `clear_type` deserves its own pass.
- **Guild trigger overrides.** Gates only — see
  [[live-updates-filters|Live Updates — Filters]] §The guild floor.
- **The "+0.0x b30" delta in the embed.** Forbidden by §7 for hidden players and
  not worth a per-player conditional yet. `B30Service.compute`'s
  `exclude_score_id` (`b30.py:84`) already supports it whenever that changes.
- **Backfill** of unobserved plays. Impossible on the wire — see
  [[h-backfill-worth-building]].

---

## 11. What shipped

Migration `7ac31e9b0d54`. New modules `scores/filters.py`, `scores/poster.py`,
`scores/suppression.py`; tests in `tests/test_live_filters.py` and
`tests/test_post_suppression.py`.

Five places where the code is more specific than the design above:

- **`ingest` returns `list[int]`, not `ScoreResult`s**, and `_upsert`'s own
  branch returns `(id, xmax = 0)` rather than the flag alone. `_store` **sorts
  `resolved` by `time_played` before ingest**, not after — `ingest` preserves
  input order, so the returned ids come out time-ordered for free and
  [[live-updates-poster|Live Updates — Poster]] §Ordering and stagger's ordering
  requirement needs no correlation step.
- **`INITIAL_DELAY` is per drained batch, not per play**, and **planning stays
  in the consumer loop** — only the sends become tasks. Both exist for the same
  reason: a FIFO lock orders whoever is *already waiting on it*, it does not
  reconstruct creation order. Per-play jitter, or planning concurrently (it is
  several awaits deep — two DB reads per linked user, plus the PB query and a
  b30 scan), would let two plays reach a shared channel's lock in whichever
  order happened to finish first. Planned in sequence, the send tasks are
  created in play order and take an uncontended lock without yielding, so the
  waiter queue preserves it.
- **`floor_for` returns a `ChannelFloor` carrying `guild_id`**, which is what
  resolves `timezone` at guild scope below at no extra query.
- **`PostSuppressor` lives in its own module** (`scores/suppression.py`), so
  `extensions/recent.py` writes to it without importing the poster. Registered
  for DI *and* handed to the background task, the same dual wiring
  `ObservationCache` has.
- **A missing `live_update_prefs` row falls back to `pb` only**
  (`poster._DEFAULT_FILTERS`), matching the column defaults.

---

## 12. Settled during the build

- **Locale and `night` for a channel post** — settled as
  [[live-updates-poster|Live Updates — Poster]] §Routing implied, then
  **reversed 2026-07-28**: the `locale` REGISTRY key is gone (Discord's
  `interaction.locale` already carries the invoking user's language, so every
  command path reads it off the interaction). A post nobody asked for has no
  interaction to read and a channel post has no single viewer, so the poster
  renders **English**, alone among the render paths. Remembering a user's locale
  from their last interaction would serve the DM destination — worth building
  the day one exists (every enabled `live_update_prefs` row points at a channel
  today). `night`
  passes the recipient for a DM and `0` for a channel — `is_night` ignores the
  argument today (`jackets.py:44`), and the seam stays for a future
  `/timezone`.

## Still open

- **`min_level` fail-closed on unresolved charts** (see
  [[live-updates-filters|Live Updates — Filters]] §Unresolved charts). Shipped
  fail-closed; revisit with real use. One-line flip in
  `filters._level_gate_passes`.
- **Whether `all` earns its place**, given §7's sampling caveat makes it a
  sampled feed rather than a record. Kept — it is one boolean.

## Related

[[live-updates-filters|Live Updates — Filters]] · [[live-updates-poster|Live Updates — Poster]] ·
[[live-updates-suppression|Live Updates — Suppression]] ·
[[scores|scores (module)]], [[score-poll-loop|Score Poll Loop]],
[[chart-resolution|Chart Resolution]], [[db]] (`play_scores`, `player_links`,
`live_update_channels`, `live_update_prefs`), [[b30]] (feeds `bX`),
[[registration|Registration]], [[h-live-update-post-filters]],
[[h-recent-duplicate-suppression]], [[handoff-08-live-updates-poster]] (source)
