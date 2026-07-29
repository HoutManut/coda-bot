---
type: domain
status: active
source: arcaea-auth-behavior.md
verified: 2026-07-29
grade: B
created: 2026-07-21
updated: 2026-07-21
tags: [domain, arcaea, wire, auth, sessions]
aliases: ["Auth & Sessions (lowiro wire)", "Auth & Sessions"]
---

# Auth & Sessions (lowiro wire)

## Model

Two hosts: `arcaea.lowiro.com` is the static SPA (origin/referer source only, no API);
`webapi.lowiro.com` is the private API — all auth and data. There is no versioning and no
deprecation window; a response key present today can vanish without notice (`friends` moved
off `/webapi/user/me` between when the old client was written and 2026-07-17 — see
[[w-friends-key-removed]]). Auth is carried entirely by one opaque signed cookie, `sid`; the
login response body itself carries no token.

Three data-access tiers exist over the same domain concept ("what does this bot know about
a player's plays"), and they are **not** binary friend-vs-credentials — see the table below.

## Endpoints

`verified: 2026-07-17`, `grade: see per-row`

| Method | Path | Tier | Purpose | Grade |
|---|---|---|---|---|
| `POST` | `/auth/login` | — | Authenticate; issues `sid`. Bad creds → 403, distinct envelope | FACT |
| `POST` | `/auth/logout` | — | Destroys the session server-side immediately. Never call from the bot | FACT |
| `GET` | `/webapi/user/me` | any | Own profile + own `recent_score`. **No friends list** | FACT |
| `GET` | `/webapi/friend/me` | any | The friends list — separate endpoint, never paginated | FACT |
| `POST` | `/webapi/friend/me/add` | any | Add by `friend_code`. Unknown code → 404/401 | FACT |
| `POST` | `/webapi/friend/me/delete` | any | Remove by `friend_id` (= `user_id`) | FACT |
| `GET` | `/webapi/score/song/me/all` | sub | Paginated (page size 10); **DISPUTED** whether it is a full play log or one row per chart | FACT (existence/shape) / DISPUTED (semantics) |
| `GET` | `/webapi/score/rating/me` | sub | b30 + filtered-r10 for PTT. **Never** a latest-score feed | FACT + OWNER-STATED (filter rules) |
| `GET` | `/webapi/score/rating_progression/me` | sub | PTT over time; irregular shape, do not stitch durations | FACT |
| `GET` | `/webapi/user/me/online_image` | sub | URL to a server-rendered PNG, ~9.5s. Never in a command path | FACT (timing) / UNTESTED (expiry) |
| `GET` | `/webapi/score/total_ranking/world` | any | World leaderboard — free, gated per-route not per-prefix | OWNER-STATED |
| `GET` | `/webapi/score/total_ranking/friend` | sub | Friend leaderboard — unusable from a free bot account | OWNER-STATED |
| `GET` | `/country` | — | Unauthenticated, sets no session cookie | FACT |

`sub` = requires an active Arcaea Online subscription; gate on `arcaea_online_expire_ts`
from `/webapi/user/me`, compared to `now()` at read time (never stored as a boolean).

## Envelopes and error_code taxonomy

**Verified against shipped code**: `src/coda/arcaea/errors.py`. There are **three**
envelopes in practice, though `arcaea-auth-behavior.md` (dated 2026-07-17) documents only
two:

| Envelope | Shape | Meaning | Grade |
|---|---|---|---|
| `/webapi/*` generic | `{"success": false, "error_code": N}`, carried by HTTP 400 **and** 404 | Domain error; **status is noise, read the body** | FACT |
| `/auth/login` rejection | HTTP 403 `{"error":{"name":"ForbiddenError","message":104}}` | Bad credentials — terminal | FACT |
| `/webapi/*` session-dead (v2) | HTTP 401 `{"code":"UnauthorizedError","message":...}` | A **second** "session is dead" shape, captured 2026-07-18 (a day after the source doc's capture window) for a server-side password rotation | **Not in `arcaea-auth-behavior.md`** — see [[w-third-auth-envelope]] |

> [!warning] may be reversed by handoffs
> [[handoff-06-credentials-changed-server-side]] is being ingested by a parallel
> agent and may formalize or extend this third-envelope behavior further (e.g. a
> Bearer-token migration is explicitly flagged as a watch item in `CLAUDE.md`). Treat this
> row as current-best-understanding, not final.

`error_code` → exception mapping (`src/coda/arcaea/errors.py`):

| `error_code` | Exception | Handling | Grade |
|---|---|---|---|
| `203` | `SessionExpired` | Transient — re-login once, retry once, fail | FACT |
| `401` | `PlayerNotFound` | Player error — do **not** flag the account, do **not** try the next account | FACT (401 confirmed real, was UNVERIFIED before 2026-07-17) |
| `602` | `AlreadyFriend` | Recoverable — no body to diff, re-read `/friend/me` | FACT |
| any other | `ApiError` | Unknown — on `add_friend`, treat as "this account is unusable, try the next" | UNKNOWN (covers e.g. the never-observed cap-exceeded code) |

**The rule that matters most**: branch on the body (`success`/`error_code`/`code`), never
on the HTTP status. One status spans several codes (400 carries both 203 and 602); one code
arrives under more than one status (401 arrives under both 404 and, in its `code:
"UnauthorizedError"` HTTP-401 form, under a different shape entirely). `/auth/login`'s 403
is the one genuine status-based exception.

## Session lifecycle

- `sid` is `Domain=lowiro.com` (parent domain, not `webapi.`), `Expires` = issuance + 30
  days, `HttpOnly; Secure; SameSite=Strict`. **FACT.**
- `sid` **rotates** at every auth boundary: login, logout, and a rejected tampered cookie
  all issue a fresh one. Never cache a pre-login cookie. **FACT.**
- Expiry is **30 days, non-sliding** — no authenticated response (read or write) re-issues
  `sid`. **STRONG** (server-side TTL could still slide via `store.touch()` without a
  `Set-Cookie`; not observable from outside). Design consequence: `expires_at` is an
  optimization only; `error_code: 203` (or the HTTP-401 v2 envelope) is the authoritative
  "session is dead" signal. **Never assume a non-expired sid is valid.**
- `POST /auth/logout` invalidates immediately, server-side. **Never call it from the bot** —
  it would nuke a pooled session other in-flight work depends on. **FACT.**
- No CSRF token exchange anywhere; protection is `SameSite=Strict` + a CORS allowlist, both
  browser-enforced and irrelevant to a server-side client. **STRONG** (absent across 3
  mutating authed POSTs).
- `sid` alone, with **no** spoofed browser headers at all, gets a 200. **FACT, CLOSED.**
  Header spoofing (Origin/Referer/UA/`sec-ch-ua*`) is kept anyway as Cloudflare insurance —
  see [[w-coherent-browser-identity|Coherent Per-Account Browser Identity]]. **Do not read this fact as
  license to drop spoofing.**

## Friend-slot cap (`max_friend`)

| Value | Meaning | Grade |
|---|---|---|
| `10` | Fresh account's starting cap | FACT (observed live) |
| `15 → 20 → 25` | Ladder, rises in steps of 5 with play progression | OWNER-STATED (the trigger; both ladder endpoints — 10 and 25 — are FACT) |
| not subscription-tied | `max_friend` is orthogonal to Arcaea Online | OWNER-STATED |

**Per-account and mutable — never hardcode.** Read live from `/webapi/user/me`'s
`max_friend` at add time (`src/coda/sessions/pool.py::_capacity`). At this project's ≤50-
player scale, plan for **10 per account** (~5 hand-made bot accounts); reaching 25 needs
real play investment that is not worth it for a bot account.

## Traps

- **[[w-friends-key-removed]]** — `/webapi/user/me` no longer carries `friends`; a direct
  `data['friends']` subscript (the old client's pattern) is a hard `KeyError` on every call
  today.
- **[[w-formdata-504]]** — `aiohttp.FormData` on `add`/`delete` streams chunked with no
  `Content-Length`; lowiro's origin hangs, Cloudflare 504s.
- **[[w-friend-code-strip]]** — stripping every non-digit from user input (rather than
  separators only) manufactures a plausible 9-digit code out of garbage.
- **[[w-status-vs-body]]** — re-logging in on any HTTP 400 (the old client's rule) is wrong
  twice over: a duplicate add is also 400, and an unknown friend code is 404 with the
  identical envelope.
- **[[w-third-auth-envelope]]** — a second "session is dead" shape (HTTP 401
  `UnauthorizedError`) exists beyond `error_code: 203`, undocumented in the source doc,
  captured a day later.
- `rating: -1` (PTT hidden, not zero), `score: 0` (a real score, not null), and
  `showcase_characters` (ints **or** dicts in the same response) are DTO-boundary sentinels
  — see [[arcaea|arcaea (module)]] §sentinels for the handling.
- `add`/`delete` field asymmetry (`friend_code` vs `friend_id`) — easy to pass the wrong
  identifier since `ArcaeaAccount` stores both.

## Source

[[arcaea-auth-behavior]] — authoritative and more detailed than this page; every
claim there is individually graded in its §9 table. Re-verify after any lowiro update rather
than trusting this page indefinitely.
