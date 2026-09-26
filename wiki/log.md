---
type: meta
title: "Log"
status: active
created: 2026-07-21
updated: 2026-09-06
tags: [meta, log]
aliases: ["Operations Log"]
---

# Operations Log

Append-only. Newest entry at the TOP.

---

## 2026-09-06 — ownership ships, and packs turn out not to be a thing worth storing

`/owned` is built: a pack picker, a Beyond page, and `pool.owned_by_all` finally doing
something. The design changed twice on the way, both times toward less.

The first plan had three tables — `owned_packs`, `owned_songs`, and chart rows later.
The owner cut it to one: *"do we really need to track owned pack? feel like it can just
live in the logic. itll couple our per chart unlock system later"*, then *"in this v1 we
can just add 3-4 ownedchart row when the user pick 1"*. That is design call 8.d in
[[ownership-worksheet-2026-09-03]] reached directly instead of migrated into, and it
dissolves the precedence question a pack row would have created against a per-chart
answer. A pack is now a fan-out at write time and nothing else. A fully-declared account
is ~1 800 rows, which Postgres does not notice.

Dropping the pack table created exactly one new problem — the checkmark has to be
*derived* — and that turned into the module's central invariant: the writer and the
counter must share one predicate, or a whole-pack tick can never read as checked and the
picker looks broken with no error anywhere. See [[ownership-module|ownership]].

Then Beyond. Storing at chart grain made "does a pack tick grant its Beyond?" a
one-predicate decision rather than a schema change, so it got asked properly instead of
defaulted: 66 of 67 Beyonds are gated and the wire reports them positively only, so a
tick that granted them would put unplayable charts in pools. It withholds, and a second
page on the same message asks directly — which the owner accepted on the condition it
stay terse (*"drop the unnessesary subtitle"*). 39 Beyonds live in the 61 pickable packs,
20 more in `base`, so the page is proportional to what was just ticked and is three menus
at worst.

Then the scores got put to work (*"you should really use playscore more. like if i have a
score on tempestissimo then id have to own blackfate"*). `inferred_pack_ids` reads
`play_scores` and settles **25–32 of the 61 packs** on real accounts before anyone is
asked anything — one account's pick list drops from 61 to 29. Exempt are the three packs
that release song-by-song: `base`, `single`, `extend_*`.

A first attempt also skipped `world_unlock` songs inside paid packs, which the owner
corrected: *"world unlock inside paid pack may still need that pack purchase"* — the map
ships **inside** the pack you bought, so `solitarydream` being world-earned still proves
Eternal Core. Checked: every song whose map has a cross-pack prerequisite (`guardina`,
`diein`, `desive`, `acheron`, `chronologia`) is in `single` and exempt already, so the
flag has no job here at all — which also puts the 18 stale rows out of ownership's reach.

That raised the real UX question — *"is there a distint way to show that a pack is
inferred to be owned and cannot be unchecked?"*. Answer: **stop rendering it as a
checkbox**. Discord has no per-option disabled state, so a ticked-but-locked option can be
unticked and snaps back on the next render, which reads as a bug. A whole disabled select
greys out convincingly but cannot be opened, so its contents become unreachable. Inferred
packs now leave the menus entirely and are *named* in the body — counted-only would invite
"which ones?" with nowhere to look.

The owner then caught that the rejected pattern was already shipping: *"the 'leave it in the
menu, ticked, and re-assert on write' currently exists on byd picker"*. True — a Beyond
prefilled from `has_score` was a checkbox that snapped back, exactly the thing being argued
against one page over. `BeyondEntry` now separates `declared` (a claim, retractable) from
`proven` (a play, not), and locking applies to both pages under one rule: **a locked option
never reaches a menu**, because `playable_chart_ids` unions plays in regardless of what the
menu says. On one real account that leaves 8 of 23 Beyonds actually needing an answer.

`base` came off the picker last (*"take base out"*) — it is free, so a tick is noise. But
it could not simply be dropped: that would turn "not asked" into "cannot play" for 64
songs. It is granted with the first write that adds anything, never on merely opening the
command, and its 20 Beyonds are still asked because `base` is in the world-unlock list
like any other pack. 61 packs, three menus of 25/25/11.

**The bug found while wiring it**: unticking a pack cleared only what ticking it granted,
leaving Beyond rows orphaned — invisible to the picker, still counted by the pool filter.
The fix is the asymmetry now written down as the module's invariant: clear over the wide
set, grant over the narrow one. Verified against the live catalog on a throwaway account
before the tests existed, because a symmetric-looking write passes symmetric-looking
tests.

**The owner's catch, mid-build**: *"make sure that chart overrdies apply correctly. field
and byd alts"*. Measured — **53 Beyonds override `version`** and 18 charts override
`name_en`, both of Last's among them. A spoiler check on `Song.version` would have been
wrong for nearly the entire Beyond set, and song-row names would have shown "Last" twice
while losing "Axium Divergence", "overdead." and seven others. The page is built on
`effective()` and `class_full(alt)` throughout.

Two smaller things fell out. `qualifying` now applies ownership itself rather than
leaving it to callers, because song mode re-derives a round's chart set from a second call
in `match.py::_write_chart_set` that would otherwise admit the whole song. And an account
that never declared reads as **unconstrained rather than empty-handed** — the same "absence
is not a denial" rule the wire measurement produced, one level up and applied to our own
table ([[h-absent-declaration-is-unconstrained]]).

Not built, deliberately: any read of `/webapi/user/me`, so a t3 player declares by hand
exactly like a t1 player.

---

## 2026-09-06 — the rest comes before the pick

Yesterday's interleaving served each pick **on the result** and let its 60 s turn run
concurrently with the 300 s rest, both measured from the previous round's close. That
was cheaper in wall clock — the turn fits inside the rest four times over — and wrong in
ordering: it put the gap's last **ask** before the gap's **wait**. A player picked their
chart and then a fresh "hit **Ready** to go sooner" line appeared underneath it.

Play-tested on a third-party player, who picked and then **waited**, expecting to play.
They never pressed it. The overlap was invisible to them; what they saw was pick → still
not playing.

The gap now runs `result → rest → pick → play`, so the pick is the last thing before the
chart is revealed. Two smaller bugs died with it: a picker could have their chart taken
at random by `auto_pick` while still reading the result, and `prompts._break`'s no-ping
("the result beat lands at the same instant") had been false since the interleaving moved
the break line behind the pick. Cost is a worst case of 300 + 60 rather than 300; engaged
play is unchanged, because the Ready flags that ended the rest are deliberately **not**
cleared when the turn is served, so the sweep after the pick opens the round rather than
asking again.

Three traps, each pinned by a test in `TestBreak`: a rest before an unnamed round is
invisible to `phase_of` (there is no PENDING round to hang it off, so it gained a
`turn_owed` branch); a **spent** rest is not a break (a pending round whose predecessor
closed long ago is the state between a pick and the sweep, and calling it a break posts a
Ready counting down to a moment already past); and Ready must survive the turn being
served. See [[tournaments#The rest comes before the pick (owner, 2026-09-06)]] and
[[tournaments-module#Rest, then pick]].

---

## 2026-09-05 — picks are interleaved: ban, ban, pick, play, pick, play

`/tournament` drafted the entire card before round one — two bans, then `best_of - 1`
picks back to back. That is the **CS2 map-veto** shape. It is a real format, but it is
the wrong one here: CS front-loads its veto because the veto is a broadcast segment, and
CS never runs Bo7. A Bo7 here asked for **six** picks in a row, all six decided at 0-0,
and ran six 60-second turns before a note was played.

Now the **bans** are the only thing drafted up front. Each pick is served **between
rounds**, on the result — the osu! shape, which is the convention every rhythm-game
tournament scene copies. Three things follow: a player who is 1-3 down can pick their way
back, a match taken 4-0 never drafts the charts nobody plays, and the drafting spreads
into the gaps instead of sitting in front of them. Strictly one at a time, not one each
per pair of rounds: revealing both picks before either is played rebuilds the original
problem in miniature — the second picker learns the first pick, but the score has still
not moved.

**Multiple ban phases were considered with it and rejected.** The one conventional shape
for more banning is CS's `ban ban → pick pick → ban ban → decider`, whose second ban round
exists only because there is a pick *phase* to sandwich it around. With picks in the
breaks there is nothing to sandwich, and a ban between rounds bans charts that may never
come up.

`pickban.py` did not change. The sequence is still one flat list, the next turn is still
position `turn_index` in it, side is still `index % 2`, and `pool_size` is still
`2 + (best_of - 1) + 1` — the worst case is still every round being played. Only *when* a
turn is asked for moved, which is `match.py`'s business: `act` hands the match to
`PLAYING` after a pick instead of serving the next turn, and `service._resume_pickban`
hands the turn back once that round is closed. `PICKBAN` stopped being a state a match
passes through and became one it re-enters.

Three traps, each now under test:

- **A gap between rounds is indistinguishable from the end of a match** — every round
  closed, none pending. `_finished` closing there ends a Bo3 at 1-0. It now treats an
  owed turn as a round that does not exist yet.
- **`turn_index` never leaves 0 on a match that never picks**, so the sequence alone
  reports a ban owed for every bans-off and every 3+ roster match, and none of them would
  ever close again. `match.turn_owed` re-reads the frozen roster rather than trusting
  match state.
- **The result beat is owed while the match sits in `PICKBAN`.** The tick that closes a
  round is usually the one that hands the next pick back, so the `PLAYING`-only beat gate
  would have asked a player to pick before the thread was told who won.

The pick costs the gap between rounds nothing: `_break_over` still measures from the
previous round's close, so the turn runs *inside* the 300 s break rather than on top of
it. Undrafted entries on a finished match now render `unplayed` rather than `available`,
which would read as still on the table. 419 tests pass.

---

## 2026-09-05 — `best`-score mode retired: a round counts your first score, full stop

The scoring rule was a **parameter** from the first design pass — `first` (default) or
`best`, authored onto a match and copied onto every round. Both shipped 2026-09-02. Only
`first` was ever played.

`best` was the more expensive half of a choice nobody made. It bought a `scoring_rule`
enum, a column on **two** tables, a branch in the standings `ORDER BY`, a `rule:` option, a
resolver branch, a board string with two spellings — and, in the sweep, **two rule gates
that existed to say what `best` could not do**: the early `open → grace` exit and the early
end of grace both carried a `!= ScoringRule.FIRST` guard plus a comment explaining why
"everybody has a score" promises nothing when a further play can still change the result.

It also owed a design it never got. `WINDOW_SECONDS` is flat *because* a `first` window
ends the moment both sides score; a `best` window ran the full 300 s, which
[[h-tournament-window-and-clock]] recorded and the owner accepted on 2026-09-03 leaves one
attempt on most charts and **none** on a 4:10. So the mode you could pick behaved worse
than the default, and the fix for it was an unbuilt timing model.

Removed outright: `ScoringRule`, `scoring_rule_type`, both columns (migration
`d7b2f4c19e83`, `alembic check` clean and round-tripped), `options.RULE`, `DEFAULT_RULE`,
`Chosen.rule`, `MatchOptions.scoring_rule`, `MatchView.scoring_rule`, and the `rule:`
option on `/tournament quick`. The board still prints "first score counts" — anything that
changes how you play is printed — but as a constant, not a rendered value.

What that bought back:

- **`results.standings` has one `ORDER BY`.** `DISTINCT ON (account)` takes the earliest
  play; a later one is never read, whatever it scored. New regression:
  `test_only_the_first_play_counts`.
- **The early exits stop being conditional**, and the flat window stops owing a caveat to a
  mode that no longer exists.
- **[[h-tournament-attempt-overhead]] closed** — it only ever sized a `best` window.
  Overhead may return as an input to [[h-tournament-quit-rerolls-first]], which is about
  the rule that shipped and is still open.

Written up as [[h-first-score-is-the-only-rule]]. Suite unchanged: the 44 failures in
`tests/` are pre-existing drift between the tests and this mid-refactor tree (`pool_size`
arity, `PotentialEntry`, `ChartFacts`, copy strings) — a before/after run differs by
exactly the one lifecycle test this change fixes and adds none.

---

## 2026-09-05 — A pool sized for bans nobody turned on, and a shortfall nobody was told

Owner hit it on `level:12`, which the catalog answers with exactly **two** charts (Testify
BYD, DEINOS PHAINEIN BYD). Two attempts, two different failures, one root.

**With bans on** it refused honestly: a Bo3 needs 5. **With bans off** it refused for a
requirement that did not exist — `pickban.pool_size` never read `match.pick_ban`, so it
asked for `2 + (best_of - 1) + 1` regardless, while `_rounds_without_pickban` consumes only
`drawn[:best_of]`. Item 1 of [[h-tournament-pool-sizing]], filed two days earlier and now
answered: `pool_size(best_of, roster, pick_ban)`, and bans off at two players returns
`best_of`. A bans-off Bo1 or Bo2 at level 12 now runs.

The second attempt did not say any of that — it **hung on "readied"**. Two silences stacked:

- `_on_message`, the chat-word Ready ("r", "go", "ok"), threw the refusal away entirely.
  `_start_if_confirmed` returned it and the caller ignored the return.
- The button path did report it, but ephemerally, to whoever clicked last. The other player
  got nothing, and the draft prompt — keyed by roster size, so it never retires — kept
  saying "hit **Ready** and the match starts" over a board where everyone already had.

A shortfall is a fact about the match, not about the click that discovered it, so
`_start_if_confirmed` now posts it **into the thread** and clears every Ready: the ask goes
back up honestly, and a curious re-click cannot repost it until a full round of
confirmations has been spent again.

Better still, it mostly stops happening. `/tournament quick` now runs `pool.candidates`
**before opening a thread** — which is what [[handoff-13-tournaments|handoff 13]] specified
and what had never been built — so a band that cannot fill a pool costs one ephemeral line
instead of a thread, two pings and a board nobody can act on. Joining only relaxes the
requirement, so a pre-flight pass stays valid for the life of the draft.

Item 3 fell out of the same pass: `levels._BOUND` is now `^[1-9]\d?\+?$`, so `level:0` is
refused as a level rather than encoding to the TBA sentinel and reading as an empty catalog.
Item 2 (`Bo{n}` printed for a >2-player match that plays one round) is untouched and still
open — it is a surface problem, not a sizing one.

Touched: `tournaments/pickban.py`, `tournaments/match.py`, `tournaments/pool.py`,
`tournaments/levels.py`, `extensions/tournament.py`.

---

## 2026-09-04 — `first` does not mean one attempt: a quit submits nothing

Owner-raised, unbuilt, filed as [[h-tournament-quit-rerolls-first]].

The `first` scoring rule was shipped on the belief that retrying is pointless, and the flat
300 s window ([[h-tournament-window-and-clock]], answered the day before) on the belief that
it is a **forfeit timeout, not a budget**. Both are wrong for the same reason: `first` binds
the first *submitted* score, and **an abandoned play submits nothing**. Bail out, restart,
and the sheet is still clean.

`_maybe_close_window` cannot save it — `all_scored` needs BOTH sides, so an honest opponent's
submission closes nothing and the player who keeps quitting holds the window open alone. At
`t = 150 s` the budget is about **three retries**, and `viewbuild._result` builds standings
for any round past `PENDING`, so an **open** round publishes its scores: the retries are
aimed. The budget goes only to players who know a quit does not submit, which is worse than
an honest three-attempt rule.

**No window length closes it.** Excluding a reroll needs `W <= t + o + q_min` while admitting
an honest play needs `W >= t + o_max`; with `q_min` about a second, both hold only if
song-select overhead is deterministic. Reverting to `clamp(2t, 200s, 500s)` would widen the
budget, not close it.

The proposal is to stop sizing the window: **the first submission opens a band of `x`
seconds and the round is decided on what is inside it**; a side with nothing in the band
scores nothing, so quitting becomes a forfeit rather than a reroll. It is made safe by a new
owner-stated fact — **Link Play** (the in-game room, up to 4, charts may differ) submits
every score **at the same time, hard deaths included**. That kills the anchor-poisoning
attack a solo hard death would otherwise enable ([[d-hard-gauge-early-submit]]), and it means
the bot never has to detect the room: simultaneity *is* the room's signature, which is
fortunate, because `play_scores` carries no link-play marker and the wire offers none.

The cost is a **roll call** before `start_ms` — the reveal alone stops being a fair "go" once
the first submission decides for everyone — and solo/async play, which a band excludes.
Bonus: both timestamps come from lowiro's clock, so a band is immune to
[[h-tournament-clock-skew]], and `best` would inherit the timing model it never had.

Nothing built. `wiki/domains/tournaments.md` §The window duration and §Scoring rule carry the
correction inline.

---

## 2026-09-03 — Ownership answered: the wire already knew, and OWNED ≠ UNLOCKED

[[h-ownership-blob-open-before-building]] closed after 44 days, and it closed by having its
premise removed. [[handoff-11-ownership-blob|Handoff 11]] was built on the belief that lowiro
*"never reports unlocked state"*. **It does.** `GET /webapi/user/me` carries `packs`,
`singles` and `world_songs`; every id maps onto the catalog with **no translation table**
(59/59 packs, 129/129 singles, 95/95 plain ids, 50/50 Beyond entries), and catalog coverage
by derivation is **552/552**. A credentialed player never needed a blob at song grain.

The whole catalog was diffed against one live t3 payload, and the diff became a worksheet the
owner filled in — 146 answers, then four follow-up rulings that resolved every contradiction
the answers contained. Filed as [[ownership-worksheet-2026-09-03]].

**`world_songs` is misnamed.** Not "unlocked in world mode" but *"held, and not accounted for
by `packs` or `singles`"* — a catch-all filled from unrelated routes. `chronologia` proves the
read: bought after its free window closed, so it sits in `singles` and **not** here. The array
records how you got it, not what it is.

**Neither array is a denial.** The `extend_*` packs release songs incrementally and free
through world mode while also being buyable whole, and the measured account disagreed in both
directions at once — owning `extend`/`extend_2` (20 songs each) while listing only 4 and 2 in
`world_songs`, and listing all 20 of `extend_3` and all 16 of `extend_4` while owning neither.
So pack ownership is **sufficient, never necessary**, and `world_songs` absence is **unknown,
never locked**.

**The near-contradiction that turned out to be the finding.** The worksheet asked for a
per-pack Beyond rule and got `included` for six packs; the per-chart section then ruled 16 of
those same charts `story`. The owner's ruling: not a contradiction, **two independent axes** —
*acquisition* (always "with its pack or song"; no Beyond is sold separately) and *unlock*
(world map, or story). Both true of the same chart. Which means **66 of 67 Beyond charts carry
an unlock condition**, and exactly one — Your Best Nightmare — is playable the moment you buy
its pack. The worksheet's own claim that the 17 absent Beyonds were "unlocked by owning the
pack" was false in 16 cases.

`world` and `story` stay distinct rather than collapsing to "locked" because *"world mode
unlocks takes time"*, while story is one-off progression whose cost varies — *"thats why we
ask per chart"*. Both mean **ask the player**, which is why 8.a2 chose a declaration over a
catalog-side rule.

**Cross-pack grants do not exist.** The worksheet had a whole section on `guardina` being
granted by `dynamix` and `diein` by `djmax`, and on the catalog having no field for it. Wrong:
they are ordinary world-mode unlocks whose **map** has a prerequisite. Nothing is granted by
owning something else, and the catalog needs no grant-edge field. Section struck.

**Eternal removes work rather than adding it.** 109 songs carry one, no array reports it, and
none is needed: it opens by ordinary play (fragments, or grades on other charts). Owning the
song is the whole condition — `playable(etr) = playable(song)` — and pools may draw Eternal
freely.

**The directive nothing had asked for**, and the spine of whatever gets built:

> *"we should have a whole new OWNED and UNLOCKED system"*

Correct diagnosis of why `world_unlock` is a mess — one boolean on `Song` carrying two
orthogonal facts at the wrong grain. **OWNED** = did you acquire it; **UNLOCKED** = have you
satisfied the in-game condition; `playable = OWNED ∧ UNLOCKED`, with `has_score` as proof of
both. Both axes reach chart grain *and* pack grain — `epilogue` is a whole pack that is
acquired free with `finale` and then gated behind story.

**Design calls, all owner:** song-grain ownership derived from `/me` with no input (t2/t3);
Beyond **asked**, of everyone, since the wire reports it positively only; t1 by manual
declaration with `playable = declared ∪ has_score`; **both** surfaces (inline Discord picker
*and* static page → blob); stored at **chart** grain; and the tournament pool filter is
confirmed wanted — `pool.owned_by_all` is no longer waiting on a blob that might never exist.

**18 `world_unlock` rows are wrong** — 7 unflagged in `extend_3`/`extend_4` (staleness; the
owner's "all 20"/"all 16" and the seven "prob stale" answers corroborate exactly), and 11
flagged that should not be, three of them songs whose *Beyond* carries the unlock. Plus one
stale pack name (`extend_3` → "Extend Archive 3"; `extend_4`'s "World Extent 4" is correct as
stored, typo and all). Itemised and **unapplied** in [[h-world-unlock-corrections]] — this
session was documentation only, by instruction.

Also noted while measuring: `song_difficulties.world_unlock` already overrides at chart grain
and **7 rows already use it**, all `byd`, all `True` over a `False` song — 7 of the 50
world-earned Beyonds. The schema reaches the right grain; the data uses it for 14% of the
cases that need it.

Touched: [[catalog|Catalog]] §Ownership (rewritten), [[tournaments|Tournaments]] §Traps
(narrowed — ownership stays out of *ranking*, returns as a live *pool* filter),
[[h-ownership-blob-open-before-building]] (answered), [[handoff-11-ownership-blob]]
(superseded), [[h-world-unlock-corrections]] (new), [[ownership-worksheet-2026-09-03]] (new),
[[index|Index]].

---

## 2026-09-03 — The round clock answered and built: a flat window, and beats

[[h-tournament-window-and-clock]] closed. The owner's goal was to need **no signal that
valid scores are being read**; the answer turned out to be ordering, not leniency.

**The reveal is the go signal.** A round's chart is not named until its break ends, and
`start_ms` is the instant of that announcement — so a player cannot act before the window
opens, and nothing needs announcing separately. Two designs were considered and dropped in
conversation: a *soft start* reaching back before `start_ms` (it would let a player who
ignored the board out-play one who believed it), and a window **reaching back through the
break** (same trap, plus it makes the board lie about its own clock). Both would also have
been beaten by the third finding —

**"past the song pick time" does not survive pick/ban.** Every chart is picked *before
round one opens*, so anchoring a window to its entry's `acted_at` would let a player bank a
score on round three's chart during round one. Under `best` a head start; under `first`
worse, because the banked play *is* the first inside the window and locks in. Anchoring to
the reveal makes it structurally impossible.

**The window is flat 300 s.** `window.py`, `pool.chart_times`, `service._chart_times` and
**decision 8's `t = 0` sentinel rule** deleted — all of it existed only to size a window
that is no longer sized. It can be flat because under `first` it is rarely spent: the
all-scored exit ends it early. That exit stays `first`-only; `best` runs the full window
until it has timing rules of its own, and it was flagged to the owner that at 300 s `best`
collapses toward `first` on long charts.

**The break was wrong about its own purpose.** `INTERMISSION_SECONDS` justified itself as
song-select navigation budget for the `2t` window — which 300 s now contains outright. Its
real purpose, per the owner: *a rest to read the result in*. Renamed `BREAK_SECONDS` and
documented as running from the round being **decided** (`closed_at`), which was already the
arithmetic; what was missing was that none of it was visible.

**Beats.** `announce.py`: the board is state and is edited, but Discord does not notify on
an edit, so *moments* are new messages — `reveal` and `result`, one each per round, pinging
a roster whose `Side.discord_id` was hardcoded `None` until now. Owed while their stamp is
NULL on the round, stamped only once the message lands, and a **closed** match stays in the
sweep while it owes one (it leaves `LIVE_MATCH` on the tick its result is announced on).

**Grace stopped lying.** It printed *"Next round shortly — press Ready to go now"* while
still collecting the score a player had just set. `MatchView` now carries a `phase` from one
definition, `service.phase_of`, read by the board and the chat-line Ready alike. Ready is
offered only in the break — and now also accepts a **word in the thread** (`ready`, `gg`,
`go`, `+`, …), matched whole so *"ready in a sec"* is not agreement.

**Fixed the same day, from the bot's own log.** The first `/tournament quick` after the
build created its thread and then died posting the board:
`AttributeError: type object 'ArcaeaAccount' has no attribute 'discord_id'`. The mention
wiring had read a grep of `arcaea_account.py` and taken `discord_id` for the account's own
column — it belongs to **`PlayerLink`**, further down the same file, because many Discord
users may share one Arcaea account. Now a LEFT join preferring `is_owner` ("the single
link that speaks for it") with the oldest link breaking a tie. Every existing test built
a `Side` by hand, so nothing exercised the query; `TestViewBuild` now runs
`viewbuild.build` against the real schema.

**Owner direction, same pass: the board calls people by their DISCORD name.** `Side` keeps
both and resolves with `Side.name`. Captured onto `tournament_participants.display_name`
at `/tournament quick` and `/tournament join` rather than looked up — the bot runs
`ALL_UNPRIVILEGED`, so `GUILD_MEMBERS` is off and the member cache cannot be trusted; the
command that rostered a player is the one moment their real user object is in hand.

Schema: `tournament_rounds.revealed_at` / `resulted_at`,
`tournament_participants.display_name`, and an index on
`tournament_matches.thread_id` for the message listener. 33 new tests; 129 tournament tests
green. [[h-tournament-sticky-board]] updated — the beats close its "nothing notifies"
motivation, and the owner reversed its delete-the-old-board ruling.

---

## 2026-09-03 — Handoff 13 spot-checked. Two fixes, six pages filed

A read of `src/coda/tournaments/` (2,157 lines), `extensions/tournament.py`, the seven
tables and the 105 tests. The design holds: the layering invariants are real, `hikari`
genuinely stays in `render.py`/`transport.py`/`board.py`, and the "playable by inserting
rows" claim is true. Two things fixed on the day, four decisions deferred to their own
pages, one residue page.

**The sweep could die silently, and take every tournament with it.** `@loader.task`
defaults to `max_failures=1` and lightbulb cancels a task **permanently** on its first
failure — it sets `cancelled` and returns (`lightbulb/tasks.py:333`). Nothing else opens a
window, closes one, auto-acts an expired turn or redraws a board, so one transient error
would have ended tournaments for the life of the process with a single ERROR line. Now
`max_failures=-1`, and `service.tick` advances each match inside its own SAVEPOINT so a
match that cannot advance costs only itself rather than aborting the transaction the others
share. Board redraws are guarded per match too — by then the DB work is committed, and a
board that will not draw must not cost the other boards their redraw. New test,
`TestSweepIsolation`, patches `_advance_rounds` to raise on one of two live matches and
asserts the other still opens its round and the session survives.

**The option constants had no owner.** `RULE_CHOICES` and `VISIBILITY_CHOICES` were dead,
and the lists they duplicated were written out three times — the `/tournament quick`
picker, the `/config` enum in `settings/registry.py`, and `defaults.py`. Now one table per
choice in **`tournaments/options.py`** (stored value → picker label), read by all three.
It has to be a leaf: `defaults.py` imports `coda.settings`, and `coda.settings.__init__`
imports `registry`, so the tables could not live where they were and still be read by the
registry. The pickers render identically; the only visible change is `/config`'s visibility
enum now listing `private` first, matching the picker and the default.

**Filed, not fixed.** Four need an owner decision and got pages:
[[h-tournament-window-and-clock]] (owner wants every window at 5 minutes with the passive
gatherer ending it early and a soft start — which retires `duration_for` and decision 8's
sentinel, and shares a surface with the fact that **nothing announces an open round**: an
in-place `edit_message` sends no notification and `Side.discord_id` is hardcoded `None`,
so no mention is ever built); [[h-tournament-sticky-board]] (owner ruled sticky — delete
and repost — which also absorbs `/tournament board` committing a null `board_message_id`
on a failed post, the orphaned board whose stateless components still work, and
`refresh` snapshotting outside its lock); [[h-tournament-untracked-participants]] (owner
ruled tracking should **not** gate a match — but `ObservationCache` is latest-play-only on
a 300 s TTL and `standings` needs every play in a window, so adoption is a persistence
decision at `scores/service.py`'s choke point, not a read swap);
[[h-tournament-one-match-per-thread]] (a second `/tournament quick` on a live match
strands the first — `_match_here` takes the newest, so nothing can cancel it).
[[h-tournament-pool-sizing]] is owner-flagged for a dynamic rework: `spec_of` never reads
`match.pick_ban`, so bans-off at Bo3 draws 5 charts, plays 3, and refuses filter sets that
would have run. [[h-tournament-spot-check-leftovers]] holds the residue — the `act` race,
`viewbuild`'s N+1, and the note that `approvals.py` and `chardle.py` carry the same
`max_failures` exposure the sweep just lost.

---

## 2026-09-02 (3) — Quick match BUILT. Handoff 13 ships, with six deltas

[[handoff-13-tournaments|Handoff 13]] implemented as `src/coda/tournaments/`: seven
tables, five native enums, seventeen modules, `/tournament`, and a hot lane in the poller.
The formats layer ([[handoff-14-tournament-formats|14]]) is untouched — its columns exist
and nothing writes them. New page: [[tournaments-module]]. [[tournaments]] loses its
**NOT BUILT** banner.

**Four owner rulings changed the design, all in one direction — a quick match should be
worth configuring, and casual play should be a first-class option rather than an
accident.** `/config` grew to **four** keys (`level`, `bans`, `best_of`, `visibility`),
reversing decision 38's "exactly two". `tournament_default_level` became a **range**, and
unset now means **any level** rather than refusing the match — "any" is a choice an
organizer may make, and the board prints it like every other filter.
`tournament_default_class` was **deleted**: the difficulty class is a **required** option,
because `ftr` versus `any` decides whether the match is competitive or casual and that is
not a thing to inherit silently from a server setting.

**`class: any` is song mode, and that reshaped a table.** A pool entry became a *song*
rather than a chart, so `tournament_pool_charts` shipped as `tournament_pool_entries` with
a `song_id` and a nullable `song_difficulty_id`; the round's chart set is re-derived from
the match's stored filters at spawn time. **The level band still bounds a casual set**
(owner): a lv9–10 match must not be winnable by posting 10,000,000 on a PST 4, so a song
contributes only its in-band difficulties and a song with none is never drawn. The
owned-by-every-participant filter shipped **always-on with no option** — you cannot play a
chart you do not own — as a stub returning its input.

**Two deltas came from measuring the design against the shipped poller.** The handoff
assumed "hot at 5 s"; `PollSchedule` carries one scalar interval, `STAGGER` idles 3–12 s
*between* keys inside a tick, and `PollCoordinator`'s refresh budget is 2 per
`poll_interval` per key with a sleeping `spend`. Owner picked **15 s**, which fits all
three — a window is 200–500 s, so it costs nothing real. Hot keys skip `_spread` (it
compares phases modulo one interval and is undefined across two) and are **pulled
forward** when they go hot, or the fast cadence would not begin until the slow slot they
already held ran out. And the board's **debounce dissolved**: the 5 s sweep already bounds
edit rate and, unlike a debounce, cannot drop the final frame. The per-match `asyncio.Lock`
survives, because pick/ban clicks write the same message as the sweep.

**Two corrections to the handoff, found by building it.** Decision 8's sentinel was
under-specified: `max({150, 0})` is 150, but a known neighbour says nothing about how long
the unknown chart runs, so **one** unknown in a set now takes the 500 s ceiling — song mode
made multi-chart sets the norm, so this stopped being a corner case. And decision 22's crew
row is written at **roster freeze**, not at create: `/tournament join` changes a roster
while the match drafts and the reuse key *is* the roster, so a create-time write binds the
thread to the crew that opened the room rather than the one that played in it.

One real bug caught by a flaky test: `auto_pick` was called *inside* a generator
expression, redrawing a random entry on every comparison and occasionally matching none —
an expired pick/ban turn would have raised instead of acting.

`scores/routing.py` is new: `/recent`'s "own path if it can, else friend" resolver, lifted
because tournaments became its second caller. It returns an opaque `PollKey`, so
`cadence.py` never sees a `bot_account_id` — the handoff's own SQL selected that column and
would have broken [[w-sid-confined-to-sessions]].

111 tests added (`window`, `levels`, `pickban`, `results`, the hot lane, the surface, and a
full draft-to-closed lifecycle driven only by inserted `play_scores` rows — the module's
central claim, under test).

---

## 2026-09-02 (2) — Tournaments, second pass: the surface. A match layer appears

Design session on the tournament **frontend**, following (1) the same day. Nothing built.
Four owner rulings, and the third of them added an object the first pass did not have.

**Every match lives in a thread, off one dedicated channel — and only there.** Private or
public; the guild sets a home channel and no channel set is a *refusal*, never a fallback
to the invoking channel. This **reverses** first-pass decision 13's `guild_id NULL` =
DM/private room: a bot cannot open a thread in a DM and cannot create a group DM, so a DM
room could hold neither the board nor a second player. Privacy is a private thread
instead, which is strictly better — participants can talk to each other in it, and the
owner's framing was that *everything* happens in the one place. `guild_id` is now
`NOT NULL` and the module is guild-only.

**Thread reuse is keyed on the exact roster, for quick matches only.** A crew that plays
again lands back in its own thread, which accumulates one board per match and *is* their
head-to-head history — so there is no history command and no results table. Any
difference in the set, or public-vs-private, is a different thread. A full tournament
(registration, multiple rounds) **never** reuses and names its threads for the stage: a
bracket match is a one-off, and folding it into a crew thread would bury it. The key is a
`tournament_threads` table, never inferred from the newest match — that inference is
exactly what failed for chardle dailies ([[h-chardle-boards-are-channel-owned]]), and the
same three revalidations apply (is a thread, parent is the *current* home channel,
unarchive).

**The board is a rendered image of MATCH state — and that forced a new object.** Not a
standings embed: a chart pool carrying pick/ban marks and per-chart winners. A pool spans
several rounds, so it cannot belong to one, and the model became
`tournament → match → round`. The match owns the roster, pool, pick/ban sequence and
best-of; the round is unchanged and still the only thing that reads `play_scores`. A
quick match is just `tournament_id IS NULL` — not a second code path. `guild_id`,
`channel_id`, `admin_gated` and `open_join` moved off the round onto the match. Schema
went 3 tables to 7. The image design itself is the owner's; the handoff carries the
`MatchView` contract, the six states it must draw, and the constraints (no viewer, so no
"you" highlight; Arcaea names not Discord ones; two encodings; cache avatars or drop
them).

**Pick/ban is head-to-head only, best-of-N, auto-acting on timeout.** Two players
alternate bans then picks and the survivor is the decider; three or more skip pick/ban
entirely and the generated pool *is* the chart set — which is the casual song-mode round
the first pass already had. Snake order over 5 players was rejected: whoever bans last
shapes the pool alone. A turn that expires **bans or picks at random**, applying decision
10's "never wait on a human" one level up; deterministic auto-act was rejected as
guessable and therefore exploitable against an ordered pool.

The pool is **generated from filters** — level, difficulty class, and *owned by every
participant* — rather than typed chart by chart or saved as named pools. That last filter
narrows the standing "song ownership is OUT OF SCOPE" ruling without weakening it: it
decides which charts are *offered*, never whether a score counts or how it ranks, and it
is a no-op until [[h-ownership-blob-open-before-building]] is answered. Generation also
excludes spoilered charts — a pool *names* charts in a readable thread, so a spoilered one
there is an **active** spoil rather than an answer to a question, and chardle's answer
picker is already the only such leak in the bot ([[h-spoiler-is-a-render-mode]]).

**Deferred deliberately:** live score visibility during `open`. v1 draws a score as soon
as ingest sees it; the owner scoped the question out and flagged it to revisit when `best`
mode is designed, since a visible leader score turns a `best` window into target-chasing.
Under `first` it is inert.

### Then: configurability, without paying for it in usability

Second half of the session. The module has a dozen knobs; all of them as slash options
makes `/tournament quick` unusable, all of them in `/config` makes starting a match a
configuration exercise. Three tiers by who changes a thing and how often — **invariant**
(code), **guild default** (`/config`, `GUILD → GLOBAL`), **per match** (an option). Four
rules, of which the fourth is the load-bearing one:

1. `/tournament quick with:@bob` is a complete command. `with:` is the only required
   option; configurability that lengthens the common command has failed.
2. An omitted option is `None` and **inherits** — never a literal default. The idiom
   [[h-spoiler-is-a-render-mode]] §5 already set for `ephemeral`.
3. **Nothing is writable at `USER` scope.** A match is shared state; a per-user default
   scoring rule means two players believe different rules apply and the board can only
   draw one. The existing scope chain is narrowed here, not reused.
4. **Anything configurable that changes how you play is printed on the board**, and the
   converse — config that is not on the board must not change how you play. Knobs are not
   dangerous because they are numerous, but because they are *invisible*: two servers
   playing what looks like the same game under different rules with nothing on screen
   saying so. Bounding the config space to what the board can state is stricter and more
   useful than bounding it by count. It is also what makes the other three safe.

Plus: a **derived value never gets its own key** (pool size is a function of `best_of`;
offering both lets a guild configure a Bo5 with three charts).

Two prerequisites in `settings/`, neither tournament-specific and both improving the six
keys already there: **`min`/`max` on `ConfigKey`, validated in `parse.py`'s int branch**
(it coerces and validates nothing today, so a turn timer of `0` hangs a match — a
pre-existing gap `chardle_bpm_window` and `chardle_abandon_hours` share), and **prefer the
tuple type over int** wherever the option set is small, since the enum type is
self-bounding and yields a picker for free.

### Correction, same session: configurable means FORMAT, not timings

The owner rejected the config model above on the axis, not the detail. Tuning knobs
(`tournament_turn_seconds`, `tournament_intermission_seconds`, a `tournament_max_roster` of
8 that had been **invented wholesale**) were the wrong thing entirely. Two rulings replaced
them.

**Stop waiting rather than tuning the wait.** One fixed intermission, one fixed turn value,
and *the wait ends when the thing it waits for has happened* — plus an instant-start button.
This is decision 10's early `open → grace` exit generalised to every wait in the system, and
it retires every timer key: a tunable timeout is what you build when you cannot end the wait
early. `Ready` becomes **one primitive** — a per-participant flag cleared whenever a new wait
begins — serving the intermission skip and the instant start alike. Timer lengths become
constants beside `DEAD_END_TTL` and `LIVE_WIDTH`. The `min`/`max` addition to `ConfigKey`
stops being a prerequisite (still a real gap for chardle's keys, just not this module's).

**The configurable axis is the format**: single elimination, double elimination, round
robin, a no-elimination lobby, and banning switchable off. This landed better than feared —
**the match is the invariant unit and every format decomposes into matches** (lobby = one
match with everyone; round robin = one per pair; bracket = one per node), so four formats
perturb nothing below the tournament. A format decides exactly two things: which matches
exist, and what a finished match does next.

Four format rulings: **async** for bracket and round robin (28 matches at 8 players cannot
run in one sitting, so a match waits for both players and instant-start fires it — which
scopes "never wait on a human" to *inside* a match); **random seeding** shown before the
first match (not registration order, not PTT — decision 12 already refused ratings deciding
anything competitive); **a lobby plays N rounds with points accumulating**; and **a no-show
forfeits while a double no-show stalls** for the organizer, because silently emptying a
bracket branch is worse than a visible stall.

Configuration then reduced to one line: **it lives where the choice is already being
deliberate.** A quick match must be one option long, so its format is fixed and two guild
defaults fill its gaps; creating a tournament is already a form, so it carries the full
format spec and needs no guild defaults at all. The tier is not a property of the value, it
is a property of how much attention the user is already paying. Two `/config` keys survive,
both only so `/tournament quick with:@bob` stays one option long.

**Then the handoff was split**, on the owner's instruction, at the match seam.

**Pages touched:** [[handoff-13-tournaments]] rewritten and rescoped to **the match and
below** (187 → ~815 lines; decisions 17–42, 7 tables, two state machines, Discord surface,
board contract, configuration); [[handoff-14-tournament-formats]] **created** (decisions
43–52, the four formats, registration and entrant schema, the advancement graph as explicit
rows, async lifecycle, standings, the bracket board and its width problem); [[tournaments]]
reconciled against both — status callout, three-object model, a format subsection, both
state machines, §Starting a match rewritten for threads, the ownership ruling narrowed in
place, §Configuration rewritten around the wait rule, source section demoted.

---

## 2026-09-02 (1) — Tournaments iterated: score-only ranking, casual song mode, rooms

First movement on tournaments since the 2026-07-21 ingest. Still **not built** — design
only — but four owner rulings landed, two of which reverse the page.

**A round is an eligible chart SET, not one chart.** That split a question the
single-chart design could answer once: which plays are eligible, and how eligible plays
compare. Standard = a one-element set; **casual song mode** = every difficulty of one
song, mirroring the game's own multiplayer room — the room picks a song, each player
picks a difficulty. Membership stays on the resolved `song_difficulty_id`, so `byd_2`
remains free.

**Ranking is raw `score`, full stop** ([[h-score-is-the-only-ranking-value]]). Play rating
was the obvious cross-difficulty normalizer and was rejected: it depends on a catalog CC
that can be TBA or refined later, and since 7.0 folds in a clear bonus tier 1 can only
infer — so the same play would rank differently depending on which path saw it. A PST
9.9M and an FTR 9.9M tie, deliberately. Consequence worth carrying: the lowest difficulty
in a pool is always the rational pick, so **pool selection is the balancing lever**, which
is the argument for it staying a deliberate organizer choice rather than anything derived.

**Every score in the window counts** ([[h-every-valid-score-counts]]) — this reverses the
page's "cannot be enforced on tier 1" framing. Filtering hard-gauge deaths (by `modifier`
on tier 2, or by a `time_played < start + t` inference on tier 1) does not prevent a cheat,
it *creates* one: under `first`, a discarded play hands back a free reroll, which is the
one thing `first` exists to stop. Owner's call, and it is the general rule — any future
proposal to reject a play must answer why it is not a retry. Tier 1 losing
`clear_type`/`modifier` costs this nothing, because the rule never wanted those fields.
Together with score-only ranking that makes **a round tier-agnostic**, and "do not mix
tiers" now survives only for detail formats these rules rule out.

**Rooms, and the friend-slot correction.** A round is created as a room; a server-wide
event is the same object, guild-scoped and admin-gated — same reasoning as
[[h-chardle-boards-are-channel-owned]]. A room is **not tied to a bot account**: the friend
link belongs to the player (`pool.place()` writes it once), and the tournament layer reads
`play_scores` without ever seeing a `bot_account_id`. So `max_friend` bounds the total
observable player population, never how many rounds may be open. The real per-round cost is
cadence fan-out, which scales with participant *scatter*, not room count.

**Window duration settled, and the manual note baked in.** `t = 0` now resolves to the
**ceiling** — an unknown length widens the window, never narrows it — and window `t` is the
**max** across the chart set. Bounds landed at **`clamp(2t, 200s, 500s)`** after two passes:
a first move to 120s/300s on the reading that no song is under 2m, which the live catalog
disproved (552 songs, `time` 0-189s, shortest non-zero is `Lights of Muse` at 100s, 26 songs
under 2m), then the owner's correction to 200/500 once 300 no longer looked right beside a 2t
floor of 200.

The final shape is the good one, and measurably so: **no song is under 100s and none reaches
250s**, and no per-difficulty override falls outside that band, so *neither bound clamps any
catalog input*. Every real chart resolves to a plain `2t` between 200s and 378s; the floor is
a guard against bad catalog data and the ceiling's only live role is the 27 songs carrying the
`t = 0` sentinel. It also makes the attempt budget uniform — `floor(2t / (t + o))` is 1 across
the whole catalog and the whole 20-40s overhead estimate — which retires the "5m ceiling makes
the budget inconsistent" caveat that had stood on the page since the 2026-07-21 ingest.

**[[handoff-13-tournaments|Handoff 13]] written** — a pure implementation spec: 16 locked
decisions, three tables (`tournament_rounds`, `tournament_charts`,
`tournament_participants`), the `src/coda/tournaments/` layout, the standings and cadence
queries, and the state-transition table. Open questions and rejected alternatives are
deliberately excluded; they stay on [[tournaments|Tournaments]] and in `questions/`. The
standings query is where decisions 5 and 6 become structural — it joins no CC and reads five
columns, so there is no field in scope to weight or filter a play by.

---

## 2026-08-31 (8) — Dark Lephon art, the Inscribed plate, and a side clue that scores by family

Owner-supplied Chardle art wired in, plus two rule changes it dragged along.

**Plates are picked by chart now, not by side.** `assets.plate` took `(side, beyond)` and
resolved one filename; it takes `(song_id, side, beyond=, alt=)` and answers three questions
in priority order — is this song its own plate, is this an Inscribed Beyond, else which
side. That order matters: `alt` outranks the side because the Inscribed skin is a chart
property and already spans Achromic and Dark Lephon. `ChartFacts` gained `alt` to carry it,
which is the whole reason the renderer can see it at all.

**Ember's row draws no jacket and no title.** The plate contains both, baked into the art,
so the renderer's job is to *not* paint over it — the geometry is untouched, the space is
simply left to the plate. `assets.BAKED_IN` holds the one song id, and the title cell
is skipped whole — no text and no feedback wash, which would otherwise tint the art's own
lettering. Every other column on that row scores normally.

**`2_BYD.png` / `3_BYD.png` / `4_BYD.png` are deleted.** All three were byte-copies of their
plain plate, kept so a lookup could not miss on a side with no Beyond art. `_side_plate`
now falls back on a missing file, which is a rule rather than three duplicated files. Side 4
never needed one anyway: both Dark Lephon Beyonds are Inscribed.

**Achromic, Lephon and Dark Lephon score as one family** (owner). The `side` column's yellow
is now the only one that is not a distance — same side is green, wrong one of those three is
yellow, anything else is red. It follows the game's own presentation: the song list offers
Light, Conflict and Colorless, and the three sides are one thing to a player. Light and
Conflict are untouched. Dark Lephon is what forced it: a fourth thin side would otherwise
have made the clue near-useless on the charts it applies to.

**Daily clue count 6 → 7.** `MAX_COLUMNS` includes `title`, so the cap the domain page always
claimed is now the cap the code enforces. Measured against the live catalog: draws land on 6
or 7 columns (was 5 or 6) and distinct board shapes fall 64 → 56 — a higher cap means less
freedom about *which* column to leave out. The shortfall is pre-existing and unrelated:
`bpm`/`note` sit in both `_FILLERS` and `REDUNDANT_GROUPS`, so a filler can duplicate the
group's pick and `in_render_order` collapses it.

---

## 2026-08-31 (7) — the 7.0 UI: `/potential`, the clear-review card, disclosure by absence

The owner-facing half of the rework, closing [[h-clear-override-review-queue]] — the last missing
piece. Four decisions, all owner's, all taken before any code.

**Placement: a new top-level `/potential`, not `/score review`.** The wiki's own best guess was
the subcommand; reading `score.py` killed it. `/score` is a *flat* command (`q`, `difficulty`,
`ephemeral`), so adding any subcommand would have forced every existing invocation to become
`/score chart q:…` — a regression on the common path to serve the rare one. `/potential` also
closed the rework's *other* unbuilt half: the aggregate figure had no home outside the `/recent`
impact line. The queue is a list of pool entries, so hanging it off the pool view is the natural
seam rather than a compromise. Still pull-only per
[[d-clear-bonus-impossible-friend-path]] — the entry point is a button on `/potential` itself,
never a hint pushed from a score embed.

**Layout: one card at a time.** The compact-list alternative dies on arithmetic — Discord caps a
message at five action rows, so five plays × [Cleared][Failed] consumes all five and leaves no
room for paging. A select menu paginates fine but costs two interactions per correction. The card
carries the jacket, the score, `chart_rating_line`, and `#rank in your pool · n of N`.

**Bulk accept forced a second review mode.** `Accept all N guesses` writes each entry's assumed
status as an explicit answer — numerically a no-op, the point being that the rows stop asking. But
an answered row leaves the queue by definition, so bulk-accept would have been a one-way door for
up to 50 charts at once. Hence `ReviewMode`: `unconfirmed` is the queue proper, `all` also lists
answered rows so an override can be flipped back. This was not in the original scoping; the bulk
button is what made it load-bearing.

**Disclosure is now by absence** — the change the owner actually asked for, framed as "don't blast
the user". The shipped scheme marked `~` for assumed *and* `*` for owner-marked. But a tier-1
account has `clear_type = None` on **every** row, so before review every rating carried `~` and
after review every rating carried `*`: a mark that fires in all states discriminates nothing. So
`*` is deleted and `~` moved to a **prefix**; wire and override both render unmarked, because both
are statements of fact — one lowiro's, one the owner's. Unmarked now means "known", which makes
the marked rows *exactly* the review queue. This is not a retreat from
[[d-clear-bonus-impossible-friend-path]]'s "never blend them into one number silently": the three
bases still resolve separately and `ClearStatus.basis` still travels with every entry; only the
two *settled* ones share a rendering, which is a different claim from blending a guess into a fact.

Structure: `scores/clears.py` is the only module that writes `clear_override`, holding the queue
filter and two account-scoped UPDATEs. `extensions/potential.py` owns a `pot:` custom-id contract
mirroring `score.py`'s invoker-first shape — not a reuse of `_on_score_component`, whose dispatch
table has nothing in common. The queue is rebuilt from source on every interaction and answering
re-renders at the *same index*, so the answered row drops out and a cascade-promoted buried row
appears in place with no second invocation. `PotentialEntry` gained `rank` so a surface never
recomputes a position it was handed. `/potential` shows the figure with **no `rating_visible`
gate**, unlike `potential_stat_line` — [[potential|Potential]] §Traps scopes hidden-PTT
suppression to passive surfaces, and invoking a self-only rating command is the consent.

Five tests added to `tests/test_potential.py`, four of them pure (the queue filter against
hand-built `PotentialResult`s — no DB, and the counted-boundary case would otherwise need 51
charts). The two writes are left untested on purpose: they commit, and `conftest.py` guarantees
no test ever does.

Unrelated, same session: play embeds now render their timestamp as `<t:…:R>` ("2 minutes ago")
rather than `:f`. One line in `utils/container.py::_caption`, which covers the live poster,
`/recent` and `/score` at once because all three share the embed→container converter, and score
embeds are the only ones that set a timestamp at all.

---

## 2026-08-31 (6) — b30 → b50: the 7.0 potential model ported to code

Backend plumbing for the whole rework, landed in one pass. `scores/b30.py` → `scores/potential.py`
and `b30_stat.py` → `potential_stat.py`, with **model-neutral naming** (`PotentialService`, not
`B50Service`) chosen by the owner so the next rework is a constant change rather than a third
rename. `POOL = 50`, `_DOUBLED = 10`, `_DIVISOR = 60`; `PotentialResult.potential` is the
PTT-scale figure and still divides by the full 60 on an underfilled pool.

The port deliberately did **not** wait on [[h-7.0-potential-rework]] item 4's open `clear_type`
boundary, reversing that page's earlier "should not change until captured" stance. The assumption
is instead isolated to one line in `utils/scoring.py::resolve_clear`, so closing the capture is a
one-line change — cheaper than holding the whole rework hostage to it.

`calculate_play_rating` grew a **required keyword-only** `cleared` argument rather than a
defaulted one: since 7.0 two identical scores can earn different ratings, so a caller that has
not decided must not be able to inherit an answer silently. That forced exactly three call sites
to state their answer, which is the point.

The load-bearing change is not the constants — it is that the per-chart winner is now picked by
**resolved rating over every stored row** instead of `MAX(score)`. Play rating stopped being
monotone in score the moment the clear bonus existed, so the old query selected the wrong PLAY,
not merely a wrong number for the right one ([[d-clear-bonus-impossible-friend-path]]'s worked
example). `best.py` keeps its `ORDER BY score DESC` — correct for `/score` display — and its
docstring now says explicitly that it must never feed the rating calc.

Shipped alongside: `play_scores.clear_override` (nullable bool, migration `1acd77155bd9`); a
config data migration (`a5e0c91d7f34`) renaming `recent_b30_stat` → `recent_b50_stat` and values
`b30`/`b40` → `b50`/`b60`. The value half is **mandatory, not cosmetic** — the settings read path
never validates against the registry tuple, so a stale `b30` reaches `_MODE_REACH` and `KeyError`s
on every `/recent` and `/score` for that user. Verified against real rows: a stored `b40` became
`b60` and a user-scope `always` survived the key rename.

Disclosure, per the gotcha's requirement that the three clear states never blend: `chart_rating_line`
marks an assumed rating `~` and an owner-marked one `*`; `potential_stat_line` marks the PTT figure
when any counted entry rests on the heuristic. `/calc`, which has no play row to read a status
from, shows **both** ratings (`11.0 → 12.5 / 12.7 (cleared)`) rather than silently asserting one.

`tests/test_potential.py` (20 tests) pins the boundaries, the flat bonus, `resolve_clear`
precedence, the `/60` divisor including an underfilled pool, and the override cascade — flipping
one row's override must promote a previously-buried row into the chart's slot.

Still open: the surface that lets an owner SET an override ([[h-clear-override-review-queue]],
now the only missing half) and any `/potential`-equivalent command.

---

## 2026-08-31 (5) — Filed [[d-clear-bonus-impossible-friend-path]], successor to the r10 gotcha

New gotcha page in `wiki/gotchas/`, modeled directly on [[d-r10-impossible-friend-path]]: the
7.0 clear bonus needs `clear_type`, which is `None` on every friend-path-sourced `ScoreResult`
(`src/coda/arcaea/dto/score.py:64`) by construction of the endpoint, confirmed live via
[[h-7.0-clear-bonus-investigation-plan]] Phase 4 (`new_friend_res.json`). Unlike r10, best-50's
per-chart ranking has a sound partial answer from `score` alone (the base formula, no bonus), so
the ruling differs from r10's "drop entirely": tier-1 renders the base-formula figure labeled as
a lower bound rather than gating it away. Flagged as a page-filed ruling pending owner override,
since no explicit owner call on this specific case exists yet — the mechanism (never approximate
an own-credentials-only field) is the established precedent, the "label as lower bound vs. gate"
choice is this page's own reasoning. Cross-linked from [[h-7.0-potential-rework]] item 4,
[[potential|Potential]] §Traps, and `wiki/index.md`. No code exists yet for best-50 to enforce
this against — the page exists to settle policy before the port, same as r10's page did.

## 2026-08-31 (4) — Correction: item 4's friend-path-safety and magnitude were already answered

[[h-7.0-potential-rework]] item 4 and its "Answer" section had understated
[[h-7.0-clear-bonus-investigation-plan]]'s own results — that page's Phase 0/1/4 already
confirmed the clear-bonus magnitude (flat `+0.2`, uniform across score range and every captured
`clear_type`/modifier) and that best-50 is **not** friend-path-safe (Phase 4: the friend wire
carries no `clear_type` at all, confirmed not just analogized by r10). The rework question was
incorrectly still listing these as open. Corrected in [[h-7.0-potential-rework]] item 4, "Current
best guess," and "Answer," and in [[potential|Potential]]'s Traps section and §Historical. Only
the `clear_type` boundary itself (which types earn the bonus) remains a working assumption rather
than a captured fact.

## 2026-08-31 (3) — 7.0 PTT divisor confirmed `/60`

[[h-7.0-potential-rework]] item 2's last open point closed without a before/after play. Owner
supplied `new_rating_me_res.json` (`GET /webapi/score/rating/me`, 50 `best_rated_scores` entries)
and `new_me_res.json` (`GET /webapi/user/me`, same account/session, `user_id: 4213096`) captured
together. `(sum(all 50 ratings) + sum(top 10 ratings)) / 60 = 13.021390523…` against the account's
wire `rating` of `13021` (→ `13.021` at the ×1000 encoding) — exact match; the `/50` alternative
(no top-10 doubling) computes `12.982`, ruling out coincidence. The account's own aggregate PTT
served as the "after" value, so no play was needed to test the formula.

Also confirms in passing: `best_rated_scores` returns exactly 50 entries, pre-sorted descending by
`rating`, one per chart. Still open under item 2: whether an underfilled pool still divides by the
full 60 — this account has ≥50 qualifying charts, so the capture can't exercise that case.

[[h-7.0-potential-rework]] and [[potential|Potential]] updated. Item 4 (`clear_type` boundary for
the clear bonus) is untouched by this capture and remains the only blocker before
`b30.py`/`b30_stat.py`/`utils/scoring.py` can be touched.

## 2026-08-31 (2) — Phase 4 confirmed, Phase 2 attempt inconclusive, working assumption recorded

Continuing [[h-7.0-clear-bonus-investigation-plan]] same day as the Phase 0+1 capture below.

**Phase 4** (`new_friend_res.json`, 20 friends): every `recent_score` entry is the plain
`{time_played, score, difficulty, song_id, title}` shape, no `clear_type`/`modifier` on any of
them — confirms (not just analogizes) that the friend path cannot see clear status, matching
`from_friend_wire`'s existing tier-1 parsing exactly.

**Phase 2 attempt**: owner played a matched `TRACK_LOST`/`EASY_CLEAR` pair (`balor` PRS,
`cataclysmcry` PST) intending to isolate the bonus, but both chart slots turned out to have
unrated/TBA CC in the catalog (`song_difficulties.rating = 0`) — per
[[d-unknown-cc-no-play-rating]] neither play can produce a computable rating regardless of clear
status, so the pair can't answer the question. No before/after `rating/me` diff was taken to
confirm the plays are absent from `best_rated_scores`.

Owner then recorded a **working assumption, explicitly not live-verified** (can't test right
now): `TRACK_LOST → +0.0`, `EASY_CLEAR → +0.2`. [[potential|Potential]] §Encoding and the
investigation plan's Answer section both updated to state this as provisional, flagged for
re-verification before `clear_type != 0` is treated as a fact in any ported code.

## 2026-08-31 — 7.0 clear bonus magnitude confirmed: flat +0.2

Phase 0+1 of [[h-7.0-clear-bonus-investigation-plan]] executed via an owner-supplied
`GET /webapi/score/rating/me` capture (`best_rated_scores`, 50 entries, tier-3 own-credentials).
Residual analysis — `actual_rating − (catalog CC + base score formula)` for every entry, CC pulled
live from `song_difficulties` — landed on exactly `+0.200000` for all 50, zero exceptions, spanning
4 distinct `clear_type` values (`CLEAR`, `FULL_RECALL`, `PURE_MEMORY`, `HARD_CLEAR`), both gauge
modifiers (`NORMAL`, `HARD`), CC 10.7–12.0, and both score-formula segments. Confirms the bonus is
flat, not score/CC-scaled. Does **not** confirm the `clear_type` boundary — no `TRACK_LOST` or
`EASY_CLEAR` entries exist in a 50-best pool by construction, so "gated on `clear_type != 0`"
remains the working assumption, not proven. [[potential|Potential]] §Encoding updated with the
confirmed magnitude; investigation plan's Answer section updated; Phase 2 (one controlled
`TRACK_LOST` play) is what's left to close the boundary question.

## 2026-08-28 — Investigation plan filed for the 7.0 clear-bonus question (item 4)

New page [[h-7.0-clear-bonus-investigation-plan]]: a five-phase live-capture protocol for item 4
of [[h-7.0-potential-rework]] (the clear-status play-rating bonus), the highest-risk of the four
open 7.0 items — chosen over item 2 (the `/60` divisor, a single constant) because it's the one
that could quietly break friend-path best-50 the same way [[d-r10-impossible-friend-path]] broke
r10. Filed as its own question page rather than inline, since the protocol outgrew a subsection.
Resources confirmed: tier-3 subscribed test account, manual HTTP toolkit direct against
`webapi.lowiro.com`, second account/bot key for the friend leg. Phases: (0) confirm
`score/rating/me`'s post-7.0 shape still carries `rating` + `clear_type` per entry; (1) a free
passive residual scan against existing plays, no new plays needed; (2) controlled matched-score
clear/fail pairs across `clear_type` values and score-band boundaries; (3) isolate the bonus from
item 2's top-10 doubling by testing outside the top 10 first; (4) friend-path correlation — expect
no signal, confirm rather than assume; (5) write-up and code-change gate. Not yet executed;
nothing in `b30.py`/`b30_stat.py`/`utils/scoring.py` moves until it is. [[index|Index]] updated.

---

## 2026-08-28 — Arcaea 7.0 potential rework: DEV-STATED via official tweet; wiki rewritten, no code

Owner's initial surface report (see the earlier entry below, same day) is now confirmed at the
mechanism level by a first-party source: the official `@arcaea_en` account tweeted the 7.0
potential changes directly (https://x.com/arcaea_en/status/2091314523604955307) — filed as
[[arcaea-7.0-potential-notes]], graded **DEV-STATED** throughout (first-party, not a wire
capture). Confirmed: "Top Rated Recent Plays" (r10) removed; potential can no longer decrease
from playing (a direct consequence of r10's removal — best-N pools are monotonic, same as b30
always was); PTT now averages the **best 50** plays with the **top 10 doubled**; obtaining a
**Clear** slightly increases a score's play rating. Not stated anywhere: the resulting divisor
(guessed `/60` by analogy with the old `30+10=40`), the clear-bonus magnitude, or which
`clear_type` values count as "a Clear."

[[potential|Potential]] rewritten: the 7.0 model is now the page's primary content, and the
pre-7.0 model (b30+r10, `/40`, the recent-30 admission asymmetry, and the full 2026-07-23
replay-semantics testing) is preserved verbatim in a new §Historical section rather than
deleted — it was correct research against a mechanic that was live when it ran.
[[arcaea-potential]] (source) marked `status: superseded`, `superseded_by:
arcaea-7.0-potential-notes.md`. [[d-r10-impossible-friend-path]] and
[[h-recent-config-ptt-b30-r10]] marked `status: superseded` — r10 itself is gone, though the
*reasoning* in the gotcha carries forward as the ancestor of the open question below.
[[h-7.0-potential-rework]] rewritten from "unverified owner report" to "mechanism confirmed,
magnitudes open."

**Still open, deliberately not guessed into code**: the `/60` divisor; the clear-bonus
magnitude; whether the clear bonus depends on `clear_type` (own-credentials only) the way r10's
admission rule did — if so, best-50 inherits r10's old friend-path gap under a new mechanic, the
single highest-risk open question here. **No code changed** — `b30.py`, `b30_stat.py`, and
`utils/scoring.py` still implement the pre-7.0 model exactly as before this entry.

---

## 2026-08-28 — Arcaea 7.0 potential rework reported; investigation filed, nothing changed

Owner reports (surface-level, no wire capture yet) that update 7.0 reworded the potential
system: r10 removed; b30 → "B50" with the top 10 counted twice (~/60 divisor); wire `rating`
grew a third decimal (already fixed 2026-08-27, see below — same rework, unrelated filing);
and cleared plays reportedly earn a slightly higher play rating than a matched-score fail,
magnitude and friend-path detectability both unknown. Filed [[h-7.0-potential-rework]] with the
investigation checklist. [[potential|Potential]] carries a Manual Note pointing there.
Cross-referenced from [[d-r10-impossible-friend-path]] and [[h-recent-config-ptt-b30-r10]],
both possibly moot pending confirmation. **No code or formula changes made** — `b30.py`,
`b30_stat.py`, and `utils/scoring.py` still implement the pre-7.0 model.

---

## 2026-08-27 — PTT wire scale changed ×100 → ×1000; poller outage traced to a false-positive account deactivation

lowiro's maintenance window today changed PTT precision: `friend.rating` / `me.rating` now
arrive ×1000 (`209 → 0.209`), not ×100 — the in-game display grew a third decimal the same day.
Fixed in `arcaea/dto/friend.py` and `arcaea/dto/me.py`; `-1`-hidden sentinel unaffected. See
[[potential]].

Separately: the poller went dark all day because bot account #1 got `is_active=False`'d at
09:55:10 after a re-login attempt returned `HTTP 500` from Cloudflare (the origin was down for
the same maintenance) whose JSON body happened to contain an `error` key —
`raise_for_login_envelope` (`arcaea/errors.py`) classifies that shape as a terminal 403 credential
rejection regardless of actual HTTP status, so a transient outage was misread as "wrong password"
and the account was deactivated. `sessions/session.py`'s log line hardcodes "(403)" even when the
real status differs, and `/auth/login` response bodies are redacted from logs entirely
(`_CREDENTIAL_PATHS`), so there was no record of the real cause short of correlating the
`client.py` WARNING (status) with the `session.py` ERROR (fixed text) by timestamp. Reactivated
via re-running `seed_bot_account.py` now that lowiro is back up. Not yet fixed: the envelope
classifier still can't distinguish a real 403 from an outage's error-shaped body.

---

## 2026-08-27 — Spoiler mode: flagged versions render blurred, and default to private

`spoiler_versions` (migration `9fbd1bd80128`), `catalog/spoilers.py`, `utils/container.py`,
`ops/spoiler.py`. The owner flags a version with `/run spoiler add 7.0`; every chart whose
**effective** version matches then renders blurred and flips its command's ephemeral
default. See [[h-spoiler-is-a-render-mode]].

**Discord has no spoiler flag for rich embeds** — only attachments, `||text||` and
Components V2 items carry one. Jackets ride inside the embed, where a `SPOILER_` prefix is
ignored, and the difficulty buttons are top-level rows nothing in the classic model can
cover. So a spoilered payload is a Components V2 `Container` with `spoiler=True`, built by
**one generic `embed → container` converter**: no embed builder changed.

**Shape follows the song, blur follows the chart.** `IS_COMPONENTS_V2` can never come off a
message, so every view reachable from one message must agree on the shape —
`Rendered.container` from `song_spoilered`, `Rendered.spoiler` from `chart_spoilered`.

Ephemeral defaults moved from `False` to **unset** (`default=None`) on `/song`, `/score`,
`/calc`; `respond()` resolves unset to the payload's spoiler state, so an explicit
`ephemeral: false` still shares. `/recent` gets the blur but not the flip — it defers before
`request_refresh` says which play it is, and an ephemeral `/recent` would suppress a live
post nobody in the channel saw.

Two things fell out along the way. `/calc`'s copy of `_Rendered`/`_respond`/the inline edit
path was **deleted onto `utils/render.py`** (second duplication, so the extraction point),
which also gives calc's dead ends the 15s teardown it never had. And the empty-query `/song`
autocomplete now excludes flagged versions — it is ordered by `idx` descending, so it *was*
handing every unreleased song's name to anyone who opened `/song` and typed nothing.

Scope is rendering and visibility only: search, the `version:` filter, typed autocomplete
and **chardle answers** still reach spoilered charts. Chardle is the one open leak.

---

## 2026-08-10 — `/score` built: personal best per chart, with its b30 position

`src/coda/extensions/score.py`. Options mirror `/song` (`q` + autocomplete, `difficulty`,
`ephemeral`) and the query goes through the same `SearchService.resolve` — which
`catalog/search.py` named `/score` as a future caller of from the day it was written.

**Pure read.** No `request_refresh`, no lowiro: a personal best is history, and
`play_scores` already holds all the history there will ever be. `/recent` polls because it
asks "what did you just play"; this asks "what is your best", and a poll cannot improve
that answer.

**A query that pins no class opens the highest class the player has a SCORE on** (owner's
call), not the highest class that exists. Same rule drives the class buttons: only scored
charts get one, because a button leading to "no score" would replace a real result with a
dead end that then deletes itself.

New: `scores/best.py` (`best_play`, `scored_charts`), `b30_rank_line` in `scores/b30_stat.py`,
config key `score_rank_depth`. That key is a **second** knob rather than a reuse of
`recent_b30_stat`, and it defaults to `b30` where that one defaults to `never` — the rank
line prints a position and never a rating value, so the PTT-visibility gate `/recent`'s
impact line needs (`ObservationCache.latest_rating`, "unknown ⇒ hidden") does not apply to
it. Mode values are now a `StatMode` `Literal` shared by both lines.

Extracted on second use, not speculatively: `utils/render.py` (`Rendered`, `notice`,
`button_row`, `respond`, `apply` — the deferred-update + attachment-replacement + dead-end
teardown dance) and `catalog/autocomplete.py` (`song_choices`, with `numeric_echo=False`
for `/score`, which has no single chart to show for a level browse). `/song` was rewritten
onto both and is otherwise unchanged.

Every `score:` custom id carries the invoker (`score:c:<discord_id>:<difficulty_id>`, user
id **before** the payload since a song id may contain a colon). A click from anyone else
gets an ephemeral refusal, so no passer-by can drive someone else's lookup or spill their
own scores into it.

Updated [[scores|scores (module)]], root `CLAUDE.md`.

---

## 2026-07-29 — Split `chardle.md` and `live-updates.md` past the 300-line threshold

Both pages were flagged by the same-day lint pass (`meta/lint-report-2026-07-29.md`,
findings 6 and 7) at 437 and 602 lines respectively. Reorganization only — no new claims,
no content dropped.

**`domains/chardle.md`** (437 → overview + 3): kept the model/modes overview, build-iteration
notes, and cross-references; split out
[[chardle-clue-columns|Chardle — Clue Columns]] (column set, feedback rules, jacket and
duplicate-title identity handling), [[chardle-discord-surface|Chardle — Discord Surface]]
(the guild Chardle channel, daily scoreboard, board transport chain), and
[[chardle-mechanics|Chardle — Mechanics]] (answer pool, stats, standing rules, prototype
provenance table). Updated every inbound `[[chardle|Chardle]] §Section` reference across
`decisions/`, `gotchas/`, and `questions/` that pointed at content which moved, to point at
the correct sub-page instead (10 links across `h-chardle-closest-match-always-costs`,
`d-chardle-dead-clue-columns` ×5, `h-chardle-err-is-an-event`,
`h-chardle-puzzle-rows-not-modes`, `h-chardle-board-rendering` ×2).

**`flows/live-updates.md`** (602 → overview + 3): kept the constraining facts (§1), decisions
table (§2), copy rules, command surface, failure modes, out-of-scope list, and build/settle
history; split out [[live-updates-filters|Live Updates — Filters]] (trigger/gate algebra +
storage columns, was §3–4), [[live-updates-poster|Live Updates — Poster]] (hand-off, task
lifecycle, routing, ordering/stagger, attribution, was §5), and
[[live-updates-suppression|Live Updates — Suppression]] (`/recent` duplicate marker, set/check
rules, was §6). Updated the two inbound `§N` references that pointed at moved sections
(`questions/h-recent-duplicate-suppression.md`, `questions/h-live-update-post-filters.md`);
left the `§11`/`§12` references in `h-config-audience-declared-on-key.md` and
`h-live-update-post-filters.md` alone since those sections stayed on the overview page.

`index.md` updated for both splits (Domains table, Flows line, top-of-page summary).

---

## 2026-07-28 — `/run` BUILT; `/config global` and `/reconcile` deleted; timezone left Chardle

Same day as the design below, and it holds up: one flat `/run`, one free string, verb-first
`shlex` grammar, `config get|set|reset|list` + `reconcile` + `help`. New package `coda/ops/`
(`types`, `registry`, `config`, `reconcile`) that imports no `hikari` — an op returns text and
an optional `ConfirmAction`, and `extensions/run.py` decides how that renders. `ConfirmAction.run`
opens its **own** session: the button fires up to 60 s later, so a captured one is closed.

**Four gates, not three.** Registration in `OWNER_GUILD_IDS` turned out to be a cheaper first
layer than `default_member_permissions`, which stays as the second, with the owner-gated
autocomplete and the handler check behind it. Two mechanics found in the pinned lightbulb that
would each have silently inverted the requirement: `Loader.command`'s **second-order** decorator
drops `global_` (so `/run` is registered by function call), and `client.py:610-620` reads
`guilds=None` as "fall back to `default_enabled_guilds`" while a non-`None` empty sequence
registers **nowhere** — an unset env must therefore pass a tuple, never `None`. Also:
`AutocompleteContext` has no `user`; the invoker is `ctx.interaction.user.id`, and getting it
wrong renders identically to "no suggestions".

**Audience landed as designed, with the owner's call going further than the decision required.**
Six keys are `audience="owner"` and **none** surfaces to users — `polling` included, which the
decision explicitly permitted to stay user-readable. `/config view` now labels a value inherited
from `Scope.GLOBAL` as *"from default"* in the neutral colour: the value stays truthful, the word
"global" never appears, and `_SCOPE_COLOR/_LABEL/_TITLE[GLOBAL]` are deleted.

**`chardle_timezone` became `timezone`.** One clock decides Chardle rollover *and* day/night
jacket art, so the key is general, guild-settable, bot-default-backed. `is_night`
(`catalog/jackets.py`) took a `ZoneInfo` in place of a hardcoded GMT+7 and a `user_id` it
ignored; six render paths resolve the zone first (`poster`, `calc` ×2, `recent`, `song` ×2).
`DEFAULT_ZONE`/`parse_zone` moved to the pure `coda/utils/zones.py`, which retires the
two-literals-kept-in-step-by-comment compromise in [[h-chardle-build-time-leftovers]] §5 —
`settings/__init__` was never what `schedule` needed to import, only the zone name was.

The no-coercion bug is fixed at the same time: `settings/parse.py` `parse_value` on both write
paths, including `ZoneInfo` validation for the timezone key so a typo is refused at write rather
than swallowed by the read-side fallback. No rows needed migrating — the dev database held no
int-key rows at all. New tests: `test_config_parse.py`, `test_ops_dispatch.py`,
`test_night_window.py`. Still open: [[h-run-terminal-build-time]] item 1, the autocomplete
replacement capture, which needs a live Discord client.

---

## 2026-07-28 — `/run` owner terminal designed; the config leak was never `/config global`

Design conversation, nothing built. The ask was to delete `/config global` — it clutters
everyone's suggestion list and publishes internal parameter names — and replace it with a
`/run` command taking one free-text string, owner-gated dynamic autocomplete, terminal-like.

**The finding that reframed it.** `_KEYS_VIEW` (`extensions/config.py:25`) is built from the
whole of `REGISTRY` with no filter, and `ConfigView` (`:245`) has no permission check at all.
So `chardle_debug_board`, `chardle_epoch`, `chardle_abandon_hours` and `polling` are already
in every user's picker through `view` — deleting `ConfigGlobal` closes neither the clutter nor
the leak. The four scope subcommands filter on `settable_scopes`, which reads like a
permission filter and answers a different question (*where is this writable*, never *who
should know it exists*). Fix goes to the definition layer: [[h-config-audience-declared-on-key]]
puts `audience: Literal["user","owner"]` on `ConfigKey` and makes every user-facing
comprehension carry the predicate. Default `"user"` on purpose — forgetting yields a noisy
picker, not a silent gate.

**The surface.** [[h-owner-surface-is-run-terminal]]: one flat top-level `/run`, one string
option, verb-first `shlex` grammar (`config set <key> <value>`), flat dispatch table, one small
handler and one formatter per verb. **No scope token** (owner, mid-session): `/run config` is
bot-wide config and nothing else — every `set`/`reset` writes `Scope.GLOBAL`, `get` reads the
raw value stored there. Per-scope writes stay on `/config user|channel|server`, and `resolve()`
stays on `/config view`. `/run` replaces one subcommand's surface, not `/config` as a whole; the
knock-on is that an owner-audience key which is *not* GLOBAL-only would have no surface at all
(none exist today). The gate is **three layers and all three are load-bearing**
— autocomplete callback returns `[]` for non-owners (this is the one that closes the leak, and
the one nothing fails without), handler checks `owner_ids` (the only authority), registration
sets `default_member_permissions` (visibility only; guild admin ≠ bot owner). Verified in the
pinned lightbulb: `commands.py:88` exposes it, and `commands.py:190` **rejects it on
subcommands** — so `/run` can never become a `Group`. No shell state: slash commands are
one-shot, "terminal" describes the input box, not a REPL. Scope rule binds both ways —
internals-only behind `/run`, and anything a user would want gets a real discoverable command
instead. Per-verb formatters, never a generic dump, or [[w-sid-confined-to-sessions]] dies the
first time someone adds `session inspect`. Destructive verbs confirm via the existing
`_make_reset_menu` pattern; reads stay one-shot.

**The mechanics.** [[d-autocomplete-is-a-hint]] — free text is always submittable (the repo
already says so at `liveupdates.py:285`), a chosen row replaces the *whole* option value so
each suggestion must carry the rebuilt line, and the 100-char choice cap therefore lands on the
line rather than the token, which is what makes long grammars silently uncompletable. 25 rows,
~3s, so the partial-line parser stays pure and DB-free. The replacement semantics are stated
from docs, **not captured** — flagged on the page and tracked.

**A live bug surfaced on the way.** `set_value` (`settings/service.py:71`) writes `{"v": value}`
verbatim and the command layer validates only the tuple case (`config.py:133`), so every
`type="int"` key set through `/config` is persisted as a *string* — `chardle_bpm_window`,
`chardle_note_window`, `chardle_abandon_hours`. Defaults return ints, configured values return
strings. Not fixed; written up in [[h-run-terminal-build-time]] so `/run` is not built on top
of it.

**Three things found in the code after the shape was settled.** The audit trail must carry
`extra={"discord": False}` — `DiscordChannelHandler` posts records into `LOG_DISCORD_CHANNEL_ID`
and `RouteFilter` promotes anything above threshold, so logging raw `/run` lines the default way
republishes internal key names *and set values* into a Discord channel whose read access is a
server setting, undoing the whole change. `help` is a **required** verb, not a nicety: a single
free-text option discards every option description Discord would have rendered, which is the
only documentation a slash command has — for the owner too. And `/reconcile`
(`extensions/reconcile.py:22`) is the second command already living this problem — top-level row
in everyone's picker, "(bot owner only)" in its description, handler-only gate — which is the
argument that the category grows.

Four pages created, `index.md` updated. Open items: the autocomplete capture, where coercion
lives, the first verb set beyond `config`/`help`, DM `contexts`, and an audience call on each of
the eleven existing keys.

---

## 2026-07-28 — Chardle end-to-end review; the clue-column selector was eating two columns

Read all 17 modules of `chardle/`, the extension, the models, both migrations, and checked
every claim that could be checked against the live catalog. Seven findings, five fixed.

**The one that mattered.** `columns._informative` read
`None not in values and len(values) > 1` — "unknown *anywhere* in the pool" bolted onto the
variance rule [[d-chardle-dead-clue-columns]] actually asks for. Measured: `charter` dead on
**every** tier (41–42 Future/Present/Past charts carry no charter link, 11 Beyond, 8
Eternal), `artist` dead on all but `byd` (one chart). Its docstring justified the clause as
how err loses `level`/`rating` — **false**, err stores `-1` uniformly, so variance alone
drops both. Knock-on: eligible fillers never exceeded the budget, so the truncation never
truncated and `rng.shuffle` was a no-op — **4 board shapes per tier, forever**, against the
domain page's "the board's *shape* is itself a variable". Now 20 per ordinary tier, 40 on
extras, 7 columns every time. Relaxing step 1 needs step 2 or a column can be picked the
*answer* has no value for (every row ⬛), so `select_columns` now takes the drawn answer.
Same fix collapsed `_value(CLASS)` onto `ChartFacts.visible_class` — latent, but reading the
raw slot would call a Beyond+`byd_2` pool varied when the board shows one class.
`tests/test_chardle_columns.py` pins both halves against the live catalog.

**Also fixed.** `/chardle play`'s inline post was the one board-creating call with no
`HikariError` guard — a missing Send Messages threw out of the command; the daily path had
handled exactly that all along. The sweep closed boards without re-rendering them, leaving
"**3** of 6 attempts left" on a message that had already lost. `board._shared_names` read
`songs.name_en` while rows render the `effective()` name, so 16 per-difficulty overrides
(`Ignotus` → `Ignotus Afterburn`) could never match — now override-aware, and hoisted out of
the per-player loop the scoreboard runs it in. `_post_daily_board` retried after failing to
post in a thread *it had just created*, opening a second orphan. Two `Asia/*` UTC+7 defaults
became one zone, closing [[h-chardle-build-time-leftovers]] §5.

**Corrected against the catalog, not the code.** [[d-chardle-dead-clue-columns]] §err listed
`charter` and `side` among err's working columns: all seven err charts override charters to
empty and all seven are Conflict-side. Err runs 5 columns, not 7.

**Reported, not fixed.** Non-debug `board_embed` has no length guard while `_debug_embed` and
`_fit` both trim — an unbounded free-play board passes Discord's 4096 around ~130 guesses and
then silently freezes, the edit failing into `_refresh`'s `except`. `stats._counts_for_streak`
and `leaderboard` count a *`playing`* err daily as solved; [[chardle|Chardle]] §Stats says
**attempted**.

Untouched and verified sound: the ownership CHECKs (a channel board genuinely cannot point at
a daily puzzle), `puzzle.daily`'s rollover race, `_version_parts` comparing part-wise, the
per-board locks being on a DI singleton, and the no-`arcaea/`-no-`sessions/` import rule.
`uv run pytest` 150 passed, 2 failed — both `tests/test_discord_handler.py`, pre-existing
signature drift on `_enqueue`, unrelated. `uv run alembic check` clean.

---

## 2026-07-27 — FIXED: the Chardle channel no longer moves inline boards

Iteration 2's channel gate contradicted [[h-chardle-boards-are-channel-owned]]: both legs of
`/chardle play` were routed to the guild's Chardle channel, so one live board per channel
collapsed into **one live inline board per guild** — a board in the Chardle channel made
every other channel answer "Busy". Split the channel's two jobs:

- an **inline** board (`thread: none`) posts in the channel it was started in, anywhere;
- a **thread** parents to the Chardle channel from any invocation channel, and is **refused**
  when none is set instead of opening off the invoking channel. `/chardle daily`, which has
  no inline form, falls through to a **DM** there — owner's call over blocking it outright.

No schema change. `_parent_channel` deleted (its "or the invoked channel" fallback is exactly
what was wrong); `transport.resolve_daily` takes `parent_channel_id: int | None` and returns
the DM before the reuse branch, which would otherwise compare a thread's parent against
`None` and reach `create_thread(None, ...)`. Remembered daily threads need no cleanup: the
existing parent check in `_reusable_thread` already rejects a thread whose parent moved, and
the DM fallback drops the row. Edited [[chardle|Chardle]],
[[chardle-module|chardle (module)]], [[h-chardle-boards-are-channel-owned]] and the hot
cache. Copy: `_CHANNEL_SET` / `_CHANNEL_UNSET` / `_HELP` / `NO_THREAD` each asserted the old
routing, and `NO_TRANSPORT`'s "let me create private threads in this server" is a dead end on
the new no-channel + closed-DMs path — only an admin running `/chardle channel` fixes that
one, so `start_daily` picks the message by cause instead (below).

**Visibility gate, same session.** Parenting every thread to one channel means a player who
can't *see* that channel gets a board they can't reach — thread access is inherited from the
parent, and being added to a private thread does not override it. New
`utils.permissions.can_view` (VIEW_CHANNEL, factored with `can_send_in` onto a shared
`_has`), consumed through `_reachable(app, channel_id, member)` with the house
**only-False-rejects** contract, so a cold cache never blocks a legitimate board. The two
paths differ because their options differ: `/chardle play thread:` **refuses**
(`_CANT_SEE_CHANNEL`) since an inline board is right there, while `/chardle daily` **drops to
the DM leg**, which is why `start_daily` now takes `member` — both callers pass one
(`ctx.member`, and `interaction.member` from the scoreboard button).

That leaves the daily's dead end with three causes, and `_no_transport(configured_id,
parent_id)` picks between them: no channel set, a channel this player can't see, or a thread
genuinely tried and failed. Only the third is about thread permissions, so only the third
gets `NO_TRANSPORT`'s "give me thread perms" advice.

**The @everyone check, on top of that.** The per-member gate only fires at play time, one
player at a time, so an admin could point Chardle at a staff-only channel, pass `_can_post`
(which asks about *them*), and never learn that every ordinary member is being routed to DMs.
`everyone_can_view(app, channel_id)` answers the config-time question instead: the @everyone
role's baseline permissions, then that channel's @everyone overwrite (both keyed by the guild
id), against VIEW_CHANNEL. `/chardle channel` appends `_CHANNEL_RESTRICTED` to the
confirmation on a definite False, and `_show` re-runs it, since a channel can be locked down
long after it was set.

**It warns, it does not refuse** — "@everyone denied, Member allowed" is an ordinary Discord
server, and the check cannot see whether that role covers every player. Refusing on a signal
known to be incomplete would block correct setups, so the earlier blanket caveat in
`_CHANNEL_SET` was replaced by this conditional one: it now says something true of *this*
channel rather than a disclaimer attached to all of them.

**Untested.** `permissions.py` had no tests before this and still has none — `_has` and
`everyone_can_view` need a mocked `CacheAware` with channel, guild and role objects.
`permissions_in` underneath is pure and is the piece actually worth pinning down.

---

## 2026-07-27 — BUILT: Chardle iteration 2 — channel, scoreboard, threads, tiers

Owner feedback after first use. Migration `705ec00fbbd8`; new modules
`chardle/channels.py`, `chardle/scoreboard.py`, `chardle/sticky.py`; tests
`test_chardle_tiers.py`, `test_chardle_scoreboard.py`. Edited [[chardle|Chardle]],
[[chardle-module|chardle (module)]], [[h-chardle-boards-are-channel-owned]],
[[h-chardle-extra-pool-hides-class]], [[h-chardle-board-rendering]],
[[h-chardle-build-time-leftovers]]. No new pages.

1. **A guild Chardle channel** (`/chardle channel`, Manage Channels). One per guild —
   `chardle_channels.guild_id` is the PK, unlike the live-update *allowlist*, because the
   scoreboard needs one home. Parents every thread; hosts the daily scoreboard.
2. **Daily scoreboard** — one edited message per puzzle number, who is playing and each
   finished player's grid, plus a stateless `chardle:daily` Play button (a lightbulb `Menu`
   dies with its timeout; the scoreboard outlives restarts). Built as
   `scoreboard.build → render.scoreboard -> (Embed, File | None)`, the image-renderer seam.
   Windows resolve **per player**, since they are scoped settings.
3. **`/chardle play thread: none | public | private`** — a thread owns its own channel id, so
   several free-play boards coexist under one parent.
4. **Daily thread reuse fixed.** Reported as three threads across three tests. The inference
   off session history is deleted; `chardle_player_threads` stores the id, and reuse now
   checks the parent and unarchives.
5. **Standalone Beyond / Eternal tiers**; `extras` reads "ETR + BYD" **in the picker only**.
   Daily rotation untouched.
6. **Anyone may end a board 15 minutes after it started.**

Two traps worth remembering: `lightbulb.channel(default=hikari.UNDEFINED)` builds a
**required** option (`/config`'s optional keys have the same latent bug), and a core
`INSERT … ON CONFLICT` leaves the ORM identity map stale under `expire_on_commit=False` —
`set_channel` is a read-modify-write for that reason.

---

## 2026-07-27 — DESIGN: Chardle edge-case sweep; four manual notes baked

Third Chardle session the same day. **Nothing built.** Filed
[[h-chardle-build-time-leftovers]]; edited [[catalog|Catalog]], [[chardle|Chardle]],
[[chardle-module|chardle (module)]], [[h-chardle-boards-are-channel-owned]],
[[h-chardle-puzzle-number-not-date]], [[h-chardle-err-is-an-event]],
[[h-chardle-extra-pool-hides-class]], [[h-chardle-closest-match-always-costs]],
[[d-chardle-dead-clue-columns]]. 95 → 96 pages.

**The four owner manual notes are now baked into their pages:**

1. **Clue order is deterministic** — canonical constant sequence
   (`jacket · title · artist · level|rating · pack|version · charter · side · class · bpm ·
   note`), cap 7 counting `title`. A puzzle picks *membership* only. Confirmed against the
   archived prototype, which appended in a fixed order and rolled only membership — its cap
   leaked to 8 because the `level`/`rating` branch never checked it.
2. **err attempts derive from the pool** — `min(max(⌊N/2⌋, 1), 6)`, N = err charts, counted
   with `include_hidden=True` (err charts store `rating = -1`, which is also the delisted
   predicate, so the ordinary path counts 0) and frozen at puzzle creation. N = 7 → 3, the
   prototype's number re-derived rather than copied.
3. **`byd_2` is not a class** — it is the mechanism that lets one song hold two charts in one
   class. Players have no concept of it; they know Last has two Beyonds. The extras tier has
   **two** visible classes, and the `class` column is binary.
4. **Rollover is local 00:00 + 4 h**, default zone **GMT+7**. Lands clear of DST, which
   transitions at 02:00–03:00 local.

**Two decisions came out of the sweep itself:**

- **Dailies are private, via a private thread** (guild) or DM, never the open channel.
  Ephemeral was rejected: an interaction token dies after 15 minutes, so an ephemeral board
  cannot be edited across a daily's life. The thread is reused per (guild, player). This
  forces a schema split — `channel_id` is **ownership**, new `board_channel_id` is
  **transport**, with `CHECK (channel_id IS NULL OR channel_id = board_channel_id)`. A
  private thread is not a privacy guarantee (`MANAGE_THREADS` can join), so the reply path
  also verifies the guesser **is** `session.discord_id`.
- **The answer outranks the delisted cloak** (§Rule 0). `SearchService._chart_visible` gates
  delisted *and* err on the same `include_hidden` flag, so a song delisted after its puzzle
  was created would vanish from its own game. Naming the answer wins regardless of
  visibility; every other delisted song stays an invalid, free guess. Exact tier only — fuzzy
  would hand the win to a near-miss.

**Smaller rules settled:** puzzle numbering is calendar-derived, not a counter (a counter
closes the gaps a no-play day leaves and reports streaks that never happened); lazy creation
races resolve by re-reading the winner's row; candidates are filtered to the puzzle's
difficulty *before* resolution rules run, or rules 3 and 4 disagree about the same guess; an
attempted err daily counts as solved for the streak but skipping April 1 still breaks it;
free play shares a self-describing string (`Chardle · FTR 9 · 4/6`) since a reader with no
puzzle number has no legend; catalog FKs are `ON DELETE RESTRICT` on both puzzles and guesses;
`attempts:` ≥ 1; `/chardle play end` needs starter or `MANAGE_MESSAGES`; stale dailies close on
`/chardle daily` invocation rather than relying on the sweep alone.

Verified in this repo's env, not assumed: hikari exposes `create_thread` /
`add_thread_member`, `ChannelType.GUILD_PRIVATE_THREAD`, and the
`CREATE_PRIVATE_THREADS` / `SEND_MESSAGES_IN_THREADS` / `MANAGE_THREADS` permissions.

**Follow-up the same day — the private-thread claim is now verified**, against Discord's own
threads documentation rather than a live capture (grade **FACT (Discord docs; no live
capture)**; no test writes were made against the owner's guild). `THREAD_CREATED` (type 18)
"is currently only sent in one case: when a `PUBLIC_THREAD` is created from an older message",
and "You must be invited to the thread to be able to view or participate in it, or be a
moderator (`MANAGE_THREADS` permission)." So a private thread posts nothing in its parent and
is invisible to non-members — and the moderator clause is precisely why the reply path still
checks the guesser is the session owner. [[h-chardle-build-time-leftovers]] item 3 answered;
4 leftovers remain.

**`byd_2` promoted out of Chardle and into [[catalog|Catalog]]**, where it belongs — it is a
catalog fact, not a minigame rule. Written into §Model, the difficulty-key table, and two
Traps bullets: `byd_2` is the storage slot that lets one song hold a second chart *within* a
class, not a class of its own; classify it as `byd` on every surface that compares or displays
classes, and keep the slot distinct only where chart *identity* matters (resolution, score
mapping). The wire already agrees — it sends `difficulty: 3`, Beyond, because there is no
`byd_2` value to send.

---

## 2026-07-27 — DESIGN: guild race collapses into free play

Follow-up session on the one Chardle mode that had not been examined alone. **Nothing
built.** Filed [[h-chardle-boards-are-channel-owned]]; edited [[chardle|Chardle]],
[[chardle-module|chardle (module)]], [[h-chardle-puzzle-rows-not-modes]],
[[h-chardle-puzzle-number-not-date]]. 94 → 95 pages.

**Race no longer exists as a mode.** Every non-daily board is owned by its channel; only
dailies are owned by a user. Solo play comes from *where* the board runs — a DM holds one
human, a thread has its own channel id — not from an invoker lock. Modes: **daily / free
play / free play with filters**. `/chardle race` and `/chardle custom` both dissolve into
`/chardle play`.

**The reasoning, in the order it actually went:**

1. Race's spec contradicted itself — attempts "free" *and* "one shared attempt pool ...
   one budget". An unbounded pool is not a budget; a co-op board with unlimited attempts
   has no loss state. Fixed by making the pool finite and opt-in (`attempts:`), default
   null.
2. Racing the daily was a **stats loophole**, not merely a spoiler as the original page
   framed it. A race session carries `discord_id IS NULL`, so `UNIQUE (puzzle_id,
   discord_id)` never binds: a channel could solve the daily together and every
   participant could still log a solo 1/6. Owner dropped daily-in-race outright.
3. Asked what then separated race from free play with the invoker lock removed — answer:
   **only the budget**. Free play's session is found by `discord_id` only because the
   guesser is the owner; once anyone may guess, lookup moves to the channel and
   `discord_id` demotes to attribution, which `chardle_guesses.discord_id` already stores.
4. Owner's decisive observation: **from a player's seat the two boards are identical.**
   Same art, same flow; the only perceptible difference is whether their guess is
   accepted, discoverable by being rejected. Two commands rendering the same and differing
   by a hidden permission are not two modes. Collapse followed.

**Schema consequence worth more than the mode count.** `user-owned ⇔ daily` is now an
exact equivalence, so one constraint does the work of two plus the loophole fix:

```sql
is_daily bool GENERATED ALWAYS AS (puzzle_number IS NOT NULL) STORED  -- puzzles
FOREIGN KEY (puzzle_id, is_daily) REFERENCES chardle_puzzles (id, is_daily)
CHECK ((discord_id IS NOT NULL) = is_daily AND (channel_id IS NOT NULL) = NOT is_daily)
UNIQUE (channel_id) WHERE state = 'playing'
```

`puzzle_number` lives on the puzzle and `channel_id` on the session, so a plain `CHECK`
cannot see across the tables — denormalising `is_daily` onto both and joining through a
composite FK brings the fact into a constraint's range. Same instinct that produced the
original xor, which [[h-chardle-puzzle-rows-not-modes]] chose specifically to keep
invariants out of "service-layer etiquette".

Also noticed: `filters ⇒ stats-ineligible` is **redundant**, since only dailies have stats
and filters can only sit on a non-daily. Real eligibility is `puzzle_number IS NOT NULL`;
`CHECK (puzzle_number IS NULL OR filters IS NULL)` keeps the redundancy enforced.

**Accepted costs**, recorded so they are not re-litigated: two people cannot each hold a
board in one busy guild channel without threads; a bounded board can be griefed by one
player burning the pool; an abandoned board holds its channel slot until `/chardle play
end` or an inactivity sweep (a *lost* board frees it for free, since the partial unique
only covers `playing`).

**Still open**: whether the abandoned-board sweep reuses `expires_at` (documented today as
dailies-only) or sweeps on `started_at` age. Board rendering remains the larger open
question — [[h-chardle-board-rendering]] — and collapse adds a requirement to it: the
board must show attempts remaining when bounded, since removing the *invisible*
distinction does not by itself make the visible state legible.

Housekeeping this session: the `wiki-sync` skill was deleted at the owner's request
(`~/.claude/skills/wiki-sync/`); this entry was written by the main thread directly. Its
`wiki-writer` subagent (`~/.claude/agents/wiki-writer.md`) is now orphaned.

---

## 2026-07-27 — DESIGN: Chardle revival

Read the archived **2024** prototype (`classes/chardle.py`, 799 lines;
`plugins/chardle.py`, 77; `assets/chardle/`; the `games.chardle` block of
`assets/config.json`) and designed a revival against coda-bot's structure. **Nothing
built** — no `src/coda/chardle/`, no tables, no commands.

Filed: [[chardle|Chardle]] (domain), [[chardle-module|chardle (module)]] (planned),
[[h-chardle-puzzle-rows-not-modes]], [[h-chardle-puzzle-number-not-date]],
[[h-chardle-closest-match-always-costs]], [[d-chardle-dead-clue-columns]],
[[h-chardle-board-rendering]] (open), [[h-chardle-extra-pool-hides-class]],
[[h-chardle-err-is-an-event]]. 9 pages, 85 → 94.

**Decided this session**: all four modes (daily / freeplay / custom / race) on three
tables with no mode column; difficulty revealed, not hidden; pool = (level window,
difficulty classes) named tiers with obscurity deliberately unfiltered; `bpm` and `note`
added as arrow clues; the jacket clue column dropped; daily pinned at 6 attempts with no
free opener; streaks over contiguous `puzzle_number`; global per-user stats with a
guild-membership leaderboard filter; race shares one co-op attempt pool; daily expires at
rollover, others never.

**Findings the prototype did not know it had**:

1. Its column dice were safe only because its level window was 2–24. Named tiers narrow
   the pool, and the same roll produces a dead `level` column — filed as
   [[d-chardle-dead-clue-columns]], which also records the `pack`/`version` redundancy it
   shipped unnoticed.
2. Its `jacket` column's `get_shadow` returned `None` unconditionally — no feedback, ever.
   **Corrected later the same session** (owner): that column existed to *identify* the
   row alongside the name, which is a real job — "no feedback" is not "no information".
   The defect is cost, not purpose: identity does not need a full 220 px flex column. The
   jacket stays, narrower, and matters more than it did in 2024 because cycling can put
   two identically-titled rows on one board.
3. Its ambiguity handling was half-right: `submit` short-circuited on a candidate equal to
   the answer (good, kept), then fell through to whichever candidate the loop left bound
   and charged an attempt for the wrong comparison (filed and fixed in
   [[h-chardle-closest-match-always-costs]]).
4. `bpm_range` / `note_range` clues and their bucket tables were configured and never
   implemented. The revival takes arrows over buckets.
5. `max_attempts` was 5 in config and 10 in code.
6. Per-guild rollover and global streaks contradict as usually stated. Resolved by
   numbering puzzles instead of dating them — [[h-chardle-puzzle-number-not-date]].

**Already solved in coda-bot, so not re-designed**: `DifficultyClass.ETR` and
`Side.LEPHON` exist (the prototype's `bg_file` handled neither);
`catalog.search.SearchService` replaces its hand-rolled fuzzy matching, and its
`SongDupes` result is what raised the duplicate-title question in the first place.

**Second pass, same session — pools and the April Fools mode**, with figures queried from
the live catalog rather than assumed:

- `err` is **7 charts**, and **all 7 store `level = -1` and `rating = -1`**; only 2 carry
  a BPM. That makes three clue columns dead 100% of the time, and it retro-justifies the
  prototype's unexplained `max_attempts = 3` — with 7 answers, 6 attempts is unlosable.
  Folded into [[d-chardle-dead-clue-columns]] §err.
- `byd` 63 + `etr` 103 + `byd_2` 1 = **167 charts over 166 songs**, and **165 of those
  songs carry exactly one extra**. That 1:1 is what makes a merged "Extra" pool work as a
  guess target at all; Last is the sole exception →
  [[h-chardle-extra-pool-hides-class]].
- Delisted charts are live in the table right now: FTR `min_cc = -88`, PRS `-60`, PST
  `-35`. The negative-CC exclusion is load-bearing, not theoretical.
- err scheduling → [[h-chardle-err-is-an-event]]: guaranteed on April 1, 25% during the
  event week, **0.3%** otherwise (half the prototype's undated 0.6%), never a random
  daily. An err daily advances the streak but is excluded from the guess histogram —
  which is what lets the daily stay pinned at 6 while err runs at 3.
- The custom `err` tier is **testing scaffolding**, to be written as one removable line
  and deleted before the joke lands.

**Third pass — ambiguity cycling.** Retyping an ambiguous name now walks to the next
reading of it, folded into [[h-chardle-closest-match-always-costs]] §Cycling. It needs
**no new state**: `UNIQUE (session_id, song_difficulty_id)` was already the duplicate
rule, and it doubles as the cycling cursor, so the board is the pointer, interleaved
guesses still advance, and the sequence self-terminates through the existing free
duplicate rejection. Bounded to the exact-match tier — unbounded, a repeated
`tempestissimo` would skip past itself into the fuzzy tail and charge an attempt for a
song the player never named.

**Vault wrinkle**: the module page is `modules/chardle-module.md`, not
`modules/chardle.md`, because Obsidian resolves wikilinks by filename and
`domains/chardle.md` already claims that name. First filename collision between a domain
and a module in this vault. Link it `[[chardle-module|chardle (module)]]`.

---

## 2026-07-24 — FIXED: the friend path front-ran the own path on detail

Owner testing found live-update posts for their own tier-2 account arriving with
no note counts, health or clear type. Cause: both paths covered the account on
independently jittered keys, and the poster fires only on a first-time INSERT
(`_upsert` returns `None` on `DO UPDATE`, by design, so enrichment never
re-posts). Whichever key fired first authored the post — roughly a coin flip,
and a friend win was permanent for the message even though the DB row healed
seconds later. `ObservationCache.record` had the identical hole: its guard is a
strict `>`, so an equal-`time_played` friend sighting overwrote the detailed own
one for `/recent`.

Fix: `_friend_scores` now drops the plays of any player the own path currently
covers, via new `PlayerSessionProvider.own_covered` (reuses `_pollable`'s
`is_valid` + `is_active` predicate through `with_only_columns`, so a dead
credential hands the player back to the friend path automatically). Ratings are
still read from every friend — a PTT reading is current state, not a play.
Filter sits in the poller, not `ingest`, because the observation cache is
written before ingest is reached.

Accepted cost (owner, explicitly): a tier-2+ player finishing a second chart
inside one own-poll interval loses the first, since `/user/me` only returns the
latest. Owner's reasoning — those are mostly failed plays, and the friend path
cannot tell a hard-gauge death from a low score anyway.

Reverses the "both paths enrich one row" framing on [[scores]] and in
`service.py`'s header; the UPSERT conflict handling stays as the backstop for
the window where a player gains or loses credentials. Verified against the dev
DB: of three registered accounts exactly the one with a valid credential is
filtered out.

---

## 2026-07-24 — BUILT: live-updates poster. Score tracking is complete end to end

Implemented [[live-updates|Live Updates (poster)]] to its design, same day it
was settled. Migration `7ac31e9b0d54`: seven filter columns on
`live_update_prefs`, `min_level`/`min_grade` on `live_update_channels`, and the
`enabled` server default finally flipped `true → false` to match
`DEFAULT_ENABLED` (the repo's first `op.alter_column`).

New: `scores/filters.py` (triggers OR-ed, gates AND-ed, `PlayFacts` computing
the account-level answers once per play and sharing them across every linked
user), `scores/poster.py` (bounded queue, batch drain, routing, per-destination
dedupe and FIFO locks, embed, send), `scores/suppression.py`. Changed:
`ScoreStore.ingest` returns row ids, `poller._store` sorts by `time_played`
*before* ingest so the ids come out time-ordered, `score_embed` takes an
optional `PlayerIdentity` author line, `LiveUpdateService` gained
`floor_for`/`set_floor`/`set_filters`, `/liveupdates` gained `filters` and
`floor` and a `status` that shows both the user's filters and any guild floor.
`Grade` + `grade_of` added to `utils/scoring.py`.

Three things the design left implicit and the code had to decide:

- **Ordering vs. ids.** §5.4 wanted time-ordered batches, §5.1 wanted ids rather
  than `ScoreResult`s. Sorting *before* ingest dissolves it — `ingest` preserves
  input order, so no correlation step exists.
- **`INITIAL_DELAY` is per batch, and planning stays in the consumer loop** —
  only sends become tasks. A FIFO lock orders waiters already contending; it
  cannot reconstruct creation order, so anything that lets two plays finish
  planning out of order loses the ordering the sort was for.
- **Locale for a channel post** ([[live-updates]] §12, previously open) — the
  `locale` REGISTRY key read at CHANNEL → GUILD → GLOBAL, with the guild id
  riding along on `ChannelFloor` so it costs no extra query. DMs read
  USER → GLOBAL.

Tests: `tests/test_live_filters.py` (28) and `tests/test_post_suppression.py`
(5) — grade boundaries, strict-`>` PB, `bX` implies `pb`, `grade_up` crossings,
fail-closed level gate, floor narrowing, per-destination suppression scope.
Unchanged and still failing before this work: `tests/test_discord_handler.py`
(two tests predate a `_enqueue(ping)` signature change).

Not built, unchanged: tournaments.

---

## 2026-07-24 — DESIGN: live-updates poster + post filters settled; both blocking questions answered

Design session for the last unbuilt piece of score tracking. Rewrote
[[live-updates|Live Updates (poster)]] as the full design (12 sections, every
code claim re-read from `src/` the same day) and closed both questions that
blocked it — [[h-live-update-post-filters]] and
[[h-recent-duplicate-suppression]] moved open→answered in [[index|Index]].
**Nothing was built.**

Two premises in the existing question pages turned out to be wrong, and
correcting them shaped the whole design:

- **"Posting everything would flood a channel" is mis-scoped.** The bounding
  unit is the *player*, not the poll key: one `/friend/me` returns a play per
  friend, so a bot key can yield many plays at once, but any one account
  surfaces at most its single latest play per cycle (~40/hr at the 90 s
  default). A channel K users point at can still burst K posts — handled by the
  per-destination stagger and the guild floor, not by restricting what an
  individual may ask for. The question is what is *worth* a message.
- **`/recent` *causes* the duplicate it was accused of** — it calls
  `request_refresh`, which drives the poll cycle that ingests the play that
  feeds the poster. The duplicate follows every `/recent` that surfaces
  something new, so it is the common case, not a corner case.

A third fact belongs on the record because it is not written anywhere else:
**`play_scores` is a sample, not a log.** Plays made between two polls are never
fetched and never can be. Every filter therefore operates on observed plays, and
no copy may promise completeness.

Decisions: triggers OR-ed / gates AND-ed; triggers `all`, `pb`, `bX`, `pm`,
`fr`, `grade_up` (AA/EX/EX+, defined as beating your previous best grade on that
chart); gates `min_level` plus a per-channel guild floor, gates only — a guild
may never override triggers. Stored as columns on `live_update_prefs`, not in
`REGISTRY`. Default `pb`. b30 feeds `bX` but the aggregate is **never printed**.
Duplicate suppression keyed `(destination, play_score_id)` — which is simpler
than the question anticipated, because the poster sends once per *destination*
rather than once per linked user. That per-destination send also fixes a latent
routing bug: two users linking one account and pointing at the same channel would
have produced two messages for one play.

Also settled during the session: a live post needs its own player attribution,
since a bot-authored message has no interaction header. Discord identity (owner
link's avatar + name) via `embed.set_author`, degrading to the Arcaea in-game
name, then to no author line. Never to `friend_code`.

Rejected and recorded so it is not re-proposed: "skip the poster on on-demand
cycles". A friend-path `/recent` targets a BOT key covering every friend on that
bot account, so it would silently and permanently drop other players' updates.

---

## 2026-07-24 — FILED: `h-real-rate-limit-shape-unknown` question; trimmed `players/reserved.py` docstring

`arcaea/client.py:173-272`'s temporary rate-limit diagnostic block
(`_DIAGNOSTIC_HEADERS`/`_diagnostics`/`_is_pushback`/`_log_non_2xx`) already
self-documented its own deletion condition in a code comment but had no wiki
tracker — filed [[h-real-rate-limit-shape-unknown]], added to
[[index#Questions — open|Index]]. Left the code docstring as-is (it's
temporary scaffolding, not a settled decision — filing it as a decision page
would have misrepresented an open question as resolved).

Also trimmed `players/reserved.py`'s module docstring: its content turned out
to be fully covered already by [[w-honest-bot-code-refusal]] (bot-account
part) and [[w-local-friend-code-validation]] + `modules/players.md` +
`flows/registration.md` (easter-egg/owner parts). Docstring now points at
both decision pages instead of restating them — same move as the poll-schedule
trim below.

---

## 2026-07-24 — FILED: `d-poll-schedule-absolute-vs-phase` gotcha, promoted from `hot.md`

`PollSchedule._spread` (`src/coda/scores/schedule.py:92`) compares neighbours by
phase (offset modulo interval), not absolute due time — comparing absolutely
reintroduces a one-directional bias that walks every key's real period past
`POLL_INTERVAL`. Was documented only inline in the module docstring; now has its
own [[d-poll-schedule-absolute-vs-phase|gotcha page]], filed under
[[index#Gotchas — silent-regression traps|Scheduling]]. The in-code docstring on
`_spread` trimmed to a one-line pointer at the wiki page instead of restating the
mechanism. `hot.md`'s Active Threads note on this trap resolved.

---

## 2026-07-23 — BUILT: live updates default flipped to off; welcome embed rewritten

`src/coda/players/live.py`: `DEFAULT_ENABLED` `True → False`. Live updates are
opt-in now, not on-to-DM-by-default — answers [[h-welcome-message-update]] and
reverses the "default-on to DM" claim [[live-updates|Live Updates (poster)]]
carried since 2026-07-21 (that page's design docs are otherwise unchanged; the
poster itself is still not built).

`src/coda/extensions/register.py`: new `_send_welcome` helper drives the
post-registration embed for both link paths (code and account). The embed now
states both defaults explicitly since they now point opposite ways — tracking
on (`/tracking state:off` to stop), live updates off. When the invoking
channel is already allowlisted (`LiveUpdateService.is_allowed`), an inline
"Enable live updates here" button appears and does `set_destination` +
`set_enabled(True)` in one click; otherwise the text points at
`/liveupdates on` / `channel`. The `ProvenOverCode` keep-or-remove prompt does
not go through this embed.

Updated: [[live-updates|Live Updates (poster)]], [[registration|Registration]],
[[h-welcome-message-update]] (now answered), [[index|Index]].

---

## 2026-07-23 — BUILT: b30 backend (on-demand, no cache)

Conversation settled the four questions still blocking [[handoff-09-b30]]'s
"designed, not built" backend: cache vs on-demand (**on-demand**, no
migration — the proposed `arcaea_accounts` cache columns are rejected, not
just deferred), whether t0/manual scores participate now (**yes at the logic
level** — the algorithm is source-agnostic, only row-*creation* mechanics
stay open in [[h-manual-score-import]]), a configurable limit past 30 for a
"what to grind next" view (**yes, capped at 50**, with a
`counts_toward_b30` marker per entry so the sum stays correct regardless of
`limit`), and the return shape (**entries + TBA/unresolved exclusion
counts**, delisted stays a silent drop).

Implemented `src/coda/scores/b30.py` — `B30Service.compute`, `B30Entry`,
`B30Result`. Promoted `catalog/search.py::_is_delisted` to public
`is_delisted` (mechanical rename, 2 call sites) so `b30.py` could reuse the
existing delisted check rather than reimplementing it. Verified live against
the dev DB: an account with 35 raw `play_scores` rows reduced to 31 distinct
charts, top-30 sum matched a hand-summed check, entry 31 correctly marked
`counts_toward_b30=False`.

Filed [[h-b30-cache-stores-sum]] (decision, reusing the stub name that was
already linked from [[handoff-09-b30]]). Updated [[scores]] (new `b30.py`
row + a new section), [[potential]] (implementation-status note),
[[handoff-09-b30]] (status line + Key claims), [[h-manual-score-import]] and
[[h-recent-config-ptt-b30-r10]] (both partially answered — the storage/read
side is settled, write-side mechanics and the `/recent` config UX are not).

No command or embed built — this is the compute backend only. `/b30` is
still unbuilt.

---

## 2026-07-23 — FILED: four surface-feature questions + t0 manual-tier decision

Conversation raised four surface features to research before building:
`/recent` ptt/b30/r10 impact config, per-chart unlock display on song
ownership, a comprehensive r30 queue view, and a welcome-message content
update. Filed as [[h-recent-config-ptt-b30-r10]], [[h-r30-queue-view]]
(depends on the first), [[h-welcome-message-update]], and cross-linked the
existing [[h-ownership-blob-open-before-building]] as a second consumer for
the unlock-display item rather than duplicating it.

A fifth ask, manual score importing, surfaced a real design decision
mid-discussion: introduce **t0** (no account link at all), allow manual score
entry there, and compute b30 from it with no verification machinery — a
manual b30 is a self-facing tool, so a fake entry only misleads its own
owner. Wire data later replacing manual entries is a typo correction, not a
merge. Filed as [[h-t0-manual-tier-b30]] (decision) and folded into
[[h-manual-score-import]] (question), which keeps open whether linked
accounts get the same treatment and all storage/validation mechanics.

Nothing built yet — all five are research/discussion filings.

---

## 2026-07-23 — CLOSED (no new capture): credentials-changed-server-side was already answered

[[h-credentials-changed-server-side]] asked whether a stored credential can go stale
server-side and whether handling is adequate — turns out this was captured 2026-07-18,
*before* the question page even existed (created 2026-07-21), documented in
`src/coda/arcaea/errors.py`'s docstring and [[w-third-auth-envelope]], just never linked
back. Mechanism: dead sid → HTTP 401 `UnauthorizedError` → `SessionExpired` (one re-login
attempt) → if that re-login 403s → `InvalidCredentials` (terminal, `mark_dead`). Covers
both `BotAccount` and `PlayerCredential` via the shared adapter core in
`sessions/adapters.py`. Handling confirmed adequate as shipped — no design change, no new
research. Reminder to check existing `wiki/sources/` + `src/` docstrings before treating a
question page as unresearched.

## 2026-07-23 — ANSWERED: backfill headcount + verdict

Owner-stated: ~3 subscribed players beyond the owner (~4 total tier-3 users). Closes
[[h-backfill-worth-building]] — but the verdict flips from the source doc's original
framing because of the same-day `rating/me` capture below: against a 1-request-per-player
cost (not the originally-scoped ~250-request `song/me/all` walk), 4 users clears the bar.
Verdict: build a one-shot backfill on the cheap `rating/me` path; leave the heavy
`song/me/all` walk deferred/research-only.

## 2026-07-23 — CAPTURED: `score/rating/me` exact wire shape (b30+r10 seeding source)

Live capture (browser, subscribed account): envelope is
`{"best_rated_scores":[30],"recent_rated_scores":[10]}`, each entry a single-play
record with server-precomputed `rating` (float, cc+bonus). Confirms
[[potential|Potential]]'s "same chart occupies both pools simultaneously" claim
live (`undyingmacula` diff 4 in both, different scores/`time_played`). Updated
[[handoff-10-score-history-backfill-research]] with the exact shape — doc previously
described the endpoint abstractly ("only 30 entries", now corrected to 30+10) without
real field names. For backfill: `rating/me` is the cheap, single-request, frozen-at-fetch
b30/r10 snapshot — cheaper than walking `score/song/me/all`, right source for seeding a
new account's PTT history.

## 2026-07-23 — ANSWERED: `score/song/me/all` is a per-chart record, not a play log

Live-captured (browser, HTTP Toolkit, subscribed account) before/after diff on chart
`undyingmacula` diff `2` after a deliberately worse replay: row unchanged except
`yearly_play_count` (4→5) — no new row appeared, best-score fields untouched. Closes
[[h-song-me-all-log-vs-record]]; confirms `arcaea-auth-behavior.md` §7.5's disputed
guess. Also captured the endpoint's full query shape while testing: `difficulty`,
`page`, `sort` (`date|score|score_below_max|title`), `term` (title search); response
`value.count` is the total filtered match count, page size 10.

## 2026-07-23 — ANSWERED: unsubscribed-account failure mode for backfill endpoints

Live-captured (browser, HTTP Toolkit, non-subscribed account) `score/rating/me` and
`score/song/me/all`: both return `HTTP 400 {"success":false,"error_code":1401}`. Closes
[[h-backfill-unsubscribed-failure-mode]] — not a 403 as guessed, same code on both routes
(the "might differ per-route" caution didn't hold here). `1401` is not yet in
`src/coda/arcaea/errors.py`'s `_CODES` map; falls through to generic `ApiError` today.

## 2026-07-23 — LINT REMEDIATION (dead links)

The 2026-07-21 report's "dead links now 18 to 6 targets" was **wrong about scope**. That
remediation only ever touched [[index|Index]] and [[hot|Hot Cache]]; every body page still linked by
TITLE, and Obsidian resolves by FILENAME. A full re-scan found **104 dead links in 39
files**.

Two distinct defects, both mechanical, no prose changed:

1. **Title-style links** — `[[Potential]]` ×15, `[[Score Mapping]]` ×11, `[[Catalog]]` ×11,
   `[[arcaea (module)]]` ×9, `[[Tournaments]]` ×9, `[[Scoring]]` ×8, `[[Registration]]` ×8,
   `[[Session Lease]]` ×7, `[[Live Updates]]` ×7, `[[sessions (module)]]` ×6, plus
   `[[Score Poll Loop]]`, `[[Index]]`, `[[Hot Cache]]`, `[[Conventions]]`, `[[Ingest Queue]]`,
   `[[Overview]]`, `[[Auth & Sessions]]`. Four long H1-style targets mapped to their real
   files: `[[Decision — arcaea never imports db]]` and ``[[`src/coda/arcaea/` never imports
   `coda.db`]]`` → [[w-arcaea-never-imports-db]]; `[[Decision: Coherent Per-Account Browser
   Identity]]` → [[w-coherent-browser-identity]]; the 60-char "third session-is-dead
   envelope" title → [[w-third-auth-envelope]]. All rewritten `[[filename|Label]]`, with the
   pipe escaped `\|` inside table rows.

2. **Backticked `## Related` footers** — 104 more links across 19 files were written
   ``` `[[db]]` ```, which renders as code and puts **nothing** in the graph. This is why the
   link topology looked sparser than the prose implied. Unwrapped. `hot.md`, `log.md`,
   `index.md`, `overview.md`, `meta/`, and `wiki/CLAUDE.md` were excluded — their backticked
   links document link *syntax*.

`meta/lint-report.md` was excluded from both passes: it is a dated historical report and
its `[[...]]` occurrences are quoted evidence, not navigation. It now understates the
problem it was reporting; read [[hot|Hot Cache]] §Lint status for the current state.

Remaining unresolved links are intentional: the 6 stubs listed in [[index|Index]] §Known stubs,
plus 3 syntax examples (`[[Page]]`, `[[Page Name]]`, `[[filename]]`). **Zero orphan pages** —
every page has at least one inbound link. Page count corrected 66 → 76 in [[index|Index]]
and [[hot|Hot Cache]]; both had been stale since the `scores/` ingest.

Not addressed: the 7 unwritten module pages (`catalog`, `settings`, `extensions`, `admin`,
`approvals`, `utils`, `logging`) and MEDIUM-14 (`verified:`/`grade:` missing on
`modules/arcaea|db|players|sessions` and `flows/registration|session-lease|live-updates`).

---

## 2026-07-22 — INGEST (source: shipped `src/coda/scores/`)

Closed the largest coverage hole: `scores/` (~1040 lines, 10 files) had **no module page
and was not even listed as unwritten**. Filed from code, not from an archived source —
this slice postdates every `sources/` document.

- Created [[scores|scores (module)]], [[score-poll-loop|Score Poll Loop]],
  [[chart-resolution|Chart Resolution]]. `Score Poll Loop` leaves [[index#Known stubs]].
- Recorded the contradiction with [[arcaea-bot-db-schema]] §9: that source sketches
  separate tier-1/tier-2 play identities; shipped `service.py` uses **one** identity tuple
  for both, with `wire_play_id` as a secondary guard. Source is stale, code is right.
- Filed three things that regress silently and appear in no gotcha page yet: the
  `(xmax = 0)` new-vs-enriched test (getting it wrong double-posts every credentialed
  user's plays), `_spread` comparing by **phase not absolute due time**, and
  `resolve_chart`'s `game_song_id`-first / no-difficulty-guard order.
- `logging/` added to the index's unwritten-modules list — it was missing there too.

Both new flow pages carry `verified:` + `grade:` per [[conventions|Conventions]], which
also starts closing lint MEDIUM-14 (0/24 pages had `grade:`).

---

## 2026-07-21 — LINT + REMEDIATION

Full health check → [[lint-report|Lint Report]]. 2 BLOCKER, 8 HIGH, 6 MEDIUM, 3 LOW.
Both BLOCKERs and every mechanical HIGH fixed the same day.

- **Dead links 61 → 19.** Not typos — a link-style mismatch: pages linked by H1, Obsidian
  resolves by filename. Fixed with `aliases:` on 60 pages, `[[filename|Label]]` in [[index]],
  `\|` escaping inside table cells, and removal of path-style targets. Titles containing `/`
  were the silent failure — Obsidian reads them as paths.
- **Template comments leaked into frontmatter** on 6 files (lint found 3). Stripped.
- `questions/h-credentials-changed-server-side` claimed no owner-notification path exists;
  `players/notify.py:40` + `session.py:87` ship one. Narrowed the question to the part that is
  genuinely open (terminal `is_valid = False` vs a re-auth prompt for a *changed* credential).
- Security scan (the one check lint never ran): **clean**.
- 19 links to 7 targets remain, all real gaps, declared in [[index#Known stubs]].

Two categories are still only partially swept — duplicate detection (stopped mid-way through
`max_friend` numeric consistency) and cross-slice contradictions (one confirmed, no full
d-/w-/h- sweep). Worth a second lint pass later.

---

## 2026-07-21 — INGEST (all 16 Layer-1 sources)

Three parallel agents, disjoint folders, filename prefixes (`d-`, `w-`, `h-`) to avoid collisions.

- **Tier 1** (domain-reference, scoring, potential, score-mapping) → 4 `sources/`, 4 `domains/`, 7 `gotchas/d-*`. No internal contradictions.
- **Tier 2** (auth-behavior, api-layer, api-research-tasks) → 3 `sources/`, `domains/auth-and-sessions`, 3 `modules/`, 2 `flows/`, 6 `gotchas/w-*`, 8 `decisions/w-*`.
- **Tier 3** (db-schema, tournament-layer, all handoffs, self-hosting) → 9 `sources/`, `modules/db`, `domains/tournaments`, `flows/live-updates`, 10 `questions/h-*`, 6 `decisions/h-*`.

63 pages total. Rewrote [[index|Index]], [[hot|Hot Cache]], [[ingest-queue|Ingest Queue]].

**Findings surfaced by the ingest** (not previously written down in any source doc):

1. A **third auth envelope** exists — HTTP 401 `UnauthorizedError` from a server-side password rotation, mapped to `SessionExpired`. Captured 2026-07-18, one day after [[arcaea-auth-behavior]]'s window closes. Handled in code, absent from the "authoritative" wire doc. → [[w-third-auth-envelope|the third auth envelope]]
2. **An API-layer findings writeup (2026-07-19, since archived out of the repo) was an unfiled source.** It held eight robustness fixes that postdate [[arcaea-api-layer]]: `TransportError`, a 30s request timeout, a rate-limiter cancellation leak fix, `raise_for_login_envelope` extraction, `CHROME_VERSIONS` ceiling bump, per-friend fault-tolerant parsing, `encode_multipart` CRLF/boundary validation, last-slot placement retry. Added to [[ingest-queue|Ingest Queue]].
3. `SessionPool.place(exclude=…)` and `_MAX_PLACEMENT_ATTEMPTS = 3` (last-slot race) are shipped behavior the api-layer doc does not describe.
4. `AccountSession` (with `BotSession` + own-path `PlayerCredentialAdapter` on top) generalizes the doc's `BotSession` sketch.
5. The delisted-song / negative-CC trap was not found in any ingested source — it belongs to an unwritten `/song` handoff. Not filed; no page invented for it.

---

## 2026-07-21 — SCAFFOLD

Created the vault at the coda-bot repo root. Mode B (repository) + Mode E (research).

- Skipped `.raw/`: the source docs, `docs/`, and `src/` already are the source layer.
- Created `wiki/` with sources, domains, modules, flows, decisions, gotchas, questions, meta, _templates.
- Wrote [[index|Index]], [[hot|Hot Cache]], [[overview|Overview]], [[ingest-queue|Ingest Queue]], [[conventions|Conventions]], `wiki/CLAUDE.md`, templates.
- Nothing ingested.
