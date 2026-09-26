---
type: decision
status: active
date: 2026-07-17
reverses:
created: 2026-07-21
updated: 2026-07-21
tags: [decision, wire, identity, cloaking]
aliases: ["One fixed, internally-consistent Chrome identity per account — not per-request rotation", "Decision: Coherent Per-Account Browser Identity"]
---
# One fixed, internally-consistent Chrome identity per account — not per-request rotation

## Context

The old client used `fake_useragent` to pick a **new random User-Agent on every request**,
while every other browser-fingerprint-relevant header (in particular `sec-ch-ua*` client
hints) stayed fixed. Header-level cloaking exists at all only as insurance — live capture
(`arcaea-auth-behavior.md` §2.1, §8) showed a bare `curl` with a default UA and no
`Origin`/`Referer` gets a 200 today, so nothing here is *required* by the API as it currently
behaves.

## Alternatives

| Option | Why not |
|---|---|
| Keep `fake_useragent`, rotating the UA per request | A **self-contradicting browser**: a UA claiming one OS/browser build alongside frozen `sec-ch-ua` client hints describing a different one. This is worse than sending no spoofed headers at all — a plain default UA is unremarkable, but a UA that disagrees with its own client hints is a coherent tell that a request is not coming from a real, stable browser install |
| Drop header spoofing entirely, reasoning from §2.1 that it is "proven unnecessary" | Rejected explicitly (`arcaea-auth-behavior.md` §8's closing warning, `arcaea-api-layer.md` §2): "unenforced today" is not "proven unnecessary" — Cloudflare fronts this API and can tighten bot rules with no notice, the cost of keeping a static header dict is near zero, and the bot accounts are hand-made and effectively unreplaceable if banned |
| Generate a fresh identity per request, but derive `sec-ch-ua*` from the same UA each time (attempt statelessness while staying internally consistent) | Adds complexity for no benefit over generating once and storing it — a real browser's UA and client hints do not change moment to moment either, so per-request regeneration is itself implausible traffic even if internally consistent |

## Decision

Each account — bot or player — gets **one fixed, self-consistent Chrome build** for its
whole life: User-Agent, the `sec-ch-ua` triplet, and platform, all derived from a single
`(platform, chrome_major_version)` pair chosen once
(`src/coda/arcaea/identity.py::generate()`), so the fields **cannot disagree** by
construction. Generated once at seed time (bot accounts) or registration time (player
credentials), stored verbatim as JSONB (`bot_accounts.browser_identity` /
`player_credentials.browser_identity`), and bound per-task via a contextvar
(`identity.bind()`/`identity.current()`) around every wire call that account makes.
**Coherence beats freshness.**

## Consequences

- `fake_useragent` was removed outright, **not** reused just to seed the one-time value at
  create time — it yields a UA with no matching client hints, so even a single
  `fake_useragent` call at seed time would reintroduce the exact UA/client-hints mismatch
  this decision exists to avoid. The replacement (`identity.generate()`) derives the whole
  set from one `(platform, major)` pair internally.
- Re-seeding an *existing* account should reuse its stored identity, not call `generate()`
  again — a browser does not change overnight, and swapping a played-in account's identity
  mid-life would itself be the kind of implausible change real traffic never exhibits.
- This is a **headers-only** guarantee. TLS (JA3) and HTTP/2 fingerprints are `aiohttp`'s,
  not Chrome's, and no amount of header coherence closes that gap — doing so would require a
  transport swap (e.g. `curl_cffi`), explicitly judged not worth it at this project's scale.
- `CHROME_VERSIONS`' ceiling is a recurring chore, not a one-time value — it must be bumped
  periodically (already done once, archived findings writeup fix 5, ceiling 132 → 138) so the
  pool of possible builds tracks real Chrome releases and does not drift into "implausibly
  old build" territory.
- A hand-inserted `BotAccount` row that was never seeded (missing `browser_identity`) falls
  back to `DEFAULT_IDENTITY` via `identity.coerce()`'s defensive validation — a partial or
  malformed stored identity is treated as *worse* than the default (inconsistent) and is
  never partially trusted.

## Enforced at

`src/coda/arcaea/identity.py` — `generate()` (the one-time derivation), `bind()`/`current()`
(the contextvar), `coerce()` (defensive validation of a stored blob). Bound in
`sessions/session.py::AccountSession.call` (every bot session's calls) and
`players/service.py::register_by_credentials` (the own-path login, and by extension every
later poll for that player, since the identity is stored and rebound each time).
`src/coda/arcaea/client.py::_headers()` is the sole reader of `identity.current()`.
