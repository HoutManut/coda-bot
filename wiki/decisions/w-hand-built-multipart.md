---
type: decision
status: active
date: 2026-07-17
reverses:
created: 2026-07-21
updated: 2026-07-21
tags: [decision, wire, multipart]
aliases: ["Hand-build the multipart body; never `aiohttp.FormData`"]
---

# Hand-build the multipart body; never `aiohttp.FormData`

## Context

`add_friend`/`remove_friend` are `multipart/form-data` POSTs with a single field. The old
client (`arcaea_online/`) hand-built the multipart body as a raw `WebKitFormBoundary`
string, including a hardcoded `Content-Length: '41'`. The rewrite's first instinct was to
treat this as exactly the kind of manual, cargo-cult-looking construction worth replacing
with `aiohttp`'s built-in `FormData`. Task 11 (`arcaea-api-research-tasks.md`) explicitly
gated building the real `add_friend` implementation on verifying this first.

## Alternatives

| Option | Why not |
|---|---|
| `aiohttp.FormData` | **Verified unusable, live, 2026-07-17.** It is a *streaming* payload, so aiohttp sends `Transfer-Encoding: chunked` with no `Content-Length`; lowiro's origin waits for a body it never decides has ended, and Cloudflare eventually answers with an HTML 504. Measured on one session, GETs bracketing the failure to rule out session/API health as the cause — see [[w-formdata-504]] |
| Keep the old client's hand-built body **and its hardcoded `Content-Length: '41'`** | The framing (bytes + real `Content-Length`) is what matters, not the specific hardcoded value — `'41'` only ever matched one email length and is genuine junk that would break on any other input length |

## Decision

The multipart body is hand-built as `bytes` (`src/coda/arcaea/client.py::encode_multipart`),
mimicking Chrome's `WebKitFormBoundary` prefix, with the **real** `Content-Length` computed
by the HTTP library from the actual byte length — not hardcoded. This makes the old client's
hand-rolled multipart construction **load-bearing, not cargo-cult**: it is the one behavior
from the old client that §8 of `arcaea-auth-behavior.md` would have been wrong to delete.

## Consequences

- Every `add_friend`/`remove_friend` call must go through `encode_multipart` — reaching for
  `aiohttp.FormData` anywhere in this call path reintroduces a ~60s hang followed by an
  unparseable HTML 504 that looks exactly like a lowiro outage to anyone debugging it, not
  like the framing bug it actually is.
- `scripts/verify_multipart.py` exists specifically to catch a regression here before it
  reaches production — a passing run is what "still frames the request the way lowiro's
  origin expects" looks like.
- The gate paid for itself: building `add_friend` on `FormData` without first verifying it
  would have shipped a `/register` that fails in exactly this misleading way. Per
  `arcaea-api-layer.md` §10, this is presented as the canonical example of why the pre-build
  research phase was worth doing at all before writing the real endpoint code.
- `encode_multipart` additionally validates every field's `name`/`value` for CRLF or the
  boundary token before assembling, raising rather than silently corrupting the frame — a
  hardening added after this decision (archived API-layer findings writeup, not in
  `arcaea-api-layer.md`), since real multipart value escaping is under-specified and a hard
  reject is the honest choice.

## Enforced at

`src/coda/arcaea/client.py::encode_multipart`, called from `request()` whenever a `form`
dict argument is passed (`endpoints.py::add_friend`/`remove_friend` are the only call
sites). See [[w-formdata-504]] for the full symptom/cause/regression-signal writeup.
