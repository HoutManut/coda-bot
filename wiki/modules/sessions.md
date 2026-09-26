---
type: module
status: active
path: src/coda/sessions/
purpose: The only place a sid exists. Session lifecycle, refresh-on-203, and bot-account pool placement.
depends_on: [arcaea, db]
used_by: [players, scores]
created: 2026-07-21
updated: 2026-07-21
verified: 2026-07-29
grade: A
tags: [module, sessions, arcaea]
aliases: ["sessions (module)"]
---
# sessions

## Purpose

`sessions/` and `arcaea/` are the only two packages that know what a `sid` is; everything
above (`players/`, `scores/`, `extensions/`) asks for a session and calls through it.
`AccountSession` owns acquiring, refreshing, and persisting a `sid` for one stored login
(bot account or player credential); `SessionPool` owns *which* bot account holds which
player and the friend-slot placement decision.

## Public surface

| Symbol | File | What it does |
|---|---|---|
| `AccountSession(account: AccountAuth, db)` | `session.py` | Generic session over either account type. `.call(fn, *args)` runs an endpoint fn with the stored sid, refreshing once on `SessionExpired` |
| `BotSession(account: BotAccount, db)` | `session.py` | `AccountSession` bound to a `BotAccountAdapter` |
| `SessionPool(db)` | `pool.py` | `.active()` — every usable bot account's session (the polling unit). `.get(id)` — one account's session or None. `.place(code, exclude=)` — pick an account with room, returns `(session, known_arc_user_ids)`. `.release(account)` — give a slot back. `.poll_key(account)` — `("bot", id)` or None. `.known_arc_user_ids(bot_account_id)` |
| `NoCapacity` | `pool.py` | Every active bot account is full — genuinely terminal at this scale; needs a human to create another account |
| `AccountAuth`, `BotAccountAdapter`, `PlayerCredentialAdapter` | `adapters.py` | Uniform interface so `AccountSession` works over either row type |

## Layer rules

- **`sessions/` is the only module that knows what a `sid` is** apart from `arcaea/`
  itself. Verified: no `sid` value crosses into `players/service.py` or an extension except
  as an opaque return of `auth.login()` immediately handed to `_store_credential`.
- **`bot_account_id` appears in `sessions/pool.py` and nowhere else** — never in a service
  signature, a query result exposed upward, or a `ScoreResult`. Verified: `pool.py::release`
  and `poll_key` are the only places `BotAccount` rows are read/written by id;
  `players/service.py` only ever holds a `BotSession`/`ArcaeaAccount`, never a raw
  `bot_account_id`.
- **Per-session (really per-account) lock, distinct from the global rate limiter.** `session.py::_login_lock` is a shared `asyncio.Lock` keyed by `(account_type, account_id)`,
  preventing double-login for the *same* account; `arcaea/client.py`'s `_RateLimiter` is
  global across all accounts and prevents flooding. Both exist; they solve different
  problems.
- **Capacity is always read live**, never trusted from the stored `friend_count`/`max_friends`
  hints — `pool.py::_capacity` calls `fetch_me` + `fetch_friends` every placement.

## State it owns

- `AccountSession._lock` — the shared per-account re-login lock (module-level dict,
  `session.py::_login_locks`), so two coroutines racing a 203 on the same account cannot
  double-login.
- Nothing persisted directly by this package other than what it writes through
  `account.store_session(db, sid, expires_at)` / `account.mark_dead(db)` — the actual
  columns (`BotAccount.cookie_data`, `.expires_at`, `PlayerCredential.cookie_data`, etc.)
  live in `coda.db.models` and are written via the adapters.

## Contradiction: doc vs shipped code

[[arcaea-api-layer]] §4 describes a single `BotSession.call` with the retry logic
inline. Shipped code generalizes this into `AccountSession` (the retry/refresh/lock
machinery) with `BotSession` as a thin subclass — the *design* is identical (203 → refresh
once → retry once → fail; 403 on refresh is terminal, `mark_dead`), but the doc's code
sketch does not mention the generalization needed to also serve `players/session.py`'s
own-credentials path (`PlayerCredentialAdapter`). This is scope growth the doc predates, not
a contradiction of its stated rules.

`pool.py::place`'s `exclude` parameter (for the last-slot placement race) and the
`_MAX_PLACEMENT_ATTEMPTS` retry loop in `players/service.py::_place_and_add` are documented
only in the archived API-layer findings writeup (2026-07-19) — [[arcaea-api-layer]] §6 describes
`place()` without the `exclude` set at all.

## Related

[[session-lease|Session Lease]], [[registration|Registration]], [[arcaea|arcaea (module)]],
[[players]], [[w-release-order]], [[w-third-auth-envelope]]
