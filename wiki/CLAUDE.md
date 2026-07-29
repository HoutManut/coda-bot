# coda-bot Wiki

Mode: B (Repository) + E (Research)
Purpose: a queryable, cross-referenced knowledge base for coda-bot.
Owner: marut
Created: 2026-07-21

## Layers

```
src/         Layer 1 — the code itself. Always wins over a wiki page.
docs/        Layer 1 — user-facing docs (self-hosting).
wiki/        Layer 2 — the knowledge base (this folder).
wiki/CLAUDE.md  Layer 3 — schema + rules (this file).
```

The vault was originally derived from a set of research/design source documents
that are **archived outside this repository**. `sources/` pages are what survives
of them — treat those pages as the record, not as pointers to files you can open.
Their `path:` frontmatter names the archived document, not a path in this repo.

## Structure

```
wiki/
├── index.md        master catalog — update on EVERY page create
├── log.md          append-only operations log, newest entry at TOP
├── hot.md          ~500-word recent-context cache, overwritten each session
├── overview.md     executive summary of the whole system
├── sources/        one page per archived source doc: what it covered, grade, staleness
├── domains/        Arcaea game knowledge: catalog, scoring, potential, wire API
├── modules/        one page per src/coda/ package
├── flows/          end-to-end paths: register, poll loop, score resolution, session lease
├── decisions/      ADRs — a choice, its alternatives, why it went that way
├── gotchas/        traps that regress silently; each states the wrong behavior it replaced
├── questions/      open/unbuilt work, contradictions, things to re-verify against the wire
├── meta/           dashboards, lint reports, conventions
└── _templates/     note templates per type
```

## Conventions

- YAML frontmatter on every page: `type, status, created, updated, tags` minimum.
- Wikilinks `[[Page Name]]` — filenames unique, no paths.
- `wiki/index.md` is the master catalog — update on every ingest.
- `wiki/log.md` is append-only; new entries at the TOP.
- Never modify `docs/` or `src/` from a wiki operation.
- **The code and the live wire are the source of truth.** Wiki pages summarize and cross-reference; when a page disagrees with shipped code or an observed response, the page is wrong and gets `status: stale`.
- **The private webapi changes without notice.** Any page making a wire claim carries `verified:` (a date) and a confidence grade (see [[auth-and-sessions]]). Undated wire claims are suspect.
- **Newer decisions reverse older pages by design** — a page contradicting a later entry in `decisions/` is stale, not authoritative. Encode that direction on the page.

## Operations

- Ingest: `ingest <file>` → creates/updates sources + domains + gotchas pages
- Query: ask anything — reads `hot.md`, then `index.md`, then drills in
- Lint: "lint the wiki"
- Save: "/save" to file a conversation insight
