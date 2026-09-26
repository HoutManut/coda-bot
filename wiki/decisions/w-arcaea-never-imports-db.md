---
type: decision
status: active
date: 2026-07-17
reverses:
created: 2026-07-21
updated: 2026-07-21
tags: [decision, layering, arcaea]
aliases: ["`src/coda/arcaea/` never imports `coda.db`", "Decision — arcaea never imports db"]
---
# `src/coda/arcaea/` never imports `coda.db`

## Context

`arcaea/` is meant to be a pure wire client for lowiro's private webapi — login, fetch,
add/remove friend, DTO parsing. Persistence (writing a `sid`, an `expires_at`, a play score)
naturally wants to live somewhere, and the easiest place to put it is right next to the wire
call that produced the value, inside `arcaea/` itself.

## Alternatives

| Option | Why not |
|---|---|
| Let `auth.login()` persist the sid it obtains directly (import `coda.db`, open a session, write the row) | Importing `coda.db` builds the async engine **at import time** — so merely importing `coda.arcaea.auth` anywhere (a script, a test, a REPL) would require a live database connection to succeed, even for code that never touches the DB |
| An injected `SessionStore` protocol passed into `arcaea/` functions, so persistence is pluggable but still callable from inside the package | Considered and rejected (`arcaea-api-layer.md` §1) — unnecessary complexity once the simpler rule ("this package never persists, full stop") does the same job with no abstraction to maintain |
| A `call_authed(account, fn)` helper living in a `services/`-adjacent layer that both authenticates and calls, blurring where session-management ends and domain logic begins | Rejected (`arcaea-api-layer.md` §1) — smears session refresh into the domain layer instead of keeping it in `sessions/` |

## Decision

`src/coda/arcaea/` (and every module inside it — `client.py`, `auth.py`, `endpoints.py`,
`errors.py`, `identity.py`, `dto/*`) **never imports `coda.db`, and never persists
anything.** `auth.login(email, password)` *returns* `(sid, expires_at)`; it is the caller's
job (in `sessions/session.py`) to write it somewhere.

## Consequences

- The wire layer is importable — and therefore independently testable, scriptable, or
  usable in a throwaway REPL session — without a running Postgres instance or a configured
  `DATABASE_URL`. This is not a nice-to-have; violating the rule makes the package
  **unimportable** without a live database, because `coda.db`'s module-level code builds the
  async engine as a side effect of import.
- Every persistence decision (when to write a fresh `sid`, when to mark an account dead,
  when to store a decoded score) is made exactly once, in `sessions/` or the feature
  services above it — `arcaea/` cannot make that decision even by accident, because it has
  no way to reach the DB to act on one.
- This is the reason `sessions/` exists as a distinct package rather than folding into
  `arcaea/`: something has to own the DB-touching half of "get a sid and keep it working",
  and that something must not be `arcaea/` itself.

## Enforced at

Not enforced by a lint rule or an import-boundary check — "it simply never persists"
(`arcaea-api-layer.md` §1's own words). Verified by direct inspection for this ingest: no
file under `src/coda/arcaea/` imports anything from `coda.db`. `src/coda/sessions/session.py`
is the actual call site that persists what `auth.login()` returns, via
`account.store_session(db, sid, expires_at)` / `account.mark_dead(db)`.
