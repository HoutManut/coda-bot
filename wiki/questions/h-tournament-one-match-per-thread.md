---
type: question
status: open
blocks: [tournaments — /tournament quick, _match_here]
source: spot check 2026-09-03 (handoff 13 review)
created: 2026-09-03
updated: 2026-09-03
tags: [question, tournaments]
aliases: ["What does a thread's match mean when a second one is started in it?"]
---

# What does a thread's match mean when a second one is started in it?

## Why it is open

A quick match reuses its crew's thread — that is the feature, and the reuse key *is* the
roster. But `/tournament quick` never checks whether a match is already **live** in the
thread it is about to reuse, and `_match_here` resolves a thread to its match with:

```python
select(TournamentMatch)
    .where(TournamentMatch.thread_id == int(ctx.channel_id))
    .order_by(TournamentMatch.id.desc())
    .limit(1)
```

So running `/tournament quick with:@bob` while the previous match against bob is still
`playing` creates match #2 in the same thread, and #1 becomes **unreachable**: `join`,
`leave`, `start`, `cancel` and `board` all resolve to #2. Match #1 keeps ticking in the
sweep, keeps editing its board, and there is no longer any command that can cancel it.

Owner assessed this as major and deferred it 2026-09-03.

## Why the obvious answer does not settle it

"Refuse when a live match exists" is probably right, but it decides something the module
has not decided elsewhere: whether a thread is a **room** that holds one match at a time,
or a **history** that accumulates them. The crew-thread design leans history — the thread
is explicitly the crew's record, reused across matches, and `remember_crew` binds it at
roster freeze precisely so it names the crew that actually played. A room-shaped rule sits
oddly on top of that unless it is stated.

It is also the same failure as [[h-tournament-sticky-board]] item 2 seen from the other
side: an orphaned object in a thread that still responds to input because everything here
is deliberately stateless. Worth settling the two together.

## What would answer it

An owner call on the rule, then the guard. Both readings are cheap to implement:

- **Room** — `Quick` refuses when `_match_here` returns a match in `draft`, `pickban` or
  `playing`, naming the live one and pointing at `/tournament cancel`.
- **History** — the thread holds a stack, and every verb takes the newest *live* match
  rather than the newest match, so a closed #1 stops shadowing nothing and a live #1
  cannot be shadowed by #2 at all.

## Current best guess

Refuse. One thread, one live match, unlimited finished ones — which keeps the thread a
history for reading and a room for playing, and needs no change to any verb but `quick`.
Marked as a guess.

## Answer

Unanswered.

## Related

[[tournaments-module|tournaments (module)]] · [[tournaments|Tournaments]] ·
[[h-tournament-sticky-board]] · [[handoff-13-tournaments|handoff 13]]
