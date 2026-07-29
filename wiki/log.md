---
type: meta
title: "Log"
status: active
created: 2026-07-21
updated: 2026-07-29
tags: [meta, log]
aliases: ["Operations Log"]
---

# Operations Log

Append-only. Newest entry at the TOP.

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

Read the archived **Tenniel** prototype (`classes/chardle.py`, 799 lines;
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
