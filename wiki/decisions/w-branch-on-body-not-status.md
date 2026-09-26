---
type: decision
status: active
date: 2026-07-17
reverses:
created: 2026-07-21
updated: 2026-07-21
tags: [decision, wire, errors]
aliases: ["Branch on the response body, never the HTTP status"]
---
# Branch on the response body, never the HTTP status

## Context

The old client's `ensure_authed()`-equivalent re-logged in whenever a `/webapi/*` call
returned HTTP 400, on the assumption that 400 meant "your session is bad, try again." Live
capture (`arcaea-auth-behavior.md` §6) disproved the premise the old client's design rested
on: a duplicate `add_friend` also returns 400 (`error_code: 602`), and a nonexistent friend
code returns **404** carrying the identical `{"success":false,"error_code":N}` envelope.
Status and `error_code` are observed to be uncorrelated.

## Alternatives

| Option | Why not |
|---|---|
| Re-login on any HTTP 400 (the old client's rule) | Fires a pointless re-login on every duplicate `add_friend`, and masks real domain errors as auth failures |
| A status-based dispatch table (`400 → X`, `404 → Y`, ...) | The set of statuses carrying the `{"success":false,"error_code":N}` envelope is explicitly treated as **open** — a client hardcoded to a status allowlist breaks the moment lowiro's gateway picks a different status for the same domain error, which it has already been observed to do (401 moved from an assumed-400 to an observed-404) |
| Inspect status first, only fall back to the body if the status is "unexpected" | Still couples correctness to a guess about which statuses matter; the whole point is that the status carries **no information the body doesn't** on `/webapi/*` |

## Decision

Every `/webapi/*` response is validated purely by its **body**: `success: true` → OK;
`success: false` → read `error_code` and map it to a typed exception; a third distinct shape
(`{"code": "UnauthorizedError", ...}`) is also read from the body. The HTTP status is not
even a parameter to the function that does this (`raise_for_envelope`). `/auth/login`'s HTTP
403 is the **one** stated exception — that endpoint's rejection is genuinely
status-plus-envelope, and it is parsed by an entirely separate function
(`raise_for_login_envelope`) so the two shapes can never be confused with each other.

## Consequences

- A future lowiro gateway change that moves an existing error to a new HTTP status (as
  already happened once, moving `error_code: 401` from an assumed 400 to an observed 404)
  requires **zero** code changes here — the body-based branch already covers it.
  A status-based design would have silently broken.
- Every domain error still needs its own `error_code` mapped explicitly
  (`errors.py::_CODES`); an unrecognized code is deliberately **not** an error in itself — it
  becomes the generic `ApiError`, kept recoverable rather than crashing a poll (see
  [[w-status-vs-body]] for the failure story this replaced).
- Nothing downstream of `raise_for_envelope`/`raise_for_login_envelope` may re-introduce a
  status check on `/webapi/*` — that would silently reopen the exact bug this decision
  exists to close.

## Enforced at

`src/coda/arcaea/errors.py::raise_for_envelope` (the `/webapi/*` envelopes) and
`raise_for_login_envelope` (the `/auth/login` envelope) — the **only** two places a lowiro
response envelope is read in the whole codebase, per that module's own docstring. See
[[w-status-vs-body]] for the specific failure this decision replaced, and
[[w-third-auth-envelope]] for the third body shape this design accommodated without a status
check.
