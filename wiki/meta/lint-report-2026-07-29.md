---
type: meta
title: "Lint Report — 2026-07-29"
status: active
created: 2026-07-29
updated: 2026-07-29
tags: [meta, lint]
aliases: ["Lint Report — 2026-07-29"]
---

# Lint Report — 2026-07-29

> [!note] Procedure note
> `skills/wiki-lint/SKILL.md` (referenced by the task brief as the source of the full
> procedure, sub-section schema, and banded thresholds) does not exist anywhere in this
> repository — checked `find . -iname SKILL.md`, only a vendored FastAPI skill under
> `.venv/` matched. This run instead followed the checklist given directly in the task
> instructions (frontmatter, wikilinks, headings, orphans, concept/mention scan, stale
> index entries, stale `seed` pages) plus the DragonScale opt-in detection commands
> verbatim. If a recurring wiki-lint cadence is wanted, author that skill file so future
> runs have one procedure to point at instead of re-deriving it from the task prompt.
>
> This report file will itself show as a 0-inbound-link page on the next lint pass —
> that's expected for a freshly-written dated report, not a regression. Whether to link
> it from `index.md`/`hot.md` (as `lint-report.md`, the 2026-07-21 report, already is) is
> left to the user; not done here since only the user decides what gets fixed.

Pages scanned: 103 markdown files under `wiki/` (excludes `_templates/`) — 102 schema-bearing
content pages plus `CLAUDE.md`, the layer-3 schema doc (no frontmatter expected, excluded
from page-level checks, expected to show as a 0-inbound-link "orphan"). This is a re-run
against the same vault as [[lint-report|the 2026-07-21 report]]; findings below note where a
prior issue was fixed and where it wasn't. Resolution rule for wikilinks: a `[[Target]]`
resolves if `Target` matches a page's filename, H1, or frontmatter `aliases:` entry —
case-insensitive, with or without a leading path segment or trailing `.md`, and with
table-escaped `\|` treated the same as a bare `|` before splitting target from label.

## DragonScale feature detection

```
[ -x ./scripts/allocate-address.sh ] && [ -f ./.vault-meta/address-counter.txt ] → DRAGONSCALE_ADDR=0
[ -x ./scripts/tiling-check.py ] && command -v python3 → DRAGONSCALE_TILE=0
```

Neither `scripts/allocate-address.sh` nor `.vault-meta/address-counter.txt` nor
`scripts/tiling-check.py` exist in this repository (`scripts/` only holds
`dump-songs.sh`, `seed_bot_account.py`, `verify_multipart.py`, `check_font_coverage.py`).
This vault has not adopted DragonScale. Per the opt-in rule, Mechanism 2 (Address
Validation) and Mechanism 3 (Semantic Tiling) are **skipped** — this is expected, not a
gap, and no `## Address Validation` / `## Semantic Tiling` sections follow.

## Summary

- Pages scanned: 103 (102 content pages + `CLAUDE.md`)
- Issues found: 9 (1 critical, 7 warnings, 1 suggestion) — plus two disclosed
  not-fully-run sweeps (below) that are deliberately not counted as clean
- Since the 2026-07-21 report: both blockers fixed (`modules/db.md` `path:`,
  `h-credentials-changed-server-side.md` contradiction), 4 of 6 HIGH findings fixed — the
  two still open are the `verified:`/`grade:` gaps on `modules/arcaea.md` and
  `domains/score-mapping.md` (items 2–3 below). The friend-slot-cap (`max_friend`)
  numeric-consistency check left incomplete last time is now finished (clean — 10→25
  ladder stated consistently everywhere it's cited), and the security scan (never run
  last time) is now complete (clean).

## Critical (must fix)

1. **Dead wikilink** — [[h-real-rate-limit-shape-unknown]] line 18: `[[coda-bot-scale-constraint]]`
   does not resolve to any page filename, H1, or alias in this vault. The name matches a
   *personal Claude Code memory file* (`coda-bot-scale-constraint.md`, outside the repo),
   not a wiki page — it looks like a concept leaked in from an agent's private memory notes
   rather than a real cross-reference. **Fix**: either author a short page capturing the
   scale constraint it's citing (`<50 people, ~5 hand-made bot accounts, no automated
   signup, no test tier to burn`) since that reasoning is load-bearing here and is echoed
   informally elsewhere in the vault, or reword the sentence to drop the bracketed link
   and state the constraint inline instead.

   No other dead links, missing required frontmatter (`type`/`status`/`created`/`updated`/`tags`),
   or broken index-to-file mappings were found — all 102 content pages carry the full
   required set, and cross-checking every `decisions/`, `gotchas/`, and `questions/` filename
   against `index.md` confirms every page is indexed and every open/answered question sits
   in the correct index table for its `status:`.

## Warnings (should fix)

2. `modules/arcaea.md` — the core wire-client module page (`tags: [module, arcaea, wire]`)
   still carries **no `verified:` or `grade:` field at all**, not even an empty placeholder.
   Unresolved from the 2026-07-21 report (its HIGH-9).

3. `domains/score-mapping.md` — `verified:` present but **empty**, `tags` include `wire`.
   Unresolved from the 2026-07-21 report (its HIGH-10).

4. Four wire-touching pages still have **no `verified:` field at all**: `modules/sessions.md`,
   `flows/registration.md`, `flows/session-lease.md`, `gotchas/d-byd2-game-song-id-resolution.md`
   (the last also has `verified:` present-but-empty). Unresolved from the 2026-07-21 report
   (its MEDIUM-15).

5. Systemic `grade:` gap: only **4 of 35** `domains/`/`modules/`/`flows/`/`gotchas/` pages carry
   a `grade:` field (`modules/scores.md`, `flows/chart-resolution.md`, `flows/score-poll-loop.md`,
   `flows/live-updates.md` — all score-tracking pages filed 2026-07-22 to -24). This is
   progress since the 2026-07-21 report (0/24 then), but the foundational pages —
   `modules/arcaea.md`, `modules/sessions.md`, `domains/auth-and-sessions.md`,
   `domains/catalog.md`, `domains/scoring.md`, `domains/potential.md`,
   `domains/score-mapping.md` — still carry none, despite `meta/conventions.md` requiring a
   grade on every wire claim. **Fix**: backfill `grade:` on the foundational wire pages, or
   note explicitly why they're exempt.

6. **Large page** — `domains/chardle.md` is 437 lines, well past the 300-line threshold (the
   2026-07-21 report's largest page was 212 lines, `domains/tournaments.md`, still clean).
   Consider splitting clue-column mechanics, the prototype-comparison table, and the
   mode/pool rules into separate pages or a `flows/` page for the render/scoreboard pipeline.

7. **Large page** — `flows/live-updates.md` is 602 lines, also past 300. It's grown from
   filters + poster + suppression into what reads as three sub-flows in one file. Consider
   splitting the filter/gate logic (already partly covered by
   [[h-live-update-post-filters]]) out of the poster mechanics.

8. **Status-vocabulary drift** — `questions/h-catalog-schema-open-questions.md` uses
   `status: resolved`, and `questions/h-chardle-board-rendering.md` uses `status: partial`.
   Neither value is in `_templates/question.md`'s documented enum
   (`open | answered | blocked | wont-do`); every other answered question in the vault uses
   `answered`. **Fix**: normalize `h-catalog-schema-open-questions.md` to `status: answered`
   for consistency with its 7 siblings. `h-chardle-board-rendering.md`'s `partial` is a
   legitimate state (a temporary answer shipped, the question isn't fully closed) that the
   template's enum doesn't have a slot for — either add `partial` to the template enum, or
   fold it back to `open` and let the body's "Current state" section carry the nuance.

## Suggestions (worth considering)

9. `meta/ingest-queue.md` line 42 mentions `` `domains/Auth & Sessions` `` as a bare
   path-style label (no `[[ ]]`) in a table cell that already carries a real link to
   `[[arcaea-auth-behavior]]` in the same row. Not a broken reference — the row's actual
   link resolves fine — but it's the one genuine unlinked-mention hit found scanning every
   3+-word H1/alias across the vault for bare occurrences outside `[[...]]` spans (checked
   in every content page except `log.md`/`hot.md`/`index.md`/`lint-report*.md`, which are
   bookkeeping/history and quote old link text verbatim by design). Cosmetic; wikify to
   `[[auth-and-sessions|domains/Auth & Sessions]]` or drop the redundant path label since
   the row already links the source page.

## Not run / incomplete (do not treat as clean)

- **Duplicate/overlap and contradiction sweeps** were spot-checked, not run exhaustively.
  This pass **did** close the one item the 2026-07-21 report left open — the friend-slot-cap
  (`max_friend`) numeric-consistency check across the ~12 pages that cite it — and found it
  clean (starts at 10, ladders to a hard max of 25, stated the same way everywhere). A full
  `d-`/`w-`/`h-` cross-slice contradiction sweep beyond the specific pairs already
  cross-linked was not attempted this pass either.
- **Frequently-mentioned-concept scan (missing pages)** was a targeted check against a
  handful of candidate terms (`course mode`, `manual score import`, `Cloudflare`,
  `max_friend`/friend-slot cap) plus the five names `index.md` already declares as intentional
  stubs (`b30`, `Score history backfill`, `h-tournament-scoring-rule-parameter`,
  `h-manual-bot-account-creation`, `h-no-catalog-inferred-ownership` — all five still resolve
  to no file, and their link counts still match what the Known Stubs table claims, so no
  drift there). It was not an exhaustive term-frequency sweep of the whole vault, so treat
  "no new gaps found" as directional, not proof there are none.

## Clean categories (explicit)

- Frontmatter required fields (`type`/`status`/`created`/`updated`/`tags`) — 102/102 content
  pages carry all five, no empty values, no leftover template `#` comments in frontmatter.
- Dead wikilinks — 0 genuine breaks beyond item 1 above; all other `[[...]]`-shaped matches
  in prose are either declared stub targets (`index.md`'s Known Stubs table) or syntax
  examples in `CLAUDE.md`/`hot.md`/`log.md`/`meta/conventions.md`/`meta/lint-report.md`.
- Empty headings — 0. Every heading at every level in every page has real content before
  the next heading at the same or higher level (checked with proper hierarchy boundaries,
  not just "next heading of any level").
- Orphans (0 inbound resolving links) — 0 real orphans; `CLAUDE.md` is the only 0-inbound
  page, expected since it's the layer-3 schema doc. Every `decisions/`, `gotchas/`,
  `questions/` page filename confirmed present in `index.md`.
- Navigational orphans (inbound links only from bookkeeping pages `index.md`/`hot.md`/
  `log.md`/`lint-report.md`, never from a content page) — 7 found, all low-severity and
  arguably expected for their type rather than a defect: `gotchas/d-poll-schedule-absolute-vs-phase.md`,
  `hot.md`, `log.md`, `meta/conventions.md`, `overview.md`,
  `questions/h-r30-queue-view.md`, `sources/handoff-12-recent-b30-config.md`. `hot.md`/
  `log.md`/`conventions.md`/`overview.md` are entry points by design, not content pages
  other pages would cross-reference into. `d-poll-schedule-absolute-vs-phase.md`,
  `h-r30-queue-view.md`, and `handoff-12-recent-b30-config.md` are the three worth a
  second look — genuine content pages with no content-page cross-link yet.
- Unlinked mentions of existing page titles/aliases — clean except the one cosmetic hit in
  suggestion 9 (checked every 3+-word H1/alias across the vault for bare, non-bracketed
  occurrences in other content pages).
- Stale `status: seed` pages (>30 days since `updated:`) — 0, because **no page in this
  vault uses `status: seed` at all**; the status vocabulary in use is
  `active | answered | open | partial | resolved | stub` across 102 pages.
- Index staleness — `index.md`'s Known Stubs table, Questions-open table, and
  Questions-answered table all match the current file/`status:` state exactly; no renamed
  or deleted targets found.
- Friend-slot-cap (`max_friend`) numeric consistency — clean (see "Not run / incomplete").
- Security scan (credentials/keys/sids/emails/passwords) — run this pass, was skipped
  entirely in 2026-07-21. Clean: the one 19-digit-looking hit (`domains/chardle.md:425`) is
  a hardcoded Discord channel ID documented as prototype behavior to not reproduce, not a
  live credential.
- The two 2026-07-21 BLOCKERs and 4 of 6 HIGHs — fixed (see Summary).
