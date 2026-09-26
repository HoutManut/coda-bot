---
type: question
status: answered
blocks: []
source: spot check 2026-09-03 (handoff 13 review)
created: 2026-09-03
updated: 2026-09-05
answered: 2026-09-03
tags: [question, tournaments]
aliases: ["How long is a round's window, and what tells a player it opened?"]
---

# How long is a round's window, and what tells a player it opened?

## Answer

**Answered and built 2026-09-03.** The window is a flat **300 s**. Nothing tells a
player the window opened, because the window opening *is* the chart being named, and
that arrives as a new message in the thread.

```
window   300s      the validity window; ends early once everyone has scored
grace     60s      "Looking for scores…" — the poller catching a late-seen play
result             beat: who took the round (and, on the last, who took the match)
break     60s      a rest to read the result in; skippable by everyone Ready
reveal             beat: the chart is named, both sides pinged, the window opens
```

### The reveal is the go signal, so no other one is needed

The owner's goal was to need **no signal that valid scores are being read**. That is
satisfied by ordering rather than by leniency: a round's chart is not announced until
its break ends, and `start_ms` is the instant of that announcement. **You cannot play
a chart before you are told which one it is**, so there is no earlier moment for a
soft start to reach back to, and no gap in which a play lands nowhere.

This is why the "soft start" in the original direction was **not** built, and why
`start_ms`/`end_ms` still never move — the invariant [[tournaments-module]] records
survives intact. A leniency window was considered and rejected in conversation: it
would have let a player who ignored the board out-play one who believed it.

### It also closes chart banking

Every chart in a pick/ban match is picked *before round one opens* (`match.act` spawns
each round on the pick). Anchoring a window to its entry's `acted_at` — the literal
reading of "accept everything past the song pick time" — would let a player bank a
score on round three's chart during round one — and the banked play **is** the first
play in the window, so it locks in. Anchoring to the reveal makes this structurally
impossible.
Regression-guarded by `test_a_later_round_cannot_be_banked_during_an_earlier_one`.

### What the flat window retired

`window.py` (`duration_for`), `pool.chart_times`, `service._chart_times`, and
**decision 8's sentinel rule** (one unknown chart length in a set takes the 500 s
ceiling) existed only to size the window. All deleted, with `tests/test_tournament_window.py`.

The window can be flat because it is rarely spent: `_maybe_close_window` exits the
moment both sides have scored, so 300 s is a forfeit timeout rather than a budget.

> [!note] Updated 2026-09-05 — the early exit is no longer conditional
> This answer originally kept the early exit `first`-only behind a
> `!= ScoringRule.FIRST` guard, and carried a warning that at 300 s `best`
> collapsed toward `first` on long charts (a 4:10 chart leaves 50 s — no retry at
> all). Both are gone with `best` itself: [[h-first-score-is-the-only-rule]].
> A full set of scores ends the window, full stop, and the flat window owes no
> caveat to a mode that no longer exists.

### The break is a rest, not a navigation budget

`INTERMISSION_SECONDS` → `BREAK_SECONDS`, and the comment that justified it
("the 2t window assumes a player is already at song select") was **wrong about its own
purpose** — 300 s contains song-select time outright. Its real purpose, per the owner:
a beat to read the result in. So it runs from the round being **decided**
(`closed_at` = `end_ms + grace_ms`), never from the window shutting.

That was already the arithmetic in `_intermission_over`; what was missing was that
none of it was visible. `closed_at()` is now a named function, and reads the round's
**own** `grace_ms` rather than the next round's.

### The two gaps this page bundled

**1. Nothing told a player the window opened.** Fixed by `announce.py`: two beats per
round — `reveal` and `result` — each a **new message**, because Discord does not
notify on an edit. `Side.discord_id` comes from **`player_links`**, not the account —
many Discord users may share one Arcaea account, and `is_owner` marks "the single link
that speaks for it", so that link wins and the oldest breaks a tie. The join is LEFT: an
account with no link still reaches the board. Mentions are passed explicitly to
`create_message` so a chart title can never ping anything. Round one carries a rotated send-off (`glhf`, `gl hf`,
`have fun`, …); later rounds do not, because a greeting repeated every round stops
reading as a greeting. The match outcome rides on the final round's result rather than
arriving as a beat of its own — one moment, one message.

Beats are **owed while their stamp is NULL** (`tournament_rounds.revealed_at` /
`resulted_at`), so `service.tick` re-derives what to say from the rows instead of
trusting it was running when the transition happened. Stamped only after the message
lands, and committed per beat: an unstamped beat is re-posted next tick, whereas
stamping first would trade a duplicate for a silence. `_live_matches` keeps a **closed**
match in the sweep while it owes a beat — it leaves `LIVE_MATCH` on the same tick that
decides it, which is the tick its result is announced on.

**2. Grace was invisible and mislabelled.** `_waiting_line` printed *"Next round shortly
— press Ready to go now"* throughout grace, inviting a player to move on while the bot
was still looking for the score they had just set. `MatchView` now carries
`phase`/`phase_ends_ms`/`phase_ordinal` from one definition, `service.phase_of`, read
by the board and the chat-line Ready alike. Grace says "Looking for scores…"; the break
names the next round and counts down; **Ready is offered only during the break**.

### Ready got a second surface

The break is skipped when everyone is Ready — button, or a **word in the thread**.
`reads_as_ready` matches whole words only (`ready`, `r`, `gg`, `go`, `next`, `+`, …):
*"ready in a sec"* is the opposite of ready and *"gg ez"* is conversation. Accepted
only **during a break** — outside one there is nothing to be ready for, and a flag set
mid-window would survive into the break and skip a rest never offered.

### Naming: Discord first

`Side` carries **both** names and resolves with `Side.name` (Discord, else Arcaea). A
thread is a Discord room and people recognise each other by the name Discord shows; the
Arcaea name stays because it is whose *scores* these are, and because it is the only
name a player who joined before the Discord one could be captured has.

The Discord name is **captured on the roster row** (`tournament_participants.display_name`)
at `/tournament quick` and `/tournament join`, not looked up later: the bot runs on
`ALL_UNPRIVILEGED` intents, so `GUILD_MEMBERS` is off and the member cache cannot be
trusted. The command that put a player on the roster is the one moment their real user
object is guaranteed in hand. It goes stale on a rename; a quick match lasts minutes.

## Related

[[tournaments-module|tournaments (module)]] · [[tournaments|Tournaments]] ·
[[h-tournament-clock-skew]] · [[h-tournament-attempt-overhead]] ·
[[h-tournament-sticky-board]] · [[score-poll-loop|Score Poll Loop]]
