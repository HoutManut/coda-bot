---
type: meta
title: "Log"
status: active
created: 2026-07-21
updated: 2026-07-21
tags: [meta, log]
aliases: ["Operations Log"]
---

# Operations Log

Append-only. Newest entry at the TOP.

---

## 2026-07-21 — LINT + REMEDIATION

Full health check → [[lint-report|Lint Report]]. 2 BLOCKER, 8 HIGH, 6 MEDIUM, 3 LOW.
Both BLOCKERs and every mechanical HIGH fixed the same day.

- **Dead links 61 → 19.** Not typos — a link-style mismatch: pages linked by H1, Obsidian
  resolves by filename. Fixed with `aliases:` on 60 pages, `[[filename|Label]]` in [[index]],
  `\|` escaping inside table cells, and removal of path-style targets. Titles containing `/`
  were the silent failure — Obsidian reads them as paths.
- **Template comments leaked into frontmatter** on 6 files (lint found 3). Stripped.
- `questions/h-credentials-changed-server-side` claimed no owner-notification path exists;
  `players/notify.py:40` + `session.py:87` ship one. Narrowed the question to the part that is
  genuinely open (terminal `is_valid = False` vs a re-auth prompt for a *changed* credential).
- Security scan (the one check lint never ran): **clean**.
- 19 links to 7 targets remain, all real gaps, declared in [[index#Known stubs]].

Two categories are still only partially swept — duplicate detection (stopped mid-way through
`max_friend` numeric consistency) and cross-slice contradictions (one confirmed, no full
d-/w-/h- sweep). Worth a second lint pass later.

---

## 2026-07-21 — INGEST (all 16 Layer-1 sources)

Three parallel agents, disjoint folders, filename prefixes (`d-`, `w-`, `h-`) to avoid collisions.

- **Tier 1** (domain-reference, scoring, potential, score-mapping) → 4 `sources/`, 4 `domains/`, 7 `gotchas/d-*`. No internal contradictions.
- **Tier 2** (auth-behavior, api-layer, api-research-tasks) → 3 `sources/`, `domains/auth-and-sessions`, 3 `modules/`, 2 `flows/`, 6 `gotchas/w-*`, 8 `decisions/w-*`.
- **Tier 3** (db-schema, tournament-layer, all handoffs, self-hosting) → 9 `sources/`, `modules/db`, `domains/tournaments`, `flows/live-updates`, 10 `questions/h-*`, 6 `decisions/h-*`.

63 pages total. Rewrote [[Index]], [[Hot Cache]], [[Ingest Queue]].

**Findings surfaced by the ingest** (not previously written down in any source doc):

1. A **third auth envelope** exists — HTTP 401 `UnauthorizedError` from a server-side password rotation, mapped to `SessionExpired`. Captured 2026-07-18, one day after [[arcaea-auth-behavior]]'s window closes. Handled in code, absent from the "authoritative" wire doc. → [[A third "session is dead" envelope exists, undocumented in the auth-behavior source]]
2. **An API-layer findings writeup (2026-07-19, since archived out of the repo) was an unfiled source.** It held eight robustness fixes that postdate [[arcaea-api-layer]]: `TransportError`, a 30s request timeout, a rate-limiter cancellation leak fix, `raise_for_login_envelope` extraction, `CHROME_VERSIONS` ceiling bump, per-friend fault-tolerant parsing, `encode_multipart` CRLF/boundary validation, last-slot placement retry. Added to [[Ingest Queue]].
3. `SessionPool.place(exclude=…)` and `_MAX_PLACEMENT_ATTEMPTS = 3` (last-slot race) are shipped behavior the api-layer doc does not describe.
4. `AccountSession` (with `BotSession` + own-path `PlayerCredentialAdapter` on top) generalizes the doc's `BotSession` sketch.
5. The delisted-song / negative-CC trap was not found in any ingested source — it belongs to an unwritten `/song` handoff. Not filed; no page invented for it.

---

## 2026-07-21 — SCAFFOLD

Created the vault at the coda-bot repo root. Mode B (repository) + Mode E (research).

- Skipped `.raw/`: the source docs, `docs/`, and `src/` already are the source layer.
- Created `wiki/` with sources, domains, modules, flows, decisions, gotchas, questions, meta, _templates.
- Wrote [[Index]], [[Hot Cache]], [[Overview]], [[Ingest Queue]], [[Conventions]], `wiki/CLAUDE.md`, templates.
- Nothing ingested.
