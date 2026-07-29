---
type: meta
title: "Ingest Queue"
status: active
created: 2026-07-21
updated: 2026-07-21
tags: [meta, queue]
aliases: ["Ingest Queue"]
---

# Ingest Queue

All 16 originally-queued sources were ingested 2026-07-21. The tables below are kept as the
record of what feeds what. New work is at the bottom, under **Pending**.

## Pending

| Source | Why it matters | Status |
|---|---|---|
| API-layer findings writeup, 2026-07-19 (archived out of the repo) | Eight robustness fixes postdating [[arcaea-api-layer]]: `TransportError`, 30s timeout, rate-limiter cancellation leak, `raise_for_login_envelope` split, `CHROME_VERSIONS` bump, per-friend fault-tolerant parsing, `encode_multipart` CRLF/boundary validation, last-slot placement retry. No other source doc records these; the code in `src/coda/arcaea/` is authoritative. | **not ingested** |
| `src/coda/catalog/`, `settings/`, `extensions/`, `admin/`, `approvals/`, `utils/` | Modules with no wiki page yet | **not ingested** |
| Score poll loop + chart resolution (code only) | Two flows with no page; no design doc exists for either | **not ingested** |

---

## Ingested 2026-07-21

Layer-1 sources and what they feed. Ingest order was top-down: earlier docs are referenced by later ones.

## Tier 1 — domain foundations

| Source | Lines | Feeds | Status |
|---|---|---|---|
| [[arcaea-domain-reference]] | 395 | `domains/Catalog` | ingested |
| [[arcaea-scoring]] | 203 | `domains/Scoring` | ingested |
| [[arcaea-potential]] | 433 | `domains/Potential` | ingested |
| [[arcaea-score-mapping]] | 109 | `domains/Score Mapping`, `flows/Chart Resolution` | ingested |

## Tier 2 — wire behavior

| Source | Lines | Feeds | Status |
|---|---|---|---|
| [[arcaea-auth-behavior]] | 865 | `domains/Auth & Sessions`, `gotchas/` | ingested |
| [[arcaea-api-layer]] | 623 | `modules/arcaea`, `modules/sessions`, `flows/Registration` | ingested |
| [[arcaea-api-research-tasks]] | 310 | `questions/` | ingested |

## Tier 3 — persistence & unbuilt

| Source | Lines | Feeds | Status |
|---|---|---|---|
| [[arcaea-bot-db-schema]] | 571 | `modules/db` | ingested |
| [[arcaea-tournament-layer]] | 315 | `domains/Tournaments`, `questions/` | ingested |
| [[handoffs-readme]] | 51 | `questions/` | ingested |
| [[handoff-06-credentials-changed-server-side]] | 48 | `questions/` | ingested |
| [[handoff-08-live-updates-poster]] | 160 | `flows/Live Updates` | ingested |
| [[handoff-09-b30]] | 288 | `questions/` | ingested |
| [[handoff-10-score-history-backfill-research]] | 92 | `questions/` | ingested |
| [[handoff-11-ownership-blob]] | 155 | `questions/` | ingested |
| `docs/self-hosting.md` | 129 | `sources/` | ingested |

## Not a document, still a source

`src/coda/` itself feeds `modules/`. Ingest per package, after the matching Tier-2 doc —
the doc says what was intended, the code says what shipped, and the gap is the interesting part.

## Rule

Handoff notes **reverse** claims in the older source docs by design. When ingesting a handoff
that contradicts an already-filed page, mark the older page `status: stale` and link forward.
Never silently overwrite.
