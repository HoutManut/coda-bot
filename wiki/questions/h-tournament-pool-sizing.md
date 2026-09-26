---
type: question
status: active
blocks: [tournaments — >2-player matches]
source: spot check 2026-09-03 (handoff 13 review)
created: 2026-09-03
updated: 2026-09-05
tags: [question, tournaments]
aliases: ["How big should a match's pool be?"]
---

# How big should a match's pool be?

## Why it was open

`match.spec_of` asked for `pickban.pool_size(best_of, roster_size)`, and that function
never read `match.pick_ban`. The pool was therefore always sized for a match that bans,
which is only sometimes what is being played.

Two of the three leftovers below are now closed. Item 2 is not, and it is the one that
would be reopened if pool size ever becomes **dynamic**.

## The leftovers

### 1. Bans off draws two charts it never plays — ANSWERED 2026-09-05

`pool_size` now takes `pick_ban`, and head-to-head with bans off returns `best_of`: the
pool IS the round list, so nothing is drawn that is never played and the board has no
permanent leftovers to mark. The refusal it was causing is gone with it — level 12 has
exactly two charts in the catalog, and a bans-off Bo1 or Bo2 there now runs instead of
being told it needs three or four.

Surfaced twice, because a shortfall was reaching nobody:

- `/tournament quick` refuses **before it opens a thread**, which is what
  [[handoff-13-tournaments|handoff 13]] specified all along and what had never been
  built. Joining only relaxes the requirement (above two players there is no pick/ban),
  so a pre-flight pass stays valid for the life of the draft.
- A shortfall discovered at start time is posted **into the thread** and clears every
  Ready. It used to go back ephemerally to whoever clicked last, and from the chat-word
  Ready path (`_on_message`) it was dropped on the floor entirely — the match sat in
  `draft` with everyone marked ready under a prompt still asking for Ready, which is the
  whole of what "it just hangs" looks like.

### 2. Above two players the format is printed but not played — STILL OPEN

`_rounds_without_pickban` makes the whole pool **one** round's chart set when
`roster_size > 2`. The board still says `Bo3`, the score line still counts rounds won, and
`wins_needed(3) == 2` is unreachable because only one round exists. It closes correctly —
`_finished` takes the "nothing left to play" exit and `_winner` hands it to the single
round's winner — but `best_of` there means "how many charts are on the table", and nothing
on the surface says so.

A surface problem, not a sizing one, which is why item 1's answer did nothing for it.

### 3. A level bound of `0` reads as an empty catalog — ANSWERED 2026-09-05

`levels._BOUND` is now `^[1-9]\d?\+?$`, so `0` is refused as a level instead of encoding
to `0` and being excluded by `qualifying`'s TBA guard. `99` still parses: it draws nothing
today but is not *wrong*, and a hard cap would have to be moved the day the game adds a
level above 12.

## What is left to answer

Only item 2, and only on the surface: whether a >2-player match should stop printing
`Bo{n}` for something that is one round of `n` charts, or should actually play `n` rounds.

## Related

[[tournaments-module|tournaments (module)]] · [[tournaments|Tournaments]] ·
[[handoff-13-tournaments|handoff 13]] · [[h-tournament-sticky-board]]
