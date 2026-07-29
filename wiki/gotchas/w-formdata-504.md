---
type: gotcha
status: active
severity: high
area: wire
verified: 2026-07-17
created: 2026-07-21
updated: 2026-07-21
tags: [gotcha, wire, multipart]
aliases: ["aiohttp.FormData hangs `add_friend`, then Cloudflare 504s"]
---

# aiohttp.FormData hangs `add_friend`, then Cloudflare 504s

## Symptom

`POST /webapi/friend/me/add` (and, by inference, `/delete` — same shape, not separately
captured) never returns a normal response when built with `aiohttp.FormData`. The request
sits until Cloudflare's own gateway timeout fires and returns an **HTML** `504 Gateway
time-out` — not a JSON error envelope, not a lowiro response at all.

## Cause

`aiohttp.FormData` is a **streaming** payload: aiohttp sends it with
`Transfer-Encoding: chunked` and no `Content-Length` header. lowiro's origin server waits
for a body it never decides has ended, and Cloudflare (which fronts the API) eventually
times the connection out at ~100s and answers with its own error page instead of lowiro's.
Verified with GETs bracketing the failure on the same session, seconds apart — `GET
/webapi/user/me` and `GET /webapi/friend/me` both 200'd immediately before and the session
was healthy, so the 504 is the **request body's framing**, not lowiro being down or the
session being dead.

## The wrong fix

**Reaching for `aiohttp.FormData` at all**, on the reasoning that it is the "modern,
idiomatic" way to build a multipart body and the old client's hand-rolled
`WebKitFormBoundary` string construction looks like cargo-cult to delete during the rewrite.
It is the opposite: this is the *one* old behavior that is load-bearing, not cargo-cult.
Deleting it (which the initial pass toward `arcaea-api-layer.md` explicitly flagged as a
risk worth gating on, per its §10) would have shipped a `/register` that hangs for ~60s and
fails with unparseable HTML — presenting to an operator as **a lowiro outage**, not as our
own bug, and burning the timeout budget of a Discord slash command in the process.

A second wrong fix, already identified and discarded: keeping the *old* client's hardcoded
`Content-Length: '41'` alongside the hand-built body. That value matched exactly one email
length and is real junk — the fix is to let the HTTP library compute the real
`Content-Length`, not to hand-write it.

## The right handling

Hand-build the multipart body as `bytes` so aiohttp sends a real `Content-Length`:
`src/coda/arcaea/client.py::encode_multipart` (called from `request()` whenever a `form`
dict is passed). It mimics Chrome's `WebKitFormBoundary` prefix (consistent with the rest of
the header-spoofing story) and, beyond the original finding, now validates every
`name`/`value` for CRLF or the boundary token before assembling — a hard reject rather than
an escape, since multipart value escaping is under-specified
(archived API-layer findings writeup, fix 7).

`scripts/verify_multipart.py` exists specifically to guard this against regression — run it
whenever `client.py`'s multipart encoding changes.

## Regression signal

A `/register` (or any `add_friend`/`remove_friend` call) that hangs for tens of seconds and
then fails with a non-JSON body — `UnexpectedResponse` raised from
`client.py::_decode_json`'s `ValueError` branch, logged at `ERROR` with the raw text. If that
ever happens again, check whether something reintroduced `aiohttp.FormData` in place of
`encode_multipart` before assuming lowiro is actually down.
