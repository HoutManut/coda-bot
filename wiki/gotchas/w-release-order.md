---
type: gotcha
status: active
severity: medium
area: wire
verified: 2026-07-21
created: 2026-07-21
updated: 2026-07-21
tags: [gotcha, wire, pool, straying]
aliases: ["`SessionPool.release` must unfriend before clearing `bot_account_id`"]
---

# `SessionPool.release` must unfriend before clearing `bot_account_id`

## Symptom

An account that strayed (its last `/unregister`) shows `bot_account_id = NULL` in the
database, but lowiro's live friends list for that bot account **still holds them** — the
bot's own bookkeeping says the slot is free while it is not. The next `place()` call may then
try to add a genuinely new player onto an account it believes has room, and lowiro answers
`602 AlreadyFriend` for what looks like a fresh registration — exactly the drift the 602
recovery path exists to clean up, but avoidable in the first place.

## Cause

Releasing a friend slot is really two separate operations: telling lowiro to unfriend the
player (`POST /webapi/friend/me/delete`), and clearing our own `bot_account_id` pointer. If
the pointer is cleared **first**, and the unfriend call then fails or the process crashes in
between, the two facts disagree in exactly the direction that causes damage: our accounting
believes the slot is free (and will happily hand it to someone else) while lowiro still
holds the friend, so the live friend count for that bot account is one higher than expected.

## The wrong fix

Clearing `bot_account_id = NULL` first "to be safe" (on the theory that if the unfriend call
then fails, at least the DB reflects the player as unlinked from any bot) is backwards. It
optimizes for the DB looking clean over the DB matching lowiro's actual state, and the
capacity check in `pool.py::_capacity` counts friends from the **live** `/friend/me` response
— so a prematurely-cleared pointer does not even buy the DB-cleanliness it was chasing; it
just creates silent drift that the pool discovers later, the hard way, via a spurious 602.

## The right handling

`src/coda/sessions/pool.py::SessionPool.release` — unfriend by `arc_user_id` **first**, via
`session.call(endpoints.remove_friend, account.arc_user_id)` (note: `remove_friend` takes
the arc `user_id`, not the friend code — the same add/delete asymmetry as everywhere else in
this API). Only after that call succeeds does it set `account.bot_account_id = None`. If the
unfriend call raises `ArcaeaError`, `release` **logs and returns without raising** — a stray
must never fail `/unregister` on a flaky unfriend — and deliberately **leaves
`bot_account_id` set**, so the mismatch is left for the standalone reconcile job (diffing
`/friend/me` against `ArcaeaAccount` rows) rather than silently discarded.

## Regression signal

A bot account's live `/friend/me` friend count that is persistently higher than the count of
`ArcaeaAccount` rows pointing at it with `bot_account_id` set — or the inverse, a row with
`bot_account_id = NULL` that lowiro still lists as a friend. Either is the reconcile job's
signal to fire; either recurring in volume (rather than the occasional flaky-network case)
suggests the ordering in `release` regressed.
