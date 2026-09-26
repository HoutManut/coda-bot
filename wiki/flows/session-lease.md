---
type: flow
status: active
entrypoint: "AccountSession.call(fn, *args) -- src/coda/sessions/session.py"
touches: [sessions, arcaea, db]
created: 2026-07-21
updated: 2026-07-21
verified: 2026-07-29
grade: A
tags: [flow, sessions, arcaea]
aliases: ["Session Lease"]
---
# Session Lease

## Trigger

Any code that needs a wire response — the poller (bot or own path), pool placement
(`SessionPool._capacity`), an on-demand `/recent` refresh — calls
`AccountSession.call(endpoint_fn, *args)` rather than touching a `sid` directly.

## Path

1. `AccountSession.call` acquires `self._lock` — the **shared, per-account** re-login lock
   (`session.py::_login_lock`, keyed `(account_type, account_id)`). This prevents two
   coroutines racing the same account's 203 from both logging in.
2. `identity.bind(self._identity)` — binds this account's stored, coherent browser identity
   for the duration of the call, so every header this request sends matches the account's
   permanent build.
3. `_ensure_sid()`:
   - No stored `sid` at all → `_refresh()`.
   - `expires_at` is within `REFRESH_MARGIN` (24h) of now → proactively `_refresh()`. This is
     an **optimization only** — `expires_at` never slides and the server can invalidate
     out-of-band, so it is never trusted as sole proof of validity.
   - Otherwise, return the stored `sid` as-is.
4. Call `fn(sid, *args, **kwargs)` — the endpoint function from `coda.arcaea.endpoints`.
5. On `SessionExpired` (either `error_code: 203` or the HTTP-401 `UnauthorizedError` shape —
   see [[w-third-auth-envelope]]): `_refresh()` once, retry the call **once**, never loop.
6. `_refresh()`: `auth.login(email, password)` → on success, `account.store_session(db, sid,
   expires_at)` and return the new `sid`. On `InvalidCredentials` (403): `account.mark_dead(db)`
   (deactivate the row) and **re-raise, never retry** — a login storm on bad credentials is
   the failure mode this guards against.

`endpoints.fetch_me` is self-validating (200 with a live session, 400/203 without), so there
is no separate auth-probe step anywhere in this path — the first real call *is* the check.

## Failure modes

| Failure | Where it surfaces | User-visible result |
|---|---|---|
| Dead session (`error_code: 203`) | `AccountSession.call` catches `SessionExpired` | Transparent — one re-login, one retry, then success or a raised `ArcaeaError` |
| Rotated password (HTTP 401 `UnauthorizedError`) | Same catch clause — mapped to `SessionExpired` | Transparent retry that then hits `InvalidCredentials` (403) on the re-login attempt → terminal |
| Bad/rotated credentials confirmed | `_refresh()` catches `InvalidCredentials` | Account marked dead (`is_active=False` / `is_valid=False`); own-path also DMs the owner once (`players/notify.py`) |
| Two live `AccountSession` instances for the same account hold different sids | Documented, not fixed | At most one extra re-login per stale-instance call; bounded by the shared lock. Listed as "Deferred" in the archived API-layer findings writeup |
| Transport failure (DNS/TCP/TLS/timeout) | `client.request` raises `TransportError` | Propagates as `ArcaeaError` — callers that must not blind-retry a write (`add_friend`/`remove_friend`) do not; the 602/reconcile path absorbs the resulting drift |
| Request hangs (lowiro origin holds it open) | `REQUEST_TIMEOUT = 30s` in `client.py` | Becomes a `TransportError` after 30s instead of an unbounded stall — documented only in the archived API-layer findings writeup, not in [[arcaea-api-layer]] |

## Ordering constraints

- **203-or-401 catch, then refresh, then retry — never loop.** A second failure after the
  one retry propagates as a real `ArcaeaError`; this caps the worst case at one extra login
  per call and prevents a login storm against bad credentials.
- **`_ensure_sid`'s proactive-refresh check must run before the call, not after** — this is
  what keeps the common path to one round trip when the cached `sid` is still fresh, while
  still avoiding a near-certain 203 for an about-to-expire one.
- **`mark_dead`/`store_session` must happen before the exception propagates** on both the
  terminal-403 and successful-refresh branches — the row's state must be correct before any
  caller (e.g. `SessionPool._capacity` skipping a broken account, or `PlayerSessionProvider`
  excluding an invalid credential next sweep) reads it again.
- **The lock is per-account, not per-request** — acquired for the whole `call()`, including
  the retry, so a concurrent caller on the same account genuinely waits rather than racing a
  second login.

## Related

[[sessions]], [[arcaea]], [[registration|Registration]],
[[w-third-auth-envelope]], [[w-coherent-browser-identity]],
[[w-sid-confined-to-sessions]]
