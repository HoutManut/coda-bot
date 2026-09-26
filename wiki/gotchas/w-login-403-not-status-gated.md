---
type: gotcha
status: active
severity: high
area: wire
verified: 2026-08-27
created: 2026-08-27
updated: 2026-08-27
tags: [gotcha, wire, envelopes, auth]
aliases: ["An origin outage permanently deactivated a bot account"]
---

# An origin outage can look exactly like a dead credential on `/auth/login`

## Symptom

lowiro's webapi went down for maintenance on 2026-08-27. A bot account's session expired
mid-outage, the pool tried to re-login, and the account was immediately deactivated
(`BotAccount.is_active = False`) with the log line `account 1: credentials rejected (403).
Deactivating -- this needs a human, retrying would be a login storm` -- even though the
credentials were fine and the account came right back once lowiro recovered. The poller then
had zero active bot accounts to poll, silently, for the rest of the day: no exception, no
"poll cycle" log line, just `pool: 0 active bot accounts` on every tick.

The actual HTTP status, visible only in a separate `coda.arcaea.client` WARNING line, was
**500** from Cloudflare -- not 403.

## Cause

[[w-status-vs-body|w-status-vs-body]] documents `/auth/login`'s HTTP 403 as "the one genuine
status-carries-meaning exception" to the envelope-is-defined-by-body rule -- but
`raise_for_login_envelope` never actually checked the status. It raised
`InvalidCredentials` off the body shape (`{"error": {...}}`) alone. A Cloudflare/gateway
error page returned during an outage happened to decode as JSON with that exact shape under
a 500, so it was read as a terminal "wrong password" and the account was deactivated for
something that had nothing to do with its credentials.

Made worse by two things: `sessions/session.py`'s log line hardcoded the text `(403)`
regardless of the real status, and `/auth/login` response bodies are redacted from logs
entirely (`client.py::_CREDENTIAL_PATHS`) -- so diagnosing this after the fact required
correlating the `client.py` WARNING (which has the real status) against the `session.py`
ERROR (fixed text, no status) by timestamp across log files.

## The wrong fix

Trusting the body shape alone on `/auth/login`, the way every other `/webapi/*` envelope is
correctly read (see [[w-status-vs-body]]) -- `/auth/login` is the deliberate exception to
that rule, not a case to make consistent with it. Also wrong: logging the raw response body
here to fix the diagnosability gap -- `_CREDENTIAL_PATHS` redacts it on purpose, as a standing
invariant, not because today's body shape happens to be sensitive.

## The right handling

`raise_for_login_envelope(status, body)` (`arcaea/errors.py`) now takes the HTTP status
explicitly and only raises `InvalidCredentials` (terminal, triggers `mark_dead`) when
`status == 403`. An error-shaped body under any other status raises `UnexpectedResponse`
instead -- recoverable, caught by the ordinary `except ArcaeaError` skip-and-continue paths,
never deactivates the account. `client.py::request_with_cookie` now returns the status
alongside the body and sid so `auth.login` can pass it through. `sessions/session.py` logs
`str(exc)` instead of a hardcoded `(403)`, which surfaces lowiro's actual `error.name` /
`error.message` -- safe to log, since `raise_for_login_envelope` only ever puts those two
fields (not the raw body, not the password) into the exception text.

## Regression signal

A `BotAccount`/`PlayerCredential` deactivated during a window where `coda.arcaea.client`
logged a non-403 status for `/auth/login`. Also watch for `raise_for_login_envelope` losing
its `status` parameter, or a call site passing a hardcoded `403` instead of the real response
status.
