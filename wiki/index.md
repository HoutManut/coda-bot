---
type: meta
title: "Index"
status: active
created: 2026-07-21
updated: 2026-07-21
tags: [meta, index]
aliases: ["coda-bot Wiki — Master Catalog"]
---

# coda-bot Wiki — Master Catalog

63 pages. All 16 Layer-1 documents ingested 2026-07-21.

## Entry points

[[overview|Overview]] · [[hot|Hot Cache]] · [[log|Log]] · [[ingest-queue|Ingest Queue]] · [[conventions|Conventions]]

## Domains — game + wire knowledge

| Page | Covers |
|---|---|
| [[catalog\|Catalog]] | Songs, difficulties, packs, level `×2`/`×2+1`/`-1` encoding, CC `×10`, override resolution |
| [[scoring\|Scoring]] | Score formula, pure/far/lost, grades, `clear_type`/`modifier`, gauge |
| [[potential\|Potential]] | Play rating, b30/r10, PTT `×100`, hidden sentinel, recent-30 admission |
| [[score-mapping\|Score Mapping]] | Wire `(song_id, difficulty)` → `song_difficulties`, difficulty ints, `byd_2` |
| [[auth-and-sessions\|Auth & Sessions]] | Endpoints, envelopes, `error_code` taxonomy, session lifetime, friend-slot cap |
| [[tournaments\|Tournaments]] | Rounds, windows, validity, state machine, tiers — **not built** |

## Modules — `src/coda/`

[[arcaea]] · [[sessions]] · [[players]] · [[db]]

Not yet written: `catalog`, `settings`, `extensions`, `admin`, `approvals`, `utils`.

## Flows

[[registration|Registration]] (both paths) · [[session-lease|Session Lease]] · [[live-updates|Live Updates (poster)]] (**planned**)

Not yet written: `Score Poll Loop`, `Chart Resolution`.

## Gotchas — silent-regression traps

**Domain / decoding**
- [[d-level-cc-sentinel-values|Level/CC sentinels: `0` = TBA, `-1` = err-only `?`]]
- [[d-ptt-hidden-sentinel|PTT `-1` means HIDDEN — and it is a different field from chart CC]]
- [[d-score-zero-is-real|`score: 0` is a real score, not missing data]]
- [[d-unknown-cc-no-play-rating|Unknown CC yields NO play rating — never substitute 0]]
- [[d-hard-gauge-early-submit|Hard-gauge loss submits early; the r10 exclusion needs BOTH fields]]
- [[d-r10-impossible-friend-path|r10 cannot be reconstructed on the friend path; b30 can]]
- [[d-byd2-game-song-id-resolution|`byd_2` needs `game_song_id`, and the step order matters]]

**Wire / transport**
- [[w-formdata-504|`aiohttp.FormData` hangs `add_friend`, then Cloudflare 504s]]
- [[w-friend-code-strip|Stripping every non-digit manufactures a fake friend code]]
- [[w-friends-key-removed|`/webapi/user/me` no longer carries a `friends` key]]
- [[w-release-order|`SessionPool.release` must unfriend before clearing `bot_account_id`]]
- [[w-status-vs-body|Re-logging in on HTTP 400 masks real domain errors]]
- [[w-third-auth-envelope|A third "session is dead" envelope, undocumented in the source]]

## Decisions

**Wire layer**
- [[w-arcaea-never-imports-db|`src/coda/arcaea/` never imports `coda.db`]]
- [[w-branch-on-body-not-status|Branch on the response body, never the HTTP status]]
- [[w-hand-built-multipart|Hand-build the multipart body; never `aiohttp.FormData`]]
- [[w-coherent-browser-identity|One fixed, coherent Chrome identity per account]]
- [[w-local-friend-code-validation|Validate friend-code shape locally, before any request]]
- [[w-honest-bot-code-refusal|Refuse a bot-account code honestly, not with a mimicked not-found]]
- [[w-sid-confined-to-sessions|`sessions/` is the only module that knows what a `sid` is]]
- [[w-single-fernet-key|One `FERNET_KEY`, no rotation path]]

**Ownership & persistence**
- [[h-one-account-per-user|One account per Discord user; no atomic switching]]
- [[h-login-upgrades-link-in-place|Logging in upgrades an existing link in place — not a switch]]
- [[h-owner-consent-on-second-claim|A second unproven claim asks the owner; silence never means yes]]
- [[h-straying-preserves-history|Straying keeps `play_scores` — fixed policy, not a tradeoff]]
- [[h-bot-accounts-excluded-bidirectionally|Bot accounts excluded in both directions]]
- [[h-no-orm-relationships|No `relationship()` anywhere; joins are explicit]]

## Questions — open

| Question | Blocks |
|---|---|
| [[h-backfill-worth-building\|Are there enough tier-3 users to justify backfill at all?]] | backfill |
| [[h-backfill-unsubscribed-failure-mode\|What do the score endpoints return with no subscription?]] | backfill |
| [[h-song-me-all-log-vs-record\|Is `score/song/me/all` a play log or one row per chart?]] | backfill, b30 |
| [[h-credentials-changed-server-side\|Can a stored credential go stale server-side?]] | own path |
| [[h-live-update-post-filters\|What filters decide whether a play is worth posting?]] | live poster |
| [[h-recent-duplicate-suppression\|Suppress or merely delay a play `/recent` already showed?]] | live poster |
| [[h-ownership-blob-open-before-building\|What must settle before the ownership blob is built?]] | ownership blob |
| [[h-catalog-schema-open-questions\|What is unresolved in the catalog schema design?]] | catalog |
| [[h-tournament-attempt-overhead\|How long is song-select → load → results, really?]] | tournaments |
| [[h-tournament-clock-skew\|How far does the bot's clock skew from lowiro's?]] | tournaments |

## Sources — archived originals

These pages are what survives of the research/design documents the vault was built
from; the originals are archived outside this repository.

Domain + implementation docs: [[arcaea-domain-reference]] · [[arcaea-scoring]] · [[arcaea-potential]] · [[arcaea-score-mapping]] · [[arcaea-auth-behavior]] · [[arcaea-api-layer]] · [[arcaea-api-research-tasks]] · [[arcaea-bot-db-schema]] · [[arcaea-tournament-layer]]

Handoff notes (designed-but-unbuilt work units): [[handoffs-readme]] · [[handoff-06-credentials-changed-server-side|06 — credentials changed server-side]] · [[handoff-08-live-updates-poster|08 — live-updates poster]] · [[handoff-09-b30|09 — b30]] · [[handoff-10-score-history-backfill-research|10 — score-history backfill]] · [[handoff-11-ownership-blob|11 — ownership blob]]

`docs/`: [[self-hosting]]

**Not yet ingested**: the 2026-07-19 API-layer findings writeup, since archived out of the repo — see [[ingest-queue|Ingest Queue]].

## Known stubs

Linked from real pages but not written yet. These links are deliberate markers, not breakage —
lint treats a target listed here as intentional.

| Target | Would live in | Linked from |
|---|---|---|
| `b30` | `flows/` or `domains/` | 5 pages |
| `Score history backfill` | `flows/` | 4 pages |
| `Score Poll Loop` | `flows/` | `domains/tournaments` ×2 |
| `h-tournament-scoring-rule-parameter` | `decisions/` | tournaments ×3 |
| `h-manual-bot-account-creation` | `decisions/` | `sources/self-hosting` ×2 |
| `h-b30-cache-stores-sum` | `decisions/` | `sources/handoff-09-b30` |
| `h-no-catalog-inferred-ownership` | `decisions/` | `sources/arcaea-tournament-layer` |

## Meta

- [[conventions|Conventions]]
- [[lint-report|Lint Report]] — 2026-07-21 health check, plus what was fixed after it
