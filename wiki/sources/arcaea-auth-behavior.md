---
type: source
status: active
path: arcaea-auth-behavior.md
lines: 866
dated: 2026-07-17
verified: 2026-07-17
supersedes: []
superseded_by: []
created: 2026-07-21
updated: 2026-07-21
tags: [source, wire, auth, sessions, lowiro]
aliases: ["arcaea-auth-behavior.md"]
---

# arcaea-auth-behavior.md

## Covers

The **authoritative** live-capture record of lowiro's private webapi: hosts/endpoints,
the `sid` cookie, login flow and its two-envelope error surface, session lifecycle
(rotation, 30-day non-sliding expiry, logout), the friends list (`GET /webapi/friend/me`,
not `/webapi/user/me`), `max_friend` capacity ladder, score field shape by access tier,
`add`/`delete` asymmetry, the `aiohttp.FormData` → 504 finding, and the three-tier data
model (friend / own-no-sub / own+sub). Captured via HTTP Toolkit MITM against
`arcaea.lowiro.com`, one throwaway bot account and one played-in subscribed account, three
sessions, ~30 minutes total, plus a `curl` replay. **Every claim carries a grade** (§9 of
the source) — FACT / STRONG / OWNER-STATED / INFERENCE / DISPUTED / WEAK / UNTESTED /
UNKNOWN / ASSUMED — and this wiki page carries that grade forward rather than flattening it.

`wiki/CLAUDE.md` and `wiki/meta/conventions.md` set precedence: **live wire behavior
outranks this document**, and this document outranks the other source docs generally and
`CLAUDE.md`. Where the old client (`arcaea_online/`) disagreed, this source wins (§8 of the
source lists exactly what not to port).

## Key claims

- Friends live at `GET /webapi/friend/me`, **not** `/webapi/user/me` — lowiro removed the
  `friends` key from `/me`. **FACT.** Encoded in `src/coda/arcaea/endpoints.py` /
  `dto/me.py` / `dto/friend.py` — see [[arcaea (module)]].
- Branch on the response **body** (`success` / `error_code`), never the HTTP status: 400 and
  404 both carry `{"success":false,"error_code":N}`. **FACT.** Encoded in
  `src/coda/arcaea/errors.py::raise_for_envelope`.
- `/auth/login` failure is a **second, unrelated envelope** — `{"error":{"name":"ForbiddenError","message":104}}` under HTTP 403. **FACT.** Encoded in
  `raise_for_login_envelope`, kept deliberately separate from the webapi envelope parser.
- `error_code: 401` = player not found (not account-cap or malformed-shape). **FACT, was
  UNVERIFIED before this capture.** lowiro does not validate friend-code shape server-side —
  local validation is entirely our business. Encoded in
  `src/coda/utils/friend_code.py::clean_friend_code` + [[w-friend-code-strip]].
- `aiohttp.FormData` → chunked body → lowiro origin hang → Cloudflare 504; a hand-built
  `bytes` body with `Content-Length` gets a normal 404/401. **FACT, CLOSED.** Encoded in
  `src/coda/arcaea/client.py::encode_multipart` — see [[w-formdata-504]].
- `sid` alone (no browser headers at all) suffices for a 200; `_ga`/`ctrcode` carry no
  session state. **FACT, CLOSED.** Header spoofing is kept anyway as Cloudflare insurance,
  not because it is required — see [[w-coherent-browser-identity]].
- `time_played` is server-assigned UTC ms, not client-supplied — proven by a deliberately
  skewed device clock. **FACT, CLOSED.** The entire trust model for any time-boxed feature
  (tournaments) rests on this.
- `max_friend` starts at 10 on a fresh account, rises by 5 with play to a hard max of 25;
  **not** subscription-tied. **FACT** (both ladder endpoints observed) + **OWNER-STATED**
  (the step trigger). Plan for 10/account — see [[sessions (module)]].
- `add`/`delete` are asymmetric: `add` takes `friend_code`, `delete` takes `friend_id`
  (= `user_id`). **FACT.** `add_friend(code) -> arc_user_id` is **unimplementable** — no
  friend object ever carries the code that was submitted, so the caller must diff
  `GET /webapi/friend/me` against prior state. **FACT.**
- `rating: -1` means the player hid their PTT, decoding naively to a corrupt `-0.01`.
  **FACT.** `score: 0` is a real score, not null. **FACT.** `showcase_characters` holds ints
  **or** dicts in the same response. **FACT.** All three are DTO-boundary sentinels — see
  [[arcaea (module)]] §sentinels.
- `recent_score` shape for a never-played friend is **unverified** (`null`/`[]`/omitted all
  plausible) — **OWNER-STATED, sample had no unplayed account.** The shipped DTO treats
  `friend.get("recent_score") or []` as load-bearing regardless of which shape arrives.
- `GET /webapi/score/song/me/all` being a **full per-play history** is **DISPUTED** — the
  source's own evidence (count ≈ FTR chart count, aggregate fields on each row) argues it is
  one row per (song, difficulty) — a per-chart record, not a log. Not yet re-captured.
- Three data tiers exist and are gated **per route, not per prefix** — `total_ranking/world`
  is free while its sibling `total_ranking/friend` is subscription-only. **OWNER-STATED.**

## Contradicts / reversed by

- Directly reverses the old `arcaea_online/` client's behaviors: `OPTIONS /auth/login`
  preflight, `GET /auth/me`, re-login-on-HTTP-400, hardcoded `Content-Length: '41'`. See §8
  of the source and [[w-status-vs-body]].
- Corrects `CLAUDE.md`'s prior claim that `/webapi/user/me` carries a `friends` key — the
  live wire moved it to `/webapi/friend/me`. `CLAUDE.md` in this repo has since been
  corrected to match.
- **Does not itself document** the HTTP-401 `{"code":"UnauthorizedError"}` "third envelope"
  seen for a server-side password rotation — that was captured 2026-07-18, one day *after*
  this document's capture window (2026-07-17), and lives only in
  `src/coda/arcaea/errors.py`'s docstring and the archived API-layer findings writeup (not
  any source doc). This document is stale on that one point; see [[w-third-auth-envelope]].
- The handoff notes reverse this document's design intent (not its wire facts) around the
  bot-code fake-not-found oracle — see [[w-honest-bot-code-refusal]] and the staleness note
  on [[Registration]].

## Feeds

[[Auth & Sessions]], [[arcaea (module)]], [[sessions (module)]], [[players]],
[[Registration]], [[Session Lease]], [[w-formdata-504]],
[[w-friend-code-strip]], [[w-status-vs-body]], [[w-friends-key-removed]],
[[w-third-auth-envelope]], [[w-release-order]]
