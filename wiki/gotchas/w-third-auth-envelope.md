---
type: gotcha
status: active
severity: high
area: wire
verified: 2026-07-18
created: 2026-07-21
updated: 2026-07-21
tags: [gotcha, wire, envelopes, staleness]
aliases: ["A third \"session is dead\" envelope exists, undocumented in the auth-behavior source"]
---

# A third "session is dead" envelope exists, undocumented in the auth-behavior source

## Symptom

A stored `sid` that should still be within its 30-day, non-sliding window (per
[[arcaea-auth-behavior]]) starts failing every call — not with
`error_code: 203` inside the usual `{"success":false,...}` body, but with a completely
different shape: HTTP **401** and `{"code": "UnauthorizedError", "message": "Bearer token
invalid"}` (or similar). Code that only recognizes `error_code: 203` as "session dead" would
misparse this as `UnexpectedResponse` — "lowiro changed the API" — rather than the mundane
"this session needs a re-login" it actually is.

## Cause

Captured 2026-07-18 — **one day after** [[arcaea-auth-behavior]]'s stated capture
window (2026-07-17) — when a password change **in another browser** invalidated the sid the
bot had stored. This is a genuinely different envelope from both of `arcaea-auth-behavior.md`'s
documented shapes (`{"success":false,"error_code":N}` and `/auth/login`'s
`{"error":{"name":"ForbiddenError",...}}`), and the source document simply predates it —
it is not an error in that document, it is a gap created by the private API's own
no-versioning, no-deprecation-notice behavior that the document itself warns about
generally (§7.1's "the private webapi changes without notice" callout).

`CLAUDE.md`'s own domain-knowledge section already flags this: "password rotation surfaces
as HTTP 401 UnauthorizedError (not login 403) — a third auth envelope mapping to
SessionExpired. Watch Bearer-token migration."  The phrase "Bearer-token migration" is a
forward-looking concern: if lowiro is moving away from cookie-based `sid` auth toward
Bearer tokens, this third envelope may be an early, partial artifact of that shift rather
than a one-off quirk.

## The wrong fix

Treating this as an unrecognized envelope and letting it fall through to
`UnexpectedResponse` — technically "safe" (it does not crash) but functionally wrong: it
would surface as a permanent-looking "lowiro changed the API" alert for something that is
actually the ordinary, expected consequence of a player rotating their password, and it
would never trigger the re-login that would fix a merely-rotated (not permanently dead)
credential.

A second wrong fix: conflating this HTTP-401 `UnauthorizedError` shape with the **unrelated**
`error_code: 401` (`PlayerNotFound`) that arrives under HTTP 404 for a nonexistent friend
code. They share the digits "401" by coincidence of two completely different numbering
schemes (an HTTP status vs. a domain error_code) and mean opposite things — one is "this
session is dead", the other is "this player does not exist". `errors.py`'s docstring calls
this out explicitly as a trap.

## The right handling

`src/coda/arcaea/errors.py::raise_for_envelope` checks `body.get("code") ==
"UnauthorizedError"` as a distinct branch, before falling through to the generic
`success: false` handling, and raises `SessionExpired` — the exact same exception
`error_code: 203` raises. `AccountSession.call` (`sessions/session.py`) therefore handles
both shapes identically: refresh once, retry once. If the refresh itself then hits a genuine
403 (the password really did change and the stored old password no longer works), *that*
becomes `InvalidCredentials` — terminal, `mark_dead`, never retried. So the re-login attempt
is what turns a *rotated* password into the terminal failure it should be, rather than an
infinite loop of 401s.

## Regression signal

Any `UnexpectedResponse` in the logs whose body shape is `{"code": "UnauthorizedError", ...}`
— that means the branch in `raise_for_envelope` was removed or reordered. Also watch for
`CLAUDE.md`'s flagged "Bearer-token migration" — if lowiro starts returning tokens instead of
(or alongside) `Set-Cookie: sid`, this envelope's meaning and frequency may shift, and
[[arcaea-auth-behavior]] should be re-captured rather than patched around.
