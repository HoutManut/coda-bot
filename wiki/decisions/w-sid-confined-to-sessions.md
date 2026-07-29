---
type: decision
status: active
date: 2026-07-17
reverses:
created: 2026-07-21
updated: 2026-07-21
tags: [decision, layering, sessions]
aliases: ["`sessions/` is the only module that knows what a `sid` is; `bot_account_id` lives only in `pool.py`"]
---

# `sessions/` is the only module that knows what a `sid` is; `bot_account_id` lives only in `pool.py`

## Context

A `sid` is the entire auth mechanism for lowiro's API (§2 of `arcaea-auth-behavior.md`), and
`bot_account_id` is the pointer that says which bot account holds which player. Both are the
kind of value that is tempting to thread through wherever it happens to be convenient — a
service signature, a query result, a DTO field — because it is *right there* at the call
site. Left unchecked, that threading is exactly how a sid or an internal pool identifier
leaks into a place that has no business holding it (a log line, a `ScoreResult` returned to
Discord-facing code, a domain error surfaced to a user).

## Alternatives

| Option | Why not |
|---|---|
| Let `players/service.py` or `extensions/` hold a `sid` directly when convenient (e.g. to skip a round trip through `SessionPool`) | Spreads knowledge of the auth mechanism outside the one place responsible for its lifecycle (refresh-on-203, terminal-403 handling, the per-account login lock) — any such call site would have to reimplement or bypass that lifecycle |
| Expose `bot_account_id` on `ArcaeaAccount`-adjacent query results or `ScoreResult` for convenience (e.g. so a caller can "just look up who holds this player") | `arcaea-api-layer.md` §1 states this explicitly as a hard rule with no exception: `bot_account_id` never appears in a service signature, a query result, or a `ScoreResult` |
| A `SessionStore` protocol injected into `arcaea/` so persistence code (which necessarily touches sids) could live closer to the wire calls that produce them | Rejected for a related but distinct reason — see [[w-arcaea-never-imports-db]] — but the same instinct (spreading auth-adjacent knowledge outward "for convenience") is what both decisions push back against |

## Decision

`src/coda/sessions/` (`session.py` and `pool.py`) is the **only** code, alongside `arcaea/`
itself, that ever holds a `sid` value. `bot_account_id` specifically is confined further —
it appears **only** in `sessions/pool.py`, never in a service signature, a query result
exposed upward, or a `ScoreResult`. Everything above `sessions/` (`players/`, `scores/`,
`extensions/`) asks for a session (`SessionPool.active()` / `.get()` / `.place()`, or an
`AccountSession`/`BotSession` object) and calls through it — it never reaches in for the raw
value.

## Consequences

- A poll key is namespaced as `("bot", bot_accounts.id)` rather than a bare id
  specifically so the id space stays inside `sessions/pool.py::poll_key` — the two id
  spaces (`bot_accounts.id` vs. `arcaea_accounts.id`) are unrelated and would collide if
  either escaped as a bare integer.
- Anything needing "which bot account holds this player" (release on stray, capacity
  checks, poll-key resolution) must ask `SessionPool` for the answer rather than reading
  `ArcaeaAccount.bot_account_id` directly and reasoning about it elsewhere — even though the
  column itself lives on `ArcaeaAccount`, its *meaning* (an active pool assignment with a
  live wire consequence) is `sessions/`'s to interpret.
- `players/service.py` and `players/session.py` — verified for this ingest — only ever hold
  a `BotSession`/`AccountSession`/`ArcaeaAccount` object, never a raw `sid` string or a bare
  `bot_account_id` passed as a parameter.
- This is what makes it safe to reason about sid leakage (e.g. a sid ending up in a log
  line) as a `sessions/`-only concern: no other package has the value to leak in the first
  place.

## Enforced at

Not a lint rule — a documented invariant, stated in both `arcaea-api-layer.md` §1's "Hard
layer rules" table and restated in `sessions/session.py`'s and `sessions/pool.py`'s own
module docstrings ("This module and `coda.sessions.pool` are the only code that knows what a
sid is"; "`bot_account_id` is written only here"). Verified by direct inspection of
`players/service.py`, `players/session.py`, and `sessions/pool.py`/`session.py` for this
ingest.
