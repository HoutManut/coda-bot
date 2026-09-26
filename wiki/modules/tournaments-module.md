---
type: module
status: active
path: src/coda/tournaments/
purpose: Runs matches over scores the poller already collected — pool generation, pick/ban, windows, ranking, the thread, and the board.
depends_on: [scores, catalog, settings, db]
used_by: [extensions, scores]
created: 2026-09-02
updated: 2026-09-06
verified: 2026-09-03
grade: A
tags: [module, tournaments]
aliases: ["tournaments (module)"]
---

# tournaments

## Purpose

`tournaments/` is a **policy layer over `play_scores`**. It never calls the
lowiro API: it declares which accounts are hot and reads rows the poller wrote
for an unrelated reason. That is what makes the whole module testable by
inserting scores — see `tests/test_tournament_lifecycle.py`, which plays a
match from draft to closed with no HTTP anywhere.

Built 2026-09-02, implementing [[handoff-13-tournaments|handoff 13]]. The
formats layer ([[handoff-14-tournament-formats|handoff 14]]) is **not** built:
`scheduled`, `play_by_ms`, `stage_label`, `tournament_id` and `admin_gated`
exist as columns and no code path reaches them.

## Layout

| File | Holds |
|---|---|
| `levels.py` | `LevelRange` + `parse_level_range`. Pure |
| `pickban.py` | the sequence, whose turn, `pool_size`, random auto-act. Pure |
| `pool.py` | pool generation from filters; song-mode collapse; the ownership stub |
| `results.py` | the standings query and the ranking rules |
| `cadence.py` | the hot-key query — the module's one output to the poller |
| `match.py` | match CRUD, roster, pool writes, transitions, round spawning |
| `service.py` | round transitions, `phase_of`, `tick()`, the sweep body |
| `constants.py` | turn / window / grace / break / tick lengths |
| `announce.py` | the two beats a round says in its thread. Text only |
| `prompts.py` | the line a new wait posts + its Ready button, and what the line becomes once the wait ends |
| `defaults.py` | resolves an omitted `/tournament quick` option, in one place |
| `options.py` | the best-of / visibility tables. A leaf, so `settings/registry.py` can read them |
| `views.py` | `MatchView` and friends — frozen dataclasses, no I/O |
| `viewbuild.py` | DB → `MatchView` |
| `render.py` | `MatchView` → `Rendered`. Text today. Owns the pick/ban menu and the clocks |
| `threads.py` | the home-channel and crew-thread tables |
| `transport.py` | thread resolve/reuse/open. REST only, no DB |
| `board.py` | the board, the prompt and the beats — the only file that posts |

`extensions/tournament.py` is the only lightbulb-aware file. Its components use
a stateless `tourney:<action>:<id>` contract dispatched by one listener, where
the id is whatever the action is about — a match for `act`/`ready`, a channel
for `home` (the "Use this channel" button on `/tournament channel`, offered
only when none is set, only outside a thread, and only to someone who could use
it — then re-checked on click, because a button is an offer and never proof).

## Invariants

- **`hikari` appears only in `render.py`, `transport.py` and `board.py`.** The
  same edge split `chardle/` draws.
- **No `bot_account_id` anywhere.** `cadence.hot_keys` returns opaque
  `PollKey`s via `scores/routing.py`, so [[w-sid-confined-to-sessions]] holds
  even though the handoff's own SQL selected the column directly.
- **Membership is on the resolved `song_difficulty_id`.** `tournament_charts`
  holds catalog ids, never wire ids, so `byd_2` is free.
- **Ranking reads five columns and joins no CC.** Decisions 5 and 6 are
  structural: there is nothing in scope to weight a play by.
- **Every transition is recomputable from the DB.** Nothing lives in memory,
  which is why every board component id is stateless — and why an owed beat is a
  NULL stamp on the round rather than something the sweep remembers having seen.
- **The board is edited; a beat is a new message.** Discord does not notify on an
  edit, so state goes in the board and *moments* go in `announce.py`. `board.say`
  takes no lock (a beat is an append) and reports whether the message landed,
  because a beat is stamped only once it has.
- **The window opens at the same instant the chart is named.** That is what lets it
  need no announcement of its own, and what stops a chart picked for a later round
  being banked against an earlier one. See [[h-tournament-window-and-clock]].
- **`discord_id` is on `player_links`, never on the account.** Many Discord users may
  share one Arcaea account; `is_owner` marks the single link that speaks for it. Wiring
  a mention to `ArcaeaAccount.discord_id` — a column that does not exist — is what broke
  `/tournament quick` on 2026-09-03, and `tests/test_tournament_lifecycle.py::TestViewBuild`
  now exercises `viewbuild.build` against the real schema because every other test built
  a `Side` by hand.
- **A roster change posts a line; a round's beat is stamped.** `announce.joined`
  / `announce.left` report a command that just ran, so they are unstamped and
  unowed — there is nothing for the sweep to re-derive. The start prompt is keyed
  `start:<roster size>` so a join retires the stale Ready button and re-asks
  everyone, which is what makes `clear_ready` on join visible rather than silent.
- **The board names a chart by its EFFECTIVE name, not `songs.name_en`.**
  `viewbuild._chart_ref` reads through `catalog.resolution.effective`, and
  `ChartRef` carries `alt` so an Inscribed Beyond renders `INS` rather than
  `BYD`. A Beyond chart with its own name is a different chart to a player, and
  "Pragmatism BYD" does not name the chart the pool is asking them to play.
- **The board calls people by their DISCORD name.** `Side.name` is Discord-first with the
  Arcaea name behind it, captured onto the roster row at join time — the members intent is
  off, so the cache cannot be asked later.
- **One definition of where a match is.** `service.phase_of` is read by the board and
  by the chat-line Ready alike, so the button and the words that stand in for it can
  never disagree about whether there is a break to skip.
- **The sweep cannot die and cannot be stalled by one match.** The task carries
  `max_failures=-1` (lightbulb's default of `1` cancels a task *permanently* on
  its first failure) and `tick()` advances each match inside its own SAVEPOINT.
  Nothing else opens a window, closes one, or auto-acts an expired turn, so a
  dead tick is a dead feature — see `TestSweepIsolation`.
- **The three option tables live in `options.py`, not in the picker.** The
  slash-command choices, the `/config` enum and the resolver all read one table
  each; spelling a list out twice is how they drift.
- **`pickban.py` does not know that a round exists.** It owns the *shape* of the
  sequence; `match.py` owns when each turn is asked for. That is the seam that
  let picks be interleaved without touching a pure module.

## Interleaved picks

Changed 2026-09-05, from the CS-style full draft the handoff shipped to the
osu!-style one-pick-per-round — the reasoning is on
[[tournaments#Picks are interleaved, not drafted (owner, 2026-09-05)]]. What it
cost in this module:

| Piece | Change |
|---|---|
| `pickban.py` | **none.** The sequence is still `["ban","ban"] + ["pick"] * (best_of - 1)`, the next turn is still position `turn_index` in it, side is still `index % 2`, and `pool_size` is unchanged |
| `match.act` | after a **pick**, hands the match to `PLAYING` instead of serving the next turn. After a **ban** it serves the next turn as before, which is what keeps the two bans, and then the first pick, back to back |
| `match.turn_owed` | new. "Does the sequence still owe this match a turn" |
| `service._resume_pickban` | new. Re-enters `PICKBAN` once every round is settled, none is pending, **and the rest is spent** — see [[#Rest, then pick]] |
| `service._finished` | now treats an owed turn as a round that does not exist *yet* |
| `service._advance` | collects owed beats in `PICKBAN` too |
| `viewbuild._entry_state` | an `available` entry on a finished match renders `unplayed` |

Three things bite, and each has a test:

1. **A gap between rounds looks exactly like the end of a match** — every round
   closed, none pending. `_finished` closing there ends a Bo3 at 1-0.
2. **`turn_index` is 0 on a match that never picks**, so the sequence alone
   reports a ban owed for every bans-off and 3+ roster match, and none of them
   would ever close. `turn_owed` re-reads the roster rather than trusting state.
3. **The result beat is owed while the match sits in `PICKBAN`.** The tick that
   closes a round is usually the one that hands the next pick back, so a
   `PLAYING`-only beat gate asks a player to pick before the thread has been
   told who won.

The **decider is still derived, never stored** — the entry left neither banned
nor picked. `_close_pickban` now runs on the last pick and spawns its round
*behind* the one that pick just made, which keeps it last in ordinal order.

## Rest, then pick

Changed 2026-09-06, a day after interleaving and because of it. The gap between
rounds is `result → rest → pick → play`; the turn is served on the far side of
the rest, not alongside it. Reasoning and the play-test that forced it are on
[[tournaments#The rest comes before the pick (owner, 2026-09-06)]].

| Piece | Change |
|---|---|
| `service._rest_over` | new. The rest, measured against the round just **closed** rather than the one about to open — between rounds the next one does not exist yet. `_break_over` is now a thin ordinal lookup in front of it |
| `service._last_closed` | new. Which round a rest is timed from |
| `service._resume_pickban` | gated on `_rest_over`. Deliberately does **not** clear Ready |
| `service.phase_of` | takes `turn_owed`, and gained the trailing-rest branch + `_rest` |
| `viewbuild.build` / `_waiting_on_ready` | both pass `turn_owed` |

Three things bite here too:

1. **A rest before an unnamed round is invisible to `phase_of`.** It finds a
   break by looking for a PENDING round, and between rounds there is none — the
   pick that names it has not been served. Without the trailing branch the board
   shows an idle match for five minutes and no Ready is accepted for the one
   wait that has one. The branch is gated on `turn_owed`, never on "nothing
   pending" alone, because a **decided** match looks identical from there and
   would print a countdown to a round nobody will play.
2. **A spent rest is not a break.** A pending round whose predecessor closed
   long ago is exactly the state a match sits in for the seconds between a pick
   and the sweep that opens it. Reporting `break` there posts a second Ready
   prompt counting down to a moment already past — the precise ask this
   ordering exists to delete. `_rest` returns nothing once `now >= ends`, which
   is what that unused `now` argument was always for.
3. **Ready must survive the turn being served.** Clearing it there is the
   obvious hygiene move and it is wrong: those flags are what makes
   `_open_next` fire on the tick *after* the pick. `open_round` clears them, so
   nothing carries into the window.

`_waiting_on_ready` still refuses Ready during `PICKBAN`, which is now correct
rather than a gap — a match holding a turn wants the pick, not a confirmation
of a rest already spent.

## Two things the code does that the handoff did not say

**The board has no debounce.** The handoff specified a per-match lock *plus* a
~5 s debounce coalescing ingest edits. The 5 s sweep already is that bound —
the board cannot be edited faster than a tick however many scores land — and
unlike a debounce, a tick cannot drop the final frame. The **lock survives**:
pick/ban clicks write the same message concurrently with the sweep.

**The crew row is written at roster freeze, not at creation.** The handoff said
"written on create only", which assumed a fixed roster; `/tournament join` can
change one while the match drafts, and the reuse key *is* the roster. So create
*reads* the table and start *upserts* it, binding the thread to the crew that
actually played.

## The hot lane

An open round makes its roster hot. `cadence.hot_keys` is handed to
`poller.run(hot=...)` from `bot.py`, so `scores/` never imports `tournaments/`.

**Controls split by what they are about.** The pick/ban menu is on the board
(its subject is the pool printed above it); both Ready buttons are on the prompt
line that asks for them. Because Discord does not notify on an edit, every new
wait posts one short line (`prompts.py`), keyed by the wait in
`tournament_matches.prompt_key` so it is said exactly once and a restart says
nothing twice. When a wait ends its line is settled rather than left: a turn is
**rewritten into what happened** (`prompts.resolved`), a start or break is
**deleted**, and components come off either way. That is what
`prompt_message_id` is for. See
[[tournaments#What the thread says, and what it asks]].

**A window is 300 s flat** (see [[h-tournament-window-and-clock]]), and under
`first` it usually ends well short of that, on all-scored.

**The cadence is 15 s, not the handoff's 5 s.** `PollSchedule` carries one
scalar interval, `STAGGER` idles 3–12 s *between* keys inside a tick, and
`PollCoordinator`'s refresh budget is 2 per `poll_interval` per key with a
sleeping `spend`. 15 s fits all three; 5 s would need the stagger bypassed and
`_spread` rewritten for two moduli, against an unmeasured rate limit
([[h-real-rate-limit-shape-unknown]]). A window is 300 s, so 15 s resolves the
board and the early `open → grace` exit with room to spare.

Hot keys **skip `_spread`** and are **left out of other keys' phase
comparison**: it compares phases modulo one interval and says nothing across
two. A key that goes hot is **pulled forward**, or its first fast poll would
land after the slow slot it already held ran out.

## Deferred work

Filed by the 2026-09-03 spot check, grouped so each is one session:

| Page | Covers |
|---|---|
| [[h-tournament-window-and-clock]] | **ANSWERED + BUILT 2026-09-03** — flat 300 s window, the break as a rest, and the beats that announce a round |
| [[h-tournament-sticky-board]] | sticky mode, and everything `board.py` / `/tournament board` should absorb with it |
| [[h-tournament-untracked-participants]] | tracking must not gate a match — and why adopting the in-memory path is a persistence decision |
| [[h-tournament-one-match-per-thread]] | a second `/quick` strands the live match already in the thread |
| [[h-tournament-pool-sizing]] | `spec_of` never reads `pick_ban`, so bans-off over-draws and over-refuses |
| [[h-tournament-spot-check-leftovers]] | the residue, and what was fixed on the day |

## Related

[[tournaments|Tournaments]] · [[handoff-13-tournaments|handoff 13]] ·
[[scores|scores (module)]] · [[score-poll-loop|Score Poll Loop]] ·
[[h-score-is-the-only-ranking-value]] · [[h-every-valid-score-counts]]
