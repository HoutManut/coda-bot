---
type: question
status: open
blocks: [tournaments — _playable, /tournament leave; scores/service.py record()]
source: spot check 2026-09-03 (handoff 13 review)
created: 2026-09-03
updated: 2026-09-05
tags: [question, tournaments, scores]
aliases: ["Should score tracking gate a match?"]
---

# Should score tracking gate a match?

## Why it is open

**Owner ruling 2026-09-03: no.** Tracking should not be a condition of playing. The bot
already reads an untracked player's scores into memory for `/recent`, and tournaments
should adopt that path rather than refuse the player.

Today `extensions/tournament.py::_playable` refuses on registration **or**
`tracking_enabled=False`, at both `quick` and `join`. Its reasoning is sound as far as it
goes — `ScoreService.record` is the single choke point where the opt-out is enforced, so an
untracked participant's plays never reach `play_scores` and they would rank "no score" for
a whole match — but it answers that by removing the player instead of the assumption.

## The plain bug, ruling aside

`/tournament leave` routes through `_playable`:

```python
if problem is not None or not await match_ops.leave(db, match, account.id):
    await _say(ctx, "Not in", "You weren't on the roster.")
```

A player who joins and *then* turns tracking off is told **"You weren't on the roster"**
and cannot leave. Leaving needs neither the registration check nor the tracking one — it
needs the account id. Worth fixing whether or not the ruling lands.

## Why adoption is not a read swap

`ObservationCache` (`scores/observations.py`) is **latest-play-only**: one `ScoreResult`
per `arc_user_id`, `TTL = 300.0` seconds, in memory, no restart survival. `/recent` can use
it because `/recent` wants exactly one play.

`results.standings` is a SQL query over `play_scores` that needs **every** play an account
made inside a 200–500 s window — to find the earliest, and in song mode to know *which*
difficulty was played. The cache cannot answer that, and a restart mid-round would lose
the round.

So the adoption is not "read the cache in `results.py`". The likely shape is the opposite:
make a live round a **persistence exception** at `scores/service.py`'s choke point, so an
untracked account's plays are recorded while it is in an open round and not otherwise.
That is a real policy change and needs deciding explicitly:

- Does joining a match **consent** to storage for its duration? A tournament is public
  performance, which is a decent argument that it does.
- What happens to those rows when the match closes — kept as match history, or deleted?
  `play_scores` is `ON DELETE RESTRICT` on the account precisely because the history is
  irreplaceable, so "delete after" is not free.
- Does the player get told? An opt-out that silently stops applying is worse than one that
  refuses.

## What would answer it

The consent decision above, and then one of two builds: the persistence exception at
`record()`, or a per-round in-memory store owned by `tournaments/` that survives long
enough for a window plus grace and is reconciled into `play_scores` only for tracked
accounts.

## Current best guess

Persistence exception at `record()`, gated on `cadence.hot_accounts`-style membership,
plus a line on the board or in the join reply saying that plays during a match are
recorded. It reuses the one choke point rather than adding a second store, and the module
already computes "who is in a live round" for the poller. Marked as a guess.

## Answer

Unanswered.

## Related

[[tournaments-module|tournaments (module)]] · [[scores|scores (module)]] ·
[[tournaments|Tournaments]] · [[score-poll-loop|Score Poll Loop]]
