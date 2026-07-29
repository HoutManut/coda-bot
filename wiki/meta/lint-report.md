---
type: meta
title: "Lint Report"
status: active
created: 2026-07-21
updated: 2026-07-21
tags: [meta, lint]
aliases: ["Lint Report — 2026-07-21"]
---
# Lint Report — 2026-07-21

> [!done] Remediation applied 2026-07-21, after this report was written
> - **BLOCKER 1 fixed** — `questions/h-credentials-changed-server-side.md` no longer claims
>   "no notification path exists". Verified against `src/coda/players/notify.py:40` and
>   `session.py:87`: the one-shot owner DM ships. The question was narrowed to what is
>   actually open — whether the terminal `is_valid = False` policy suits a *changed* (vs dead)
>   credential.
> - **BLOCKER 2 fixed** — `modules/db.md` `path:` set to `src/coda/db/`.
> - **Template contamination fixed** — 6 files, not 3 (`flows/live-updates`, `modules/db` ×2,
>   `sources/arcaea-bot-db-schema`, `sources/handoff-06`, `-10`, `-11`).
> - **Dead links: 61 → 19.** Root cause was link style, not typos: pages linked by H1 while
>   Obsidian resolves by filename. Fixed by adding `aliases:` to 60 pages, rewriting `index.md`
>   to `[[filename|Label]]` form, escaping `\|` inside table cells, and dropping path-style
>   targets (`[[flows/Session Lease]]` → `[[Session Lease]]`). Links containing `/` were the
>   silent case — Obsidian parses them as paths.
> - **Orphan fixed** — `domains/auth-and-sessions.md` now resolves (`Auth & Sessions` alias).
> - **Security scan** (item 9, unrun here) completed separately: **clean**. No emails, keys,
>   sids, or passwords. All 9-digit hits are placeholders in the friend-code examples.
> - **Still open: 19 links to 7 targets**, all genuine unwritten pages, now declared in
>   [[index#Known stubs]] so they read as intentional.

Pages scanned: 73 markdown files under `wiki/` (excludes `_templates/`), of which 72 are
schema-bearing wiki pages and 1 (`CLAUDE.md`) is the layer-3 schema doc itself (no frontmatter
expected, excluded from page-level checks). Resolution rule applied throughout: a `[[Target]]`
resolves if `Target` matches a page's filename (basename, no `.md`) **or** its H1 **or** its
frontmatter `title:` field — checked case-insensitively, with and without a leading path
segment (e.g. `modules/arcaea` also checked as `arcaea`).

## Category totals

| # | Category | Sweep status | Result |
|---|---|---|---|
| 1 | Dead wikilinks | **Full** | 41 dead-looking occurrences → 9 intentional stubs (clean), 30 genuinely broken, 2 non-issues (template prose examples) |
| 2 | Template contamination | **Full** | 3 lines |
| 3 | Frontmatter required fields (type/status/created/updated/tags) | **Full** | 0 gaps — clean |
| 3b | Wire-page `verified:`/`grade:` | **Full** | 4 wire pages missing `verified:`; 0/24 wire-relevant pages carry `grade:` (systemic — see MEDIUM) |
| 4 | Orphans (0 inbound links) | **Full** | 2 found — 1 non-issue (`CLAUDE.md`), 1 real (`domains/auth-and-sessions.md`) |
| 5 | Gotcha template compliance ("The wrong fix") | **Full** | 0 violations — clean, all 13 gotcha pages comply |
| 6 | Duplicate/overlapping pages | **Partial sweep — not exhaustive.** Checked the 3 named candidate pairs (all clean/linked) plus opportunistic finds below. Stopped mid-check on friend-slot-cap (`max_friend`) numeric consistency across ~12 pages before completion. |
| 7 | Contradictions | **Partial sweep — not exhaustive.** 1 confirmed contradiction found; general d-/w-/h- cross-slice sweep not completed. |
| 8 | Precedence violations (stale CC-precision hedge) | **Full** | 0 violations — clean, reversal already correctly stated everywhere it's referenced |
| 9 | Security scan (credentials/keys/sids/emails/friend codes) | **Not started** — stopped before beginning this check per coordinator instruction |
| — | Large pages (>300 lines) | **Full** | 0 — clean, largest is `domains/tournaments.md` at 212 lines |

---

## BLOCKER

1. `questions/h-credentials-changed-server-side.md:34-35` — Claims *"no notification path
   exists today for this specific case"* — but `flows/session-lease.md:50` documents a shipped
   DM path (*"own-path also DMs the owner once (`players/notify.py`)"*), and
   `modules/players.md:34` corroborates it (*"`.handle_invalid(account)` — DM on terminal
   403"*). The question also asks *"whether existing handling is even wrong"* as fully open,
   when session-lease already documents the terminal `mark_dead`/`is_valid=False` behavior in
   detail. **Fix**: update the question to reflect what's now documented (mark answered or
   narrow to the genuinely-unresolved sub-question), and cross-link it to
   `[[Session Lease]]`/`[[players]]`.

2. `modules/db.md:4` — `path:` (a required field per the module template) is **empty**; only
   the template's placeholder comment (`# src/coda/db/`) remains, so the module page has no
   actual `path:` value despite looking filled-in at a glance. **Fix**: set `path: src/coda/db/`.

---

## HIGH

3. `domains/auth-and-sessions.md` is a real orphan (0 resolving inbound links) despite being
   referenced by name 3 times, because every reference uses the short title `Auth & Sessions`
   while the page's actual H1 is `Auth & Sessions (lowiro wire)`:
   `index.md:26`, `sources/arcaea-api-research-tasks.md:48`, `sources/arcaea-auth-behavior.md:97`.
   **Fix**: either retitle the H1 to drop the suffix, or fix all 3 links to
   `[[Auth & Sessions (lowiro wire)]]`.

4. `[[Live Updates]]` is broken in 6 places even though the target page exists
   (`flows/live-updates.md`, H1 `Live Updates (poster)`): `sources/handoff-08-live-updates-poster.md:53`,
   `sources/handoff-09-b30.md:68`, `sources/handoffs-readme.md:55`, `sources/handoffs-readme.md:68`,
   `modules/db.md:163`, `questions/h-live-update-post-filters.md:4`. **Fix**: relink all 6 to
   `[[Live Updates (poster)]]` or drop the H1 suffix.

5. `flows/live-updates.md:3` — `status: planned        # active | partial | planned` — raw
   template comment left in frontmatter. **Fix**: delete the trailing comment.

6. `modules/db.md:3` — `status: active        # active | partial | planned | deprecated` — raw
   template comment left in frontmatter. **Fix**: delete the trailing comment.

7. `index.md:97` — 4 links use a `.md`-suffixed target that doesn't match the target page's
   real H1: `[[arcaea-domain-reference.md]]`, `[[arcaea-scoring.md]]`, `[[arcaea-potential.md]]`,
   `[[arcaea-score-mapping.md]]` (targets are `sources/arcaea-domain-reference.md` H1 `Arcaea —
   Game Domain Reference`, etc.). Root cause: 3 sibling source pages
   (`arcaea-api-layer.md`, `arcaea-api-research-tasks.md`, `arcaea-auth-behavior.md`) kept their
   literal filename as H1 (e.g. `# arcaea-auth-behavior.md`), which is what these links were
   modeled on, but the other 4 source pages used descriptive H1s instead. **Fix**: pick one
   convention for `sources/` H1s and apply it everywhere; until then, fix these 4 links to the
   real titles.

8. 6 "nickname" links point at existing pages under a name that matches neither filename nor
   H1:
   - `overview.md:44` `[[Decision — arcaea never imports db]]` → real title
     ``[[`src/coda/arcaea/` never imports `coda.db`]]`` (`decisions/w-arcaea-never-imports-db.md`)
   - `domains/auth-and-sessions.md:99` `[[Decision: Coherent Per-Account Browser Identity]]` →
     real title `[[One fixed, internally-consistent Chrome identity per account — not
     per-request rotation]]` (`decisions/w-coherent-browser-identity.md`)
   - `domains/tournaments.md:191` `[[game_song_id drift]]` → likely
     `gotchas/d-byd2-game-song-id-resolution.md` (real title ``[[`byd_2` needs `game_song_id`
     and step order...]]``) — confirm intent before relinking
   - `sources/arcaea-auth-behavior.md:39` and `:68` `[[arcaea (module)]]` → `[[arcaea]]`
     (`modules/arcaea.md`)
   - `sources/arcaea-auth-behavior.md:60` `[[sessions (module)]]` → `[[sessions]]`
     (`modules/sessions.md`)
   **Fix**: relink each to the real filename or H1.

9. `modules/arcaea.md` — the core wire-client module page — has `verified:` and `grade:` both
   empty despite `tags: [module, arcaea, wire]`. **Fix**: add a `verified:` date (and note the
   template gap in finding MEDIUM-16 that means there's nowhere to put `grade:` yet).

10. `domains/score-mapping.md` — `tags` include `wire`, `verified:` is empty. **Fix**: add a
    `verified:` date or drop the `wire` tag if this page makes no live-checked claim.

---

## MEDIUM

11. 11 dead-link occurrences point at concepts with **no page at all** (true gaps, not
    misnamed links, and not in `index.md`'s/`hot.md`'s named-stub list):
    - `[[b30]]` × 5 — `decisions/h-straying-preserves-history.md:49`, `flows/live-updates.md:68`,
      `flows/live-updates.md:113`, `questions/h-live-update-post-filters.md:25`, `modules/db.md:164`
    - `[[Score history backfill]]` × 4 — `modules/db.md:124`,
      `questions/h-backfill-unsubscribed-failure-mode.md:4`, `questions/h-backfill-worth-building.md:4`,
      `modules/db.md:164`
    - `[[Level Encoding]]` / `[[Rating Encoding]]` × 2 — `modules/db.md:89`, explicitly
      annotated by its own author as *"domain pages, Tier 1 — not authored by this ingest"*
    **Fix**: either author these pages, or add them to `index.md`'s/`hot.md`'s
    known-unwritten list so future lint runs treat them as intentional stubs instead of breakage.

12. `gotchas/w-release-order.md` has **zero** outbound wikilinks despite describing
    `pool.py::_capacity`/`SessionPool.release` mechanics that overlap
    `decisions/w-sid-confined-to-sessions.md` (which also discusses `pool.py`) and
    `modules/sessions.md`. Not confirmed as duplicated content, just unlinked — flagged from
    category 6's partial sweep. **Fix**: check for overlap and cross-link, or confirm it's
    sufficiently distinct and note why.

13. `gotchas/w-third-auth-envelope.md` and `questions/h-credentials-changed-server-side.md`
    cover adjacent ground (session/credential staleness) with **zero** cross-links between them,
    on top of the BLOCKER-1 contradiction. **Fix**: link them regardless of how the
    contradiction is resolved.

14. Systemic: **0 of 24** `domains/`/`modules/`/`flows/`/`gotchas/` pages carry a `grade:`
    field, even the 8 that do have `verified:` dates and clearly derive claims from
    [[arcaea-auth-behavior]] (which grades every claim per `meta/conventions.md`'s
    own rule). Root cause is partly structural: `_templates/module.md` and `_templates/flow.md`
    have no `verified:`/`grade:` placeholder at all (unlike `_templates/domain.md` and
    `_templates/gotcha.md`, which have `verified:` but still no `grade:`). **Fix**: add
    `verified:`/`grade:` slots to all four templates, then backfill.

15. Wire-touching pages missing `verified:` entirely (beyond the two in HIGH):
    `modules/sessions.md`, `flows/registration.md`, `flows/session-lease.md`,
    `gotchas/d-byd2-game-song-id-resolution.md` — all four make claims about live wire/session
    behavior with no dated check. **Fix**: add `verified:` dates.

16. `sources/handoff-10-score-history-backfill-research.md:3`,
    `sources/handoff-06-credentials-changed-server-side.md:3`,
    `sources/handoff-11-ownership-blob.md:3`, `sources/arcaea-bot-db-schema.md:3` — carry
    inline `#` comments after `status: active` that are custom annotations, not verbatim
    template text (e.g. `# research task, not a design`). Not counted as contamination, but
    flagged because they use the same "value + trailing comment" shape as the real
    contamination cases above — worth a second look to confirm none were meant to be a
    different `status:` value.

---

## LOW

17. `CLAUDE.md:40` `[[Page Name]]` and `meta/conventions.md:57` `[[Page]]` — not real dead
    links; both are prose examples illustrating wikilink syntax. No action needed.

18. `CLAUDE.md` shows as a 0-inbound-link "orphan" — expected and correct, it's the layer-3
    schema doc, not a content page that other pages would link to. No action needed.

19. 9 dead-link occurrences confirmed as the **intentional stubs** named in the task brief —
    clean, no action needed: `[[Score Poll Loop]]` ×2 (`domains/tournaments.md:34,210`),
    `[[h-tournament-scoring-rule-parameter]]` ×3 (`domains/tournaments.md:98`,
    `sources/arcaea-tournament-layer.md:40,57`), `[[h-manual-bot-account-creation]]` ×2
    (`sources/self-hosting.md:42,58`), `[[h-b30-cache-stores-sum]]` ×1
    (`sources/handoff-09-b30.md:68`), `[[h-no-catalog-inferred-ownership]]` ×1
    (`sources/arcaea-tournament-layer.md:58`).

---

## Clean categories (explicit)

- **Frontmatter required fields** — every one of the 72 content pages has `type`, `status`,
  `created`, `updated`, `tags`.
- **Gotcha "wrong fix" compliance** — all 13 `gotchas/` pages have a real, substantive section.
- **Precedence violation (CC-precision hedge)** — the reversal from
  `handoffs/09-b30.md` §3 is already correctly stated in `sources/arcaea-potential.md:53-56`,
  `domains/potential.md:116-119`, and `domains/catalog.md:85-90`; no page repeats the stale hedge.
- **Large pages** — none exceed 300 lines (max 212, `domains/tournaments.md`).
- **3 named duplicate/overlap candidates from the task brief** — all three are correctly
  cross-linked, not unlinked duplication: straying vs. RESTRICT-not-CASCADE
  (`decisions/h-straying-preserves-history.md` ↔ `modules/db.md`), multipart decision vs.
  formdata-504 gotcha (`decisions/w-hand-built-multipart.md` ↔ `gotchas/w-formdata-504.md`),
  friend-code validation decision vs. friend-code-strip gotcha
  (`decisions/w-local-friend-code-validation.md` ↔ `gotchas/w-friend-code-strip.md`).

## Not run / incomplete (do not treat as clean)

- **Security scan** (item 9) — not started.
- **Category 6 (duplicates)** — partial; the friend-slot-cap (`max_friend`) numeric-consistency
  check across ~12 pages was in progress and not completed.
- **Category 7 (contradictions)** — partial; only the credentials/notification contradiction
  above was confirmed before stopping. No full d-/w-/h- cross-slice sweep was completed.
