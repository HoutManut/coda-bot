---
type: question
status: open
blocks: [removing the temporary diagnostic-logging block in arcaea/client.py]
source: src/coda/arcaea/client.py:173-185 (temporary-instrument comment)
created: 2026-07-24
updated: 2026-07-24
tags: [question, wire, rate-limit]
---

# What does a real rate limit or Cloudflare challenge from lowiro actually look like?

## Why it is open

Every capture to date is a handful of manual requests — nobody has ever seen lowiro (or the
Cloudflare front in front of it) actually push back under real polling load. Deliberately
probing for it is unsafe: this project runs a handful of hand-made, unreplaceable bot
accounts, and there is no test tier to burn instead. So
the shape is unknown by default, and only passive observation over real traffic can answer
it for free.

## What would answer it

A real pushback event, captured through the temporary instrumentation already in place:
`_DIAGNOSTIC_HEADERS` / `_diagnostics` / `_is_pushback` / `_log_non_2xx` in
`src/coda/arcaea/client.py:173-272`. It whitelists rate-limit/CDN response headers
(`Retry-After`, `RateLimit*`, `cf-ray`, `cf-mitigated`, `Server`), logs them to the file
handler on every non-2xx reply, and forces a Discord ping only when the reply looks like
infrastructure pushback (408/429, 5xx, or a `cf-mitigated`/`Retry-After` header) rather than
a routine envelope failure (404 missing-friend, 401 dead-session).

## Current best guess

No guess — headers have never been observed non-empty in any capture to date, which the
comment block calls "the point": the first real limit announces itself in one of them, or in
a Cloudflare challenge body, whenever polling volume or account count grows enough to
trigger it.

## Answer

Unanswered. Once a genuine 429 or challenge is observed and its shape written into
[[auth-and-sessions]], the instrumentation block should be torn down to at most a live
pushback WARNING — the file already states this as its own deletion condition
(`client.py:178-180`), so this question closes and that cleanup happens together.
