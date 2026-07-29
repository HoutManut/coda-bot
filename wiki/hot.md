---
type: meta
title: "Hot Cache"
status: active
created: 2026-07-21
updated: 2026-07-21T00:00:00
tags: [meta, cache]
aliases: ["Recent Context", "Hot Cache"]
---

# Recent Context

## Last Updated
2026-07-21. Vault scaffolded and all 16 Layer-1 sources ingested in one pass. 63 pages.

## Key Recent Facts
- Vault root = the coda-bot repo. `src/` and `docs/` are Layer 1 — there is no `.raw/`. The original research/design source docs are archived **outside** the repo; `sources/` pages are what survives of them.
- Precedence: live wire > `src/` > root `CLAUDE.md` > this wiki. A wiki page that disagrees with anything above it is a bug in the wiki.
- **A third auth envelope exists** — HTTP 401 `UnauthorizedError` from server-side password rotation → `SessionExpired`. Captured 2026-07-18, one day after [[arcaea-auth-behavior]]'s window closes. Shipped in code, absent from that source.
- [[arcaea-bot-db-schema]] §9's dedup sketch (separate tier-1/tier-2 identity) does not match shipped `play_score.py`, which uses one identity tuple for both with `wire_play_id` as a secondary guard. The shipped design is recorded only in [[db]] and the code.
- [[arcaea-potential]] §7's CC-precision hedge is reversed by [[handoff-09-b30]] §3 — catalog CCs are exact, copied from the game.
- API-layer robustness fixes that postdate [[arcaea-api-layer]] (`TransportError`, 30s request timeout, rate-limiter cancellation leak, and five more) are shipped in `src/coda/arcaea/` but only partly filed here — see [[arcaea]]. Read the code as authoritative there.

## Recent Changes
- Created: 16 `sources/`, 6 `domains/`, 4 `modules/`, 3 `flows/`, 13 `gotchas/`, 14 `decisions/`, 10 `questions/`
- Rewrote: [[Index]], [[Log]], [[Ingest Queue]]

## Lint status (2026-07-21)

Full check run and remediated: 2 BLOCKER + 8 HIGH closed, security scan clean.
19 links to 7 targets stay dead on purpose — real unwritten pages, declared in
[[index#Known stubs]]. Duplicate-detection and cross-slice contradiction sweeps
were only partial; a second lint pass is worth it.

**Link style matters here**: Obsidian resolves by FILENAME. Link as
`[[filename|Readable Label]]`, escape the pipe as `\|` inside table cells, and never
link a title containing `/` — it parses as a path.

## Active Threads
- Four decision pages are referenced but unwritten: `h-tournament-scoring-rule-parameter`, `h-b30-cache-stores-sum`, `h-no-catalog-inferred-ownership`, `h-manual-bot-account-creation`.
- Modules unwritten: `catalog`, `settings`, `extensions`, `admin`, `approvals`, `utils`. Flows unwritten: `Score Poll Loop`, `Chart Resolution`.
- The delisted-song / negative-CC trap appears in no ingested source — it belongs to unwritten `/song` design notes. Deliberately not filed.
