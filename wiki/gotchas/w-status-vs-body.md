---
type: gotcha
status: active
severity: high
area: wire
verified: 2026-07-17
created: 2026-07-21
updated: 2026-07-21
tags: [gotcha, wire, envelopes]
aliases: ["Re-logging in on HTTP 400 masks real domain errors"]
---

# Re-logging in on HTTP 400 masks real domain errors

## Symptom

Every duplicate `add_friend` call (a player already friended, `error_code: 602`) triggers a
pointless re-login. Worse, a genuinely dead session and a live but domain-erroring one
(nonexistent friend code, at HTTP 404) get treated the same way or, in the 404 case,
**not recognized as an error at all** by code that only inspects HTTP 400.

## Cause

`/webapi/*` responses use one JSON envelope, `{"success": false, "error_code": N}`, but it
is **not correlated with HTTP status**. It has been observed carried by both **400** (codes
203 and 602) and **404** (code 401). One status spans several codes; one code (well, the
envelope shape generally) can arrive under more than one status. The old client's rule —
"re-login on any HTTP 400" — is wrong twice over:

1. **400 is not an auth signal.** A duplicate `add_friend` (602) is also 400. Re-logging in
   on any 400 fires a pointless re-login on every duplicate add, and worse, a session that
   really is fine gets treated as if it died.
2. **400 is not even the only status carrying this envelope.** A nonexistent friend code
   answers **404**, with the identical `{"success":false,"error_code":401}` shape. A client
   that only inspects 400 sails past a 404 error body entirely — quite possibly parsing the
   body as a success because it never checked `success: false`.

## The wrong fix

Any variant of "branch on the HTTP status to decide what happened" on `/webapi/*` — including
adding 404 to a status-based dispatch table alongside 400. The set of statuses this envelope
can arrive under is explicitly assumed **open** (not just `{400, 404}`); a client hardcoded
to a status allowlist will break the next time lowiro's gateway picks a different one for the
same domain error. The envelope is defined by the **body**, never the status.

## The right handling

`src/coda/arcaea/errors.py::raise_for_envelope` reads `body["success"]` /
`body["error_code"]` (or `body["code"] == "UnauthorizedError"` for the third envelope, see
[[w-third-auth-envelope]]) and ignores the HTTP status entirely — it is not even a parameter
to the function. `error_code: 203` → `SessionExpired` (transient, re-login once); any other
code → a specific typed exception (`PlayerNotFound` for 401, `AlreadyFriend` for 602) or the
generic `ApiError` fallback. `/auth/login`'s HTTP 403 is the **one** genuine
status-carries-meaning exception, and it is parsed by a completely separate function
(`raise_for_login_envelope`) so the two envelope shapes can never be confused.

## Regression signal

Any new call site that does `if response.status == 400:` (or `== 404`) instead of routing
through `raise_for_envelope`/`raise_for_login_envelope`. A symptom in production: repeated
re-logins in the logs correlated with `error_code: 602` duplicate-friend events, or a 404
error body silently treated as a success (a "registered!" message for a friend code that
never actually got added).
