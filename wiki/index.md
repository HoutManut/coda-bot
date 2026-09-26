---
type: meta
title: "Index"
status: active
created: 2026-07-21
updated: 2026-07-30
tags: [meta, index]
aliases: ["coda-bot Wiki — Master Catalog"]
---

# coda-bot Wiki — Master Catalog

120 pages. **1v1 casual/ranked match structure sketched 2026-07-30** (design
target, not built) — an in-between step before the full tournament module:
Elo keyed on `arcaea_account_id` (named `Elo` not `Rating`, avoiding the
play-rating/PTT name collision), HP-attrition match-end (score-differential
damage, chip damage on exact ties to prevent stalemate) instead of
best-of-N, `Match`/`Game`/`BanPhase` reused from
[[h-tournament-bracket-and-ban-formats]] as a degenerate single-match
bracket, challenge + queue matchmaking with no elo-range gating (population
too small to gate on). See [[h-1v1-casual-ranked-structure]]. Same day, earlier: **Chardle guess cooldown, non-ephemeral chart-name replies, and finished-daily
sticky refresh settled AND built 2026-07-30** — 3s universal cooldown (no `Play` toggle, same
person always exempt), every guess reply drops `ephemeral` and names the chart, a daily
finished elsewhere now folds into a guild's scoreboard on resume — see
[[h-chardle-cooldown-and-attribution]], leaving only the original relocation-while-unbeaten
ask open on [[h-chardle-shared-board-modes]]. Same day, earlier: **`/chardle play` option rework settled AND built** — `side`
hidden not deleted, weighted random-tier resolved once per board (err needs no new
handling, already covered by `roll_err`'s existing ambient/event chance), column
count only (`3`-`8`), `room` moved first — see [[h-chardle-play-options-settled]],
closing [[h-chardle-play-options-rework]]. Same day, earlier: Chardle daily stale-DM resume message
fixed, and four unbuilt shared-board ideas filed (relocation while unbeaten, guesser
avatar attribution, round-robin mode, per-player guess budget) — see
[[h-chardle-shared-board-modes]]. Previously 2026-07-29. **Manual score import mechanics settled 2026-07-29** — single-entry
first (bulk deferred), same `play_scores` table + `source` flag, linked accounts
feed b30 same as t0, self-service `/score add|delete|get` command group, lower-score
overwrite needs command-layer confirmation — see [[h-manual-score-import-mechanics]],
closing [[h-manual-score-import]]. Same session, `/recent` r10 friend-path gap settled:
omitted entirely, no placeholder — see [[h-recent-config-r10-friend-path-omit]].
**`domains/chardle.md` and `flows/live-updates.md` split into overview + 3
sub-pages each 2026-07-29**, following the 2026-07-29 lint pass's over-300-line findings —
see [[log|Log]]. **`/run` owner terminal designed AND built 2026-07-28** — two decisions, one gotcha, one question (item 1 of which is still open); the trigger was "delete `/config global`", and reading the code found the leak is `/config view` instead. Chardle designed 2026-07-27 from the archived Tenniel prototype — one domain page, one planned module, six decisions, one gotcha, two open questions; nothing built. Its edge-case sweep the same day baked four owner manual notes into the pages and left [[h-chardle-build-time-leftovers]] behind. All 16 Layer-1 documents ingested 2026-07-21; `scores/` + its two flows filed 2026-07-22 from shipped code. Dead links closed 2026-07-23 — see [[hot|Hot Cache]] §Lint status. Four surface-feature questions + the t0 manual-tier decision filed 2026-07-23 from conversation. **b30 backend built 2026-07-23** — see [[h-b30-cache-stores-sum]] and [[scores]]. Poll-schedule phase-vs-absolute gotcha + rate-limit-shape question filed 2026-07-24 during a docstring cleanup pass.

## Entry points

[[overview|Overview]] · [[hot|Hot Cache]] · [[log|Log]] · [[ingest-queue|Ingest Queue]] · [[conventions|Conventions]]

## Domains — game + wire knowledge

| Page | Covers |
|---|---|
| [[catalog\|Catalog]] | Songs, difficulties, packs, level `×2`/`×2+1`/`-1` encoding, CC `×10`, override resolution |
| [[ownership\|Ownership]] | Not-owned/owned/unlocked three-state model, `packs`/`singles`/`world_songs` wire lists, `single`/`extend_*` pack exceptions, passive per-chart unlock derivation |
| [[scoring\|Scoring]] | Score formula, pure/far/lost, grades, `clear_type`/`modifier`, gauge |
| [[potential\|Potential]] | Play rating, b30/r10, PTT `×100`, hidden sentinel, recent-30 admission |
| [[score-mapping\|Score Mapping]] | Wire `(song_id, difficulty)` → `song_difficulties`, difficulty ints, `byd_2` |
| [[auth-and-sessions\|Auth & Sessions]] | Endpoints, envelopes, `error_code` taxonomy, session lifetime, friend-slot cap |
| [[tournaments\|Tournaments]] | Rounds, windows, validity, state machine, tiers — **not built** |
| [[chardle\|Chardle]] | Wordle-over-the-catalog minigame — three modes (daily / free play / custom); overview + build notes. Split 2026-07-29 into [[chardle-clue-columns\|Clue Columns]], [[chardle-discord-surface\|Discord Surface]], [[chardle-mechanics\|Mechanics]] |

## Modules — `src/coda/`

[[arcaea]] · [[sessions]] · [[players]] · [[scores]] · [[db]] · [[chardle-module|chardle]] (**planned**)

Not yet written: `catalog`, `settings`, `extensions`, `admin`, `approvals`, `utils`, `logging`.

## Flows

[[registration|Registration]] (both paths) · [[session-lease|Session Lease]] · [[score-poll-loop|Score Poll Loop]] (both read paths) · [[chart-resolution|Chart Resolution]] · [[live-updates|Live Updates (poster)]] (split 2026-07-29 into [[live-updates-filters|Filters]], [[live-updates-poster|Poster]], [[live-updates-suppression|Suppression]])

## Gotchas — silent-regression traps

**Domain / decoding**
- [[d-level-cc-sentinel-values|Level/CC sentinels: `0` = TBA, `-1` = err-only `?`]]
- [[d-ptt-hidden-sentinel|PTT `-1` means HIDDEN — and it is a different field from chart CC]]
- [[d-score-zero-is-real|`score: 0` is a real score, not missing data]]
- [[d-unknown-cc-no-play-rating|Unknown CC yields NO play rating — never substitute 0]]
- [[d-hard-gauge-early-submit|Hard-gauge loss submits early; the r10 exclusion needs BOTH fields]]
- [[d-r10-impossible-friend-path|r10 cannot be reconstructed on the friend path; b30 can]]
- [[d-byd2-game-song-id-resolution|`byd_2` needs `game_song_id`, and the step order matters]]

**Catalog / seeding**
- [[d-reseed-duplicates-renamed-entities|Re-running the seed after admin renames/merges duplicates artists and charters]]

**Scheduling**
- [[d-poll-schedule-absolute-vs-phase|`PollSchedule._spread` must compare neighbours by phase, not absolute due time]]

**Chardle**
- [[d-chardle-dead-clue-columns|A clue column can carry zero information — narrow pools kill `level`, `pack`/`version` duplicate each other]]

**Discord surface**
- [[d-autocomplete-is-a-hint|Autocomplete is a hint, not a constraint — and a chosen row replaces the whole option value]]

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
- [[h-t0-manual-tier-b30|t0: no account link, manual-only score entry, b30 computed from it]]
- [[h-b30-cache-stores-sum|b30 backend: on-demand compute, no cache; configurable limit; source-agnostic]]
- [[h-manual-score-import-mechanics|Manual score import: single-entry first, same table + flag, feeds b30 same as t0, self-service `/score` group]] (**not built**)

**Discord surface**
- [[h-owner-surface-is-run-terminal|Owner-only operations live behind one `/run` terminal, not owner-gated slash options]] (**not built**)
- [[h-config-audience-declared-on-key|A config key declares its own audience; every user-facing picker filters on it]] (**not built**)
- [[h-recent-config-r10-friend-path-omit|`/recent` rating-impact config: friend-path scores omit r10 entirely, no placeholder]] (**not built**)

**Chardle**
- [[h-chardle-puzzle-rows-not-modes|A Chardle mode is a shape of rows, not a class]] (partly superseded)
- [[h-chardle-boards-are-channel-owned|A Chardle board is owned by where it lives; only dailies are per-user]]
- [[h-chardle-puzzle-number-not-date|Dailies are numbered globally; guild timezone moves only the unlock instant]]
- [[h-chardle-closest-match-always-costs|Ambiguous guesses resolve to the answer if possible, else to the closest match — and always cost an attempt]]
- [[h-chardle-extra-pool-hides-class|The extras pool merges Beyond and Eternal and reveals only "Extra"]]
- [[h-chardle-err-is-an-event|`err` is a dated event: guaranteed April 1, 25% that week, 0.3% otherwise, never a random daily]]
- [[h-chardle-play-options-settled|`/chardle play`: `side` hidden not deleted, weighted random-tier frozen per board, column count only, `room` first]] (**built**)
- [[h-chardle-cooldown-and-attribution|Guess cooldown (3s, universal, no toggle), non-ephemeral chart-name replies, sticky refresh on finished-daily resume]] (**built**)

## Questions — open

| Question | Blocks |
|---|---|
| [[h-ownership-blob-open-before-building\|What must settle before the ownership blob is built?]] | ownership blob, chart-unlock display |
| [[h-tournament-attempt-overhead\|How long is song-select → load → results, really?]] | tournaments |
| [[h-tournament-clock-skew\|How far does the bot's clock skew from lowiro's?]] | tournaments |
| [[h-recent-config-ptt-b30-r10\|Should /recent be configurable to show ptt/b30/r10 impact?]] | /recent rating-impact config (r10 friend-path degradation now settled — see [[h-recent-config-r10-friend-path-omit]]) |
| [[h-r30-queue-view\|What does a comprehensive r30 queue view need?]] | /r30 command |
| [[h-course-mode-ptt-detection\|How do we detect a play was made in course mode, so it can be excluded from PTT?]] | b30/r10 backend correctness, score ingest |
| [[h-real-rate-limit-shape-unknown\|What does a real rate limit or Cloudflare challenge from lowiro actually look like?]] | removing `arcaea/client.py`'s temporary diagnostic-logging block |
| [[h-chardle-board-rendering\|How is a Chardle board rendered?]] | chardle — every other rule is settled |
| [[h-chardle-build-time-leftovers\|What is still unsettled in Chardle at build time?]] | chardle — sweep policy, `bpm`/`note` thresholds, ephemeral fallback, answer-deletion path (private-thread item answered 2026-07-27) |
| [[h-run-terminal-build-time\|What is still unsettled about `/run` before it is built?]] | `/run`, settings — autocomplete replacement capture, the `set_value` no-coercion bug, first verb set, DM `contexts`, audience for the existing 11 keys |
| [[h-world-songs-id-mapping\|How do `world_songs` ids on `/user/me` map to `song_id`?]] | ownership World Mode resolution |
| [[h-passive-unlock-model-unsettled\|Is score-row-as-evidence the complete chart-unlock model, or does it need an explicit unlock table too?]] | tournaments, ownership chart-unlock tracking |
| [[h-chardle-shared-board-modes\|What should Chardle's daily relocation and public-board modes look like?]] | chardle — only player-initiated relocation while unbeaten still open; attribution, guess cooldown, and finished-daily sticky refresh built 2026-07-30, see [[h-chardle-cooldown-and-attribution]] |
| [[h-tournament-bracket-and-ban-formats\|What should bracket + chart-ban tournament formats look like?]] | tournament module build — leaderboard/FFA shape already designed, bracket + bans are net-new |
| [[h-1v1-casual-ranked-structure\|What should the 1v1 casual/ranked match structure look like?]] | 1v1 module build — planned before the full tournament module; Elo, matchmaking, HP-attrition match-end, `SCALE_CONSTANT` still needs empirical tuning |

## Questions — answered

| Question | Answer |
|---|---|
| [[h-backfill-unsubscribed-failure-mode\|What do the score endpoints return with no subscription?]] | `400 {"success":false,"error_code":1401}` on both `score/rating/me` and `score/song/me/all` — verified 2026-07-23 |
| [[h-song-me-all-log-vs-record\|Is `score/song/me/all` a play log or one row per chart?]] | Per-chart record, confirmed by replay — worse attempt left row unchanged except `yearly_play_count` — verified 2026-07-23 |
| [[h-backfill-worth-building\|Are there enough tier-3 users to justify backfill at all?]] | ~4 total (owner+3) — worth it scoped to the cheap `rating/me` path, not the heavy `song/me/all` walk — 2026-07-23 |
| [[h-credentials-changed-server-side\|Can a stored credential go stale server-side?]] | Already resolved 2026-07-18 in `errors.py`/[[w-third-auth-envelope]] — just never cross-linked; handling is correct as shipped |
| [[h-welcome-message-update\|What should the post-registration welcome message say now?]] | Shipped 2026-07-23 in `_send_welcome` — explicit tracking-on/live-updates-off callout, inline enable button when the channel is allowlisted |
| [[h-live-update-post-filters\|What filters decide whether a play is worth posting?]] | Triggers OR-ed (`all`/`pb`/`bX`/`pm`/`fr`/`grade_up`), gates AND-ed (`min_level` + per-channel guild floor); per-user columns on `live_update_prefs`; default `pb`; b30 aggregate never printed. **Built 2026-07-24** in `scores/filters.py` — 2026-07-24 |
| [[h-chardle-play-options-rework\|What should /chardle play's option set become?]] | Settled and built same day by [[h-chardle-play-options-settled]]: `side` hidden not deleted, weighted random-tier frozen once per board, column count only (`3`-`8`), `room` moved first — 2026-07-30 |
| [[h-recent-duplicate-suppression\|Suppress or merely delay a play `/recent` already showed?]] | Suppress. `/recent` *causes* the duplicate by triggering the poll; marker keyed `(destination, play_score_id)`, TTL 15 min. **Built 2026-07-24** in `scores/suppression.py` — 2026-07-24 |
| [[h-catalog-schema-open-questions\|What is unresolved in the catalog schema design?]] | 12/14 override fields used (name_jp, remote_download never fire); artist/charter seeded automatically in `seed.py`; search-config still placeholder values, never tuned; `packs.release_date` is manual-only, not derived — 2026-07-23 |
| [[h-manual-score-import\|What does manual score importing need before it can be built?]] | Settled by [[h-manual-score-import-mechanics]]: single-entry first, same table + flag, linked accounts feed b30 like t0, self-service `/score add\|delete\|get` group — 2026-07-29 |

## Sources — archived originals

These pages are what survives of the research/design documents the vault was built
from; the originals are archived outside this repository.

Domain + implementation docs: [[arcaea-domain-reference]] · [[arcaea-scoring]] · [[arcaea-potential]] · [[arcaea-score-mapping]] · [[arcaea-auth-behavior]] · [[arcaea-api-layer]] · [[arcaea-api-research-tasks]] · [[arcaea-bot-db-schema]] · [[arcaea-tournament-layer]]

Handoff notes (designed-but-unbuilt work units): [[handoffs-readme]] · [[handoff-06-credentials-changed-server-side|06 — credentials changed server-side]] · [[handoff-08-live-updates-poster|08 — live-updates poster]] · [[handoff-09-b30|09 — b30]] · [[handoff-10-score-history-backfill-research|10 — score-history backfill]] · [[handoff-11-ownership-blob|11 — ownership blob]] · [[handoff-12-recent-b30-config|12 — /recent b30 stat config]]

`docs/`: [[self-hosting]]

**Not yet ingested**: the 2026-07-19 API-layer findings writeup, since archived out of the repo — see [[ingest-queue|Ingest Queue]].

## Known stubs

Linked from real pages but not written yet. These links are deliberate markers, not breakage —
lint treats a target listed here as intentional.

| Target | Would live in | Linked from |
|---|---|---|
| `b30` | `flows/` or `domains/` | 5 pages |
| `Score history backfill` | `flows/` | 4 pages |
| `h-tournament-scoring-rule-parameter` | `decisions/` | tournaments ×3 |
| `h-manual-bot-account-creation` | `decisions/` | `sources/self-hosting` ×2 |
| `h-no-catalog-inferred-ownership` | `decisions/` | `sources/arcaea-tournament-layer` |

## Meta

- [[conventions|Conventions]]
- [[lint-report|Lint Report]] — 2026-07-21 health check, plus what was fixed after it
