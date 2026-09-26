---
type: question
status: open
blocks: [chardle]
source: design conversation 2026-07-30
created: 2026-07-30
updated: 2026-07-30
tags: [question, chardle, unbuilt, transport, rendering]
aliases: ["What should Chardle's daily relocation and public-board modes look like?"]
---
# What should Chardle's daily relocation and public-board modes look like?

## Why it is open

Raised in the same conversation as a 2026-07-30 fix to the resume message on that transport
decision ([[h-chardle-boards-are-channel-owned]]): once a daily opens in DMs (no guild channel
configured yet), it stays there for the rest of that day even if the guild sets a channel
afterward — an already-posted board can't be moved. That fix only made the bot say so honestly
(`_resume` in `extensions/chardle.py` now flags a stale-DM board and fixes the message link);
it didn't change the behavior. Four related, unbuilt ideas came up in the same breath. None
designed yet.

## The ideas

### 1. Player-initiated relocation, while unbeaten

Today the transport is decided once, at `start_daily` (`extensions/chardle.py`), and never
revisited — `_daily_flow` resumes an existing `PLAYING` session at its original
`board_channel_id` unconditionally (`session.py`'s `daily_of`). The idea: while the daily is
still unsolved, let the player themselves move it — e.g. from DM to the guild's now-configured
channel/thread. Moving would need to re-point `board_channel_id` (and re-post or move the
message; Discord has no cross-channel message move) and, per the idea, carry the *result*
destination with it — so if you relocate before finishing, your finish posts/renders in the
new location instead of the old one. Once `WON`/`LOST`, presumably frozen — no idea yet on
whether relocating after finishing is in scope.

**Open:** the command/UI surface for triggering a move, what happens to the old message
(delete? leave a pointer?), whether relocation is one-shot or can ping-pong, and how it
interacts with `_remember_transport`'s thread bookkeeping in `chardle/channels.py`.

**2026-07-30 refinement, scope widened past "while unbeaten":** even a player who already
finished their daily elsewhere (e.g. DM, no guild channel configured yet at the time)
should have that result render onto a guild/channel's daily board once they touch that
daily there — via either entry point into `start_daily` (`extensions/chardle.py:217`,
shared by `/chardle daily` and the scoreboard's Play button per its own docstring). The
board message itself still can't move (Discord has no cross-channel move, same
constraint as above) but the *sticky scoreboard* (`_sticky_after` → `sticky.refresh`,
`extensions/chardle.py:787`) currently only updates off a fresh `Accepted` outcome — a
session whose `guild_id` was `None` at finish time never gets folded into a guild's
board even if the player later opens that guild's daily and hits an
already-`WON`/`LOST` state. That path needs to trigger the same sticky refresh on
finished-session resume, not just on a live guess.

**Built 2026-07-30** — see [[h-chardle-cooldown-and-attribution]]. Only this refinement;
the original "while unbeaten" relocation ask above (command/UI surface, message-move
semantics, one-shot vs ping-pong) is still unbuilt and is the one thing keeping this page
open.

### 2. Guesser attribution on channel/public-thread boards

A free-play board in a channel or public thread is one shared session
(`session.py`'s `open_free`) — multiple people can guess into it, but the rendered board
(`render.py`) has no per-row indication of *who* made which guess. The idea: render the
guesser's avatar next to (or on) each row so a shared board reads as a group effort instead
of an anonymous grid. Only makes sense for the shared modes (channel/public thread), not a
daily (single-owner, avatar is redundant) or a private thread (same).

**Open:** where the avatar sits given the existing column/jacket layout questions in
[[h-chardle-board-rendering]] — this is one more claimant on horizontal space in whatever
renderer that page settles on.

**Correction:** the DB question above is answered, not open — `ChardleGuess.discord_id`
(`db/models/chardle.py:211`) is `nullable=False`, populated on every guess in
`_record` (`guess.py:245`). Per-guess attribution data already exists; the "no avatar"
call below is a rendering/product choice, not a data-availability constraint.

**2026-07-30 decision: no, not on the board itself.** Rendering per-guess attribution into
the image (`render.py`) is out. Attribution instead comes from the command response: `/chardle
guess` (`Guess.invoke`, `extensions/chardle.py:676`) should say *which chart* was picked in
its reply text (today `_apply_guess` just returns generic "Guess recorded." / "Solved it." /
"That was the last attempt." — no chart name, see `extensions/chardle.py:774-784`) and should
stop being ephemeral (`ctx.defer(ephemeral=True)` at `extensions/chardle.py:689` — deferred
ephemeral locks the follow-up `ctx.respond` to ephemeral too). Non-ephemeral is the point: on
a shared channel/thread board, other players seeing "so-and-so guessed Fracture Ray Song" in
the channel *is* the attribution, no avatar needed. (Checked: nothing today actually deletes
a guess or the player's message — `_on_reply`, `extensions/chardle.py:1151`, only reacts
🔍/❌ on `Invalid`/`Duplicate`/`Searched` — so "don't delete their guess" and "stop being
ephemeral" are the same fix said two ways: an ephemeral reply *reads* as vanished to the rest
of the thread even though nothing server-side was removed.) Was open: whether non-ephemeral
should be conditional on board kind (daily boards are single-owner — a non-ephemeral reply
there just leaks the guess to onlookers with no attribution upside) or unconditional on the
command.

**Built 2026-07-30, unconditional** — see [[h-chardle-cooldown-and-attribution]]. Every
board kind drops ephemeral and names the chart in the reply, dailies included.

### 3. Round-robin mode for public thread — dropped, replaced by a guess cooldown

Originally: a turn-order variant of free play, players take turns instead of anyone guessing
anytime. Two things killed it as designed:

- **No roster exists to take turns with.** Free-play (`open_free`, `session.py:87`) has zero
  join/participant concept — grepped the whole `chardle/` package, nothing. The only way to
  derive an order without new schema was "next-up = fewest guesses so far on this session,
  tie-broken by earliest `ChardleGuess.created_at`" (`db/models/chardle.py:211,213` already
  carry `discord_id` + `created_at` per guess, no migration needed) — which does resolve the
  original "join order? first-guesser-first?" question to first-guesser-first, but only solves
  *whose turn*, not the harder problem below.
- **Shared pool + strict turns starves latecomers.** `puzzle.max_attempts` (`guess.py:261`) is
  a session-global ordinal, not per-player (`uq_chardle_guesses_ordinal` in
  `db/models/chardle.py:196` is unique per `session_id`, full stop). With a fixed pool and
  strict rotation, attempts < players-in-queue means whoever's late in the rotation gets zero
  turns before the board ends — order-dependent unfairness with no good fix that doesn't also
  reopen idea #4.

**2026-07-30 decision: replaced by a per-session guess cooldown, no turn order at all.**
Free-play stays free-for-all by default, switchable via a `Play` command option and mid-round
(no reseed needed — see why below). Rule: after any **accepted** guess, the next accepted
guess that come from a **different** `discord_id` than the last one **must** wait out a cooldown
window. Same person going twice in a row is *never* blocked — no timing check applies to
their own consecutive guesses at all.

**Build-pass correction, same day:** the "switchable via a `Play` option" framing above was
dropped before build — the same-person exemption already makes the cooldown free on a
genuinely solo board, so a toggle would have added a command option and session-state field
for a case that self-resolves. Shipped always-on instead; see the "Scope" bullet below and
[[h-chardle-cooldown-and-attribution]].

Mechanics:
- Enforced in `_apply_guess` (`chardle.py:734`), before `guesses.submit` — look up the
  session's last **Accepted** guess (`discord_id` + `created_at`, both already columns, no
  schema change). If it's a different `discord_id` and within the window, reject.
- Needs one new `Outcome` variant in `guess.py` alongside `Invalid`/`Duplicate`/`Searched`
  (all of which already cost nothing and skip `_record`, `guess.py:30-64`) — e.g.
  `Cooldown(remaining: float)` — so a blocked attempt doesn't burn an ordinal slot.
- The clock only advances on **Accepted** guesses — an `Invalid`/`Duplicate`/`Searched`
  attempt produced no row, nothing to race against, so it shouldn't extend anyone's wait.
- **Scope: every session kind, not just non-daily.** Originally reasoned "gate on
  `not session.is_daily`" (solo daily = no race to guard against) — wrong assumption. Private
  free-play threads can carry multiple invited players (a private thread isn't the same thing
  as a daily — `Play`'s `thread` option opens one via `open_free`, same as a public thread,
  just less visible), so `is_daily` was never the right signal anyway. Because same-person
  guesses are always exempt, applying the cooldown universally costs nothing on a genuinely
  solo daily (the "last guess" is always the same person, rule never fires) and correctly
  covers a private free-play thread with several guessers without needing a special case.
  Note this is orthogonal to, and doesn't loosen, the existing hard lock that only a daily's
  *owner* may guess on it at all (`Guess.invoke` "Not yours" at `chardle.py:700-701`;
  `_on_reply` at `chardle.py:1181-1182`) — invited friends in a daily's thread still can't
  guess today regardless of cooldown. Whether that lock should ever loosen for co-op dailies
  is a separate, still fully open thread, not touched by this decision.
- Turn-order-style stalls (idea #3's original "skip/timeout" open question) don't apply
  anymore — nothing requires a *specific* person to act, so there's no queue position to get
  stuck on.

**Was open:** the cooldown length. Long enough that two Discord round-trips genuinely can't
land inside it (a couple seconds covers real network races), short enough it doesn't strangle
a fast group's pace — no data yet, needs an actual playtest rather than a guess.

**Built 2026-07-30, 3 seconds** — see [[h-chardle-cooldown-and-attribution]]. Picked as a
starting number, not a playtested one; still worth revisiting once there's real multi-guesser
usage to watch.

### 4. Per-player guess budget — dropped

Originally: give each player their own attempt budget instead of one shared pool, so
exhausting the shared pool (or one talkative player burning it alone) doesn't lock others out.
**2026-07-30 decision: dropped**, superseded by #3's cooldown — the cooldown paces the
*shared* pool in time rather than rationing it by headcount, which sidesteps per-player
budgets' fairness problem without new per-`(session, discord_id)` counting or a
remaining-budget UI.

Also surfaced a real ceiling either design would've had to live under: `Play.attempts`
defaults to `FREE_ATTEMPTS = 8` and caps at `MAX_FREE_ATTEMPTS = 12` (`tiers.py:25-26`,
`chardle.py:496`) — daily is fixed at `DAILY_ATTEMPTS = 6` (`tiers.py:20`). This isn't a
balance number for group play, it's the board's row count: `ordinal = len(played) + 1`
(`guess.py`) tracks 1:1 with rendered rows, and `session_id`+`ordinal` is unique
(`db/models/chardle.py:196`) — so `max_attempts` **is** how many rows `render.py` ever has to
draw, a rendering-cost ceiling, not a difficulty dial. Per-player budgets would've had to
divide that fixed 12-row ceiling by headcount (a 6-player game giving everyone 2 guesses) —
thin, and degrading exactly as more people join, the opposite of the intended feel. A
cooldown-paced shared pool doesn't have that problem: a bigger group just burns the same 12
rows faster in wall-clock time, nobody's mathematically rationed out. If 12 ever needs to grow
for group play, that's a `render.py` per-row-cost question (can it draw fewer/older rows,
paginate, etc.) — nobody's looked at that cost yet.

## What would answer it

Four ideas came in. Status after the 2026-07-30 design pass, built the same session (see
[[h-chardle-cooldown-and-attribution]]):

- **#1 (relocation):** two parts. The refinement — fold a finished-elsewhere daily into a
  guild's scoreboard on resume — is **built**: `sticky.refresh` now fires from the
  `existing is not None` resume branch (`chardle.py`'s `start_daily`) when `guild_id is not
  None` and `existing.state is not PLAYING`. The original ask — a player relocating an
  *unbeaten* daily's transport mid-game — is **still unbuilt**, still fully open (command/UI
  surface, message-move handling, one-shot vs ping-pong all undesigned).
- **#2 (attribution):** **built** — chart name in the guess reply, `ephemeral=True` dropped,
  unconditionally across every board kind.
- **#3 (races) + #4 (fairness):** **built** — collapsed into the guess cooldown, 3 seconds,
  universal, no toggle. Separately, whether dailies should ever support invited co-guessers
  remains unrelated and untouched, still fully open.

Only idea #1's original relocation ask (and the tangential daily-co-guesser question inside
#3) are still open — everything else on this page is shipped.

## Current best guess

See "What would answer it" above. #2, #3/#4, and #1's finished-daily-resume refinement are
built. What's left is idea #1's original relocation-while-unbeaten mechanism — no concrete
direction yet on the command/UI surface.

## Answer

**Partially answered, 2026-07-30** — attribution, guess cooldown, and the finished-daily
sticky-refresh refinement shipped same day, see [[h-chardle-cooldown-and-attribution]]. Still
open: idea #1's original relocation-while-unbeaten ask (the sole reason this page stays
`status: open`), and the tangential daily-co-guesser question surfaced inside #3.
