---
type: source
status: active
path: arcaea-api-layer.md
lines: 623
dated: 2026-07-21
verified: 2026-07-21
supersedes: []
superseded_by: []
created: 2026-07-21
updated: 2026-07-21
tags: [source, implementation, arcaea, sessions, players]
aliases: ["arcaea-api-layer.md"]
---

# arcaea-api-layer.md

## Covers

The **implementation doc** for `src/coda/arcaea/` (pure wire), `src/coda/sessions/`
(session lifecycle), and the registration flow built on top (`src/coda/players/`). Explicit
in its own preamble: [[arcaea-auth-behavior]] is authoritative on all wire
behavior; this doc is the design built on top of it, and where the two disagree,
`arcaea-auth-behavior.md` wins and this doc is stale. As of its 2026-07-21 status line, it
records steps 1–7 of the module layout as **built and verified**, plus the poller, score
storage, chart resolution, and `/recent` (§8) as **built too**. Not built: the live-update
poster and tournaments.

## Key claims

- **Layer rule**: `arcaea/` never imports `db/` — not stylistic, importing `coda.db` builds
  the async engine at import time, so a violation makes the wire layer unimportable without
  a live database. **Verified against shipped code**: `src/coda/arcaea/client.py`,
  `auth.py`, `endpoints.py`, `errors.py` import nothing from `coda.db`.
- **`auth.login()` returns `(sid, expires_at)`; never persists.** Verified — the caller
  (`sessions/session.py::AccountSession._refresh`) does the persisting via
  `account.store_session(...)`.
- **`sessions/` is the only module that knows what a sid is; `bot_account_id` appears only
  in `sessions/pool.py`.** Verified against `sessions/pool.py` and `sessions/session.py` —
  `players/service.py` and `players/session.py` reach sessions only through
  `SessionPool`/`AccountSession`/`BotSession`, never touching a sid or a `bot_account_id`
  directly.
- **Two error envelopes** (`/webapi/*` body-based, `/auth/login` 403) are documented here.
  **Shipped code has a third** — `errors.py`'s own docstring calls out an HTTP 401
  `{"code":"UnauthorizedError"}` shape, captured 2026-07-18 (one day after this doc's dated
  claims), for a server-side password rotation. This doc does not mention it. See
  [[w-third-auth-envelope]] and the report at the end of this ingest.
- **`add`/`delete` asymmetry** (`friend_code` vs `friend_id`) — verified against
  `src/coda/arcaea/endpoints.py::add_friend`/`remove_friend`.
- **`add_friend(code) -> arc_user_id` is unimplementable; the caller diffs.** Verified —
  `endpoints.py::unknown_friends` implements exactly this diff, and `players/service.py`
  calls it.
- **Registration ordering**: validate 9 digits locally → check `_find_by_code` (zero API
  calls if known) → `place()` → `add_friend` → diff. Verified against
  `players/service.py::register_by_code`, with one addition beyond this doc's original
  design: `_place_and_add` retries past an `ApiError` (last-slot placement race) up to
  `_MAX_PLACEMENT_ATTEMPTS = 3`, documented only in the archived API-layer findings writeup (
  2026-07-19), not in this source.
- **`SessionPool.release` order: unfriend by `arc_user_id` first, then NULL
  `bot_account_id`.** Verified against `sessions/pool.py::release` — the docstring there
  states the ordering explicitly and never raises on a failed unfriend.
- **Reserved-code fake-not-found is dropped**; a bot-account code gets an honest "you can't
  use that friend code" refusal. Verified against `players/reserved.py` — no
  `mimic_not_found_latency` exists in shipped code.
- **`ScoreResult` — one type, nullable extras** for tier-1-vs-tier-2/3 richness. Verified
  against `src/coda/arcaea/dto/score.py` shape referenced from `dto/friend.py` and
  `dto/me.py`.
- **Cadence is jittered** (`config.poll_interval` default 90s ± 40%), not metronomic; a poll
  key is namespaced `("bot", id)` / `("own", id)`. This is recorded in the doc's §8 as "as
  built" — matches `src/coda/scores/poller.py`/`keys.py` (read-only confirmation, not
  re-read line-by-line in this pass).

## Contradicts / reversed by

- This doc's §10 "Open — blocking" is fully closed by its own account (both items resolved
  2026-07-17); nothing here blocks the client build as of ingest.
- **Gap this ingest found**: a separate API-layer findings writeup (dated 2026-07-19, since
  archived out of the repo) documented eight further robustness fixes on top of this doc's described
  design — a `TransportError` type, a request timeout, a rate-limiter cancellation leak fix,
  a login-envelope misfiling fix, a browser-identity version bump, per-entry-fault-tolerant
  friend parsing, multipart value validation, and the last-slot placement retry. None of
  these appear in `arcaea-api-layer.md` itself. Treat `arcaea-api-layer.md` as the
  **design**, and shipped code as the **current state** — see the
  contradiction note in [[arcaea (module)]] and [[sessions (module)]].
- Does not restate `arcaea-auth-behavior.md`'s findings and explicitly defers to it on any
  disagreement (see this doc's own preamble).

## Feeds

[[arcaea (module)]], [[sessions (module)]], [[Registration]], [[Session Lease]],
[[w-third-auth-envelope]], [[w-formdata-504]], [[w-friend-code-strip]],
[[w-honest-bot-code-refusal]]
