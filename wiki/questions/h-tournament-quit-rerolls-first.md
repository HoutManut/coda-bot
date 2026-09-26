---
type: question
status: open
blocks: [tournaments]
source: owner, 2026-09-04
created: 2026-09-04
updated: 2026-09-05
tags: [question, tournaments, scoring, design]
aliases: ["Quitting doesn't submit — so what stops `first` from being a reroll budget?"]
---

# Quitting doesn't submit — so what stops `first` from being a reroll budget?

## Why it is open

`first` exists to make a round one attempt. It does not: **it binds the first
*submitted* score, and a quit submits nothing.** A player who bails out mid-chart pays
only the restart, keeps a clean sheet, and the round waits for them.

[[tournaments|Tournaments]] §The first score counts states *"Retrying: pointless"*.
That is true of a **completed** play and false of an abandoned one, which is the whole
of this page.

### What the flat 300 s actually buys

Rerolls fit whenever `W - t - o >= q + o`, i.e.

```
rerolls ≈ floor((W − t − o) / (q + o))

W = 300s window   t = chart 100–189s   o = select→load→results 20–40s   q = where you bail
```

At `t = 150`, `o = 30`, `q = 5` that is **three**. The [[h-tournament-attempt-overhead]]
estimate is unmeasured, but no value in its range makes the count zero.

Three things make it worse than a plain three-attempt rule:

1. **The early exit does not cap it.** `_maybe_close_window` needs `all_scored` — *both*
   sides. An honest opponent submitting does not close the window, so the player who is
   rerolling holds it open to `end_ms` unilaterally.
2. **The board shows the target.** `viewbuild._result` builds standings for any round
   past `PENDING`, so an **open** round renders live scores. The reroll is not blind —
   it is retry-until-you-beat-the-number.
3. **It is asymmetric information.** The budget goes only to players who know a quit
   does not submit. An honest three-attempt rule everyone can read would be fairer than
   this.

### No window duration closes it

Excluding a reroll needs `W <= t + o + q_min`; admitting an honest play needs
`W >= t + o_max`. Since `q_min` is about a second, both hold only if overhead is
near-deterministic — and overhead is song-select navigation on someone else's device.
**Sizing the window is the wrong instrument**, which is also why going back to
`clamp(2t, 200s, 500s)` ([[h-tournament-window-and-clock]] retired it) fixes nothing:
`2t` was a *wider* budget, not a tighter one.

## The proposal — co-submission bands

Stop measuring *"did you have room for two plays"* and start measuring *"is this the
same play they made"*.

> **Band.** The first valid `time_played` inside `[start_ms, end_ms]` opens a band of
> `x` seconds. The round is decided on what is in that band. A side with no score in
> the band scores nothing.

**Completeness is deliberately not required.** If a band had to contain everyone, one
player could quit every attempt and force a scoreless draw. Letting the anchor close
the round for everybody makes quitting a **forfeit**, which is what `first` wanted.

| Situation | Outcome |
|---|---|
| Both play it out | Both submit together, both in the band — normal round |
| One quits to reroll | Opponent's submission anchors; the retry lands `t + o` later, outside → the quitter loses |
| Both quit (mutual reroll) | No submission, no band, they go again. Consensual and symmetric — allowed |
| Nobody ever submits | No band by `end_ms` → scoreless round, exactly as today |

### Link Play is what makes it safe

_(OWNER-STATED, 2026-09-04.)_ **Link Play** is Arcaea's in-game room: up to 4 players,
same song, **charts may differ per player**, and every score **submits at the same
time — including a hard death.**

That last clause is load-bearing. Solo, the anchor is a weapon: a hard-gauge loss
submits seconds in ([[d-hard-gauge-early-submit]]), so a player could die on purpose,
anchor the band, and drop an honest full-length run outside it. Inside a room that is
impossible — the death submits with everyone else's.

It also means **the bot never has to detect the room.** `play_scores` carries no
link-play marker and the wire offers none; **simultaneity is the signature of Link
Play**, so the band tests for the room by testing for what the room produces.

### The go signal this requires

The reveal stops being sufficient. [[h-tournament-window-and-clock]] settled *"the
reveal is the only go a match needs"* on the strength of a loose window; under a band
the first submission decides for everyone, so a player still opening Discord can lose
before reading the chart name.

**Roll call:** the reveal names the chart, and `start_ms` is set when every side
confirms it is in the room (button in the thread; timeout → forfeit). Still strictly
after the reveal, so chart banking stays structurally impossible — the property that
anchoring to the reveal was chosen for is kept.

### Sizing `x`

`x` covers submission jitter and server-side timestamp assignment only — **not** song
select, which the roll call has already absorbed. **10–15 s** is generous for a room.
Differing charts do not widen it: difficulties of one song share its audio length, so
the room still submits together.

> [!note] The band is skew-proof
> Both timestamps come from lowiro's clock, so bot↔lowiro skew **cancels**.
> [[h-tournament-clock-skew]] would then bind only the outer window, where it was never
> close to mattering.

### What it changes elsewhere

- `end_ms` becomes a genuine forfeit timeout and the anti-banking anchor, nothing else.
- `_maybe_close_window` closes on *"the band closed"* rather than on all-scored. (The
  `ScoringRule.FIRST` guard this originally proposed removing is already gone —
  [[h-first-score-is-the-only-rule]] retired the parameter outright.)
- Open-round scores should stop rendering on the board regardless — there is no reason
  to publish a live target.

### What it costs

- **A dropped connection mid-song is a lost round**, not a retry. Nothing in-band
  distinguishes it from a rage-quit, and it should not try to; the escape hatch is an
  agreed round replay.
- **Solo/async play stops working** at `x ≈ 15 s`. If it must be supported, that is a
  per-tournament switch (room vs async) where async keeps today's window — **not** a
  wider `x`, which reopens the reroll budget and restores anchor poisoning.

## What would answer it

Owner sign-off on three things, in this order:

1. Is a quit-to-reroll a rule violation to close, or a tactic to leave alone? Everything
   below is moot if it is allowed.
2. Is **in-room play mandatory** for a quick match? The band is only fair if it is.
3. `x`, and whether the roll call is a button, a chat word (`reads_as_ready` already
   exists), or both.

Then: measure real submission spread inside a Link Play room over a handful of rounds —
that is the only number `x` actually depends on, and it is cheap to capture.

## Current best guess

Bands plus a roll call, `x ≈ 15 s`, in-room mandatory. It is the only formulation found
that closes the hole, because it is the only one that stops sizing a window.

## Answer

Not yet answered. Nothing is built; [[tournaments-module]] is untouched.

## Related

[[tournaments|Tournaments]] · [[tournaments-module|tournaments (module)]] ·
[[h-tournament-window-and-clock]] · [[h-tournament-attempt-overhead]] ·
[[h-tournament-clock-skew]] · [[d-hard-gauge-early-submit]] ·
[[h-every-valid-score-counts]] · [[h-first-score-is-the-only-rule]] ·
[[scoring|Scoring]]
