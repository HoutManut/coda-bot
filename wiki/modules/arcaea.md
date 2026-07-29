---
type: module
status: active
path: src/coda/arcaea/
purpose: Pure wire client for lowiro's private webapi -- DB-free, does no persistence.
depends_on: []
used_by: [sessions, players, scores]
created: 2026-07-21
updated: 2026-07-21
tags: [module, arcaea, wire]
aliases: ["arcaea (module)"]
---

# arcaea

## Purpose

The self-contained scraper of lowiro's private web API (`https://webapi.lowiro.com`).
Everything a request needs — headers, envelope parsing, rate limiting, multipart framing,
DTO translation — funnels through this package, and this package alone. It never persists
anything: `auth.login()` *returns* `(sid, expires_at)`, it does not write them anywhere.

## Public surface

| Symbol | File | What it does |
|---|---|---|
| `request(method, path, *, sid, json_body, form)` | `client.py` | The one HTTP funnel. Rate-limited, envelope-agnostic (returns decoded JSON), raises `TransportError` on no-response |
| `request_with_cookie(method, path, *, json_body)` | `client.py` | Like `request`, also returns the `sid` the response set — used only by `auth.login` |
| `encode_multipart(fields)` | `client.py` | Hand-built `WebKitFormBoundary` body. **Never replace with `aiohttp.FormData`** — see [[w-formdata-504]] |
| `login(email, password) -> (sid, expires_at)` | `auth.py` | POST `/auth/login`. Returns; never persists |
| `fetch_me(sid)` | `endpoints.py` | GET `/webapi/user/me` — own profile, no friends list |
| `fetch_friends(sid)` | `endpoints.py` | GET `/webapi/friend/me` — the friends list, never paginated |
| `add_friend(sid, friend_code)` | `endpoints.py` | POST `/webapi/friend/me/add` |
| `remove_friend(sid, friend_id)` | `endpoints.py` | POST `/webapi/friend/me/delete` |
| `unknown_friends(body, known)` | `endpoints.py` | Diffs an add/delete response against prior state — the *only* way to learn a new `arc_user_id` |
| `raise_for_envelope(body)` / `raise_for_login_envelope(body)` | `errors.py` | The one place a lowiro response envelope is read |
| `ArcaeaError` and subclasses | `errors.py` | `ApiError`, `TransportError`, `SessionExpired`, `PlayerNotFound`, `AlreadyFriend`, `InvalidCredentials`, `UnexpectedResponse` |
| `generate()` / `bind()` / `current()` / `coerce()` | `identity.py` | Per-account browser identity: generation, contextvar bind, and stored-blob validation |
| `parse_me`, `parse_friends`, `parse_friend`, `ScoreResult` etc. | `dto/` | Raw dict → typed objects, no I/O |

## Layer rules

- **Never imports `coda.db`.** Not enforced by a lint rule — it simply never persists. This
  is load-bearing, not stylistic: importing `coda.db` builds the async engine at import
  time, so a violation would make this package unimportable without a live database.
  Verified: `client.py`, `auth.py`, `endpoints.py`, `errors.py`, `identity.py`, `dto/*` all
  import nothing under `coda.db`.
- **`endpoints.py` never logs in.** Auth is a session concern; every endpoint function takes
  a `sid` as its first argument.
- **`dto/` does no I/O.** Chart resolution needs a DB lookup, so it is explicitly *not* a
  DTO job — the DTO carries `difficulty_id: int | None` and the caller (outside this
  package, in `catalog/`) resolves it.
- **Rejected, do not reintroduce**: an injected `SessionStore` protocol (unnecessary once
  this package stopped persisting), a `call_authed(account, fn)` helper (would smear session
  refresh into the domain layer).

## State it owns

- One shared `aiohttp.ClientSession` (`client.py::_get_session`), created lazily so import
  never requires a running event loop. Uses `aiohttp.DummyCookieJar()` **deliberately** — a
  default jar would parent-match `Domain=lowiro.com` cookies across accounts and leak one
  bot account's `sid` onto another's request. The `sid` is always sent as an explicit
  `Cookie` header instead.
- A global `_RateLimiter` (`MAX_CONCURRENT = 2`, `MIN_INTERVAL = 0.5`), shared by every
  caller including any bulk walk (e.g. paginated history) so nothing can starve the poller.
- A per-task browser-identity contextvar (`identity.py::_current`), bound around every
  session's calls so headers stay internally consistent for that account's whole lifetime.

### Sentinels this package must absorb (`dto/`)

| Field | Trap | Handling |
|---|---|---|
| `rating: -1` | Player hides PTT; naive decode gives `-0.01` | → `None`, independent of `is_profile_public` |
| `score: 0` | A real score, not null | Never treat falsy scores as missing |
| `recent_score` | Absent/null/omitted for a never-played friend — shape unverified | `friend.get("recent_score") or []` (`dto/friend.py`, `dto/me.py`) |
| `showcase_characters` | Ints **or** dicts in the same response | Skipped entirely — never subscripted |

## Contradiction: doc vs shipped code

[[arcaea-api-layer]] documents **two** error envelopes. Shipped
`errors.py` has a **third**: HTTP 401 `{"code":"UnauthorizedError","message":...}`,
captured 2026-07-18 for a server-side password rotation, mapped to `SessionExpired` exactly
like `error_code: 203`. Neither `arcaea-auth-behavior.md` (dated 2026-07-17) nor
`arcaea-api-layer.md` documents this third shape — it postdates both. See
[[w-third-auth-envelope]].

A separate API-layer findings writeup (2026-07-19, since archived out of the repo) recorded eight
further hardening fixes layered onto this package beyond what `arcaea-api-layer.md`
describes: a `TransportError` type for network-level failures, an explicit 30s request
timeout, a rate-limiter cancellation-leak fix, moving login-envelope parsing to its own
function (`raise_for_login_envelope`) so a `/webapi/*` body can never be misread as
`InvalidCredentials`, a `CHROME_VERSIONS` ceiling bump, per-entry-fault-tolerant friend
parsing (one bad friend object no longer takes down the whole account's poll), and
`encode_multipart` value validation against CRLF/boundary injection. None of these appear
in `arcaea-api-layer.md` itself — treat that doc as the original design and this package's
current docstrings as the current state.

## Related

`[[Registration]]`, `[[Session Lease]]`, `[[sessions]]`,
`[[w-formdata-504]]`, `[[w-third-auth-envelope]]`, `[[w-status-vs-body]]`,
`[[w-coherent-browser-identity]]`, `[[w-arcaea-never-imports-db]]`,
`[[w-hand-built-multipart]]`, `[[w-branch-on-body-not-status]]`
