---
type: meta
title: "Index"
status: active
created: 2026-07-21
updated: 2026-09-26
tags: [meta, index]
aliases: ["coda-bot Wiki — Master Catalog"]
---

# coda-bot Wiki — Master Catalog

114 pages. **PTT wire scale changed ×100 → ×1000 by a lowiro maintenance window, and a login-envelope
bug that misread that same outage as a dead credential, both fixed 2026-08-27** — see
[[log|Log]] and [[w-login-403-not-status-gated]]. **Tournaments designed 2026-09-02, in two passes** — the first movement since the 2026-07-21 ingest. Pass 1 (scoring): a round became a chart **set** (casual song mode), ranking locked to raw `score`, hard-gauge deaths locked in as valid, the window rebased to `clamp(2t, 200s, 500s)` (**retired 2026-09-03 for a flat 300 s**), rooms settled as the primitive. Pass 2 (surface): every match lives in a **thread** off a dedicated channel and the DM room is gone (`guild_id NOT NULL`), a quick match **reuses its crew's thread** as their history, the board is a rendered image of **match state** (a pool with pick/ban marks and per-chart winners) — which added a **match** layer between tournament and round, 3 tables to 7 — plus head-to-head pick/ban, filter-generated pools, and a three-tier config model whose binding rule is *anything configurable that changes how you play is printed on the board*. Then the config axis was corrected — not timers but **formats** (single/double elimination, round robin, no-elimination lobby, banning off), with every wait ending early on a `Ready` primitive instead of being tuned, which made the spec big enough to **split into two handoffs**: [[handoff-13-tournaments|13 — quick match]] (the match and below, build first) and [[handoff-14-tournament-formats|14 — tournament formats]]. Two decisions, two handoffs, four claims on [[arcaea-tournament-layer]] reversed. **Built 2026-09-02 and spot-checked 2026-09-03** — the review fixed the sweep (lightbulb cancels a task permanently on its first failure) and gave the option tables one owner, and filed six pages of deferred work, the first of which was **answered and built 2026-09-03** (flat window, the break as a rest, and the beats a round posts): [[h-tournament-window-and-clock]], [[h-tournament-sticky-board]], [[h-tournament-untracked-participants]], [[h-tournament-one-match-per-thread]], [[h-tournament-pool-sizing]], [[h-tournament-spot-check-leftovers]]. **`domains/chardle.md` and `flows/live-updates.md` split into overview + 3
sub-pages each 2026-07-29**, following the 2026-07-29 lint pass's over-300-line findings —
see [[log|Log]]. **`/run` owner terminal designed AND built 2026-07-28** — two decisions, one gotcha, one question (item 1 of which is still open); the trigger was "delete `/config global`", and reading the code found the leak is `/config view` instead. Chardle designed 2026-07-27 from the archived 2024 prototype — one domain page, one planned module, six decisions, one gotcha, two open questions; nothing built. Its edge-case sweep the same day baked four owner manual notes into the pages and left [[h-chardle-build-time-leftovers]] behind. All 16 Layer-1 documents ingested 2026-07-21; `scores/` + its two flows filed 2026-07-22 from shipped code. Dead links closed 2026-07-23 — see [[hot|Hot Cache]] §Lint status. Four surface-feature questions + the t0 manual-tier decision filed 2026-07-23 from conversation. **b30 backend built 2026-07-23** — see [[h-b30-cache-stores-sum]] and [[scores]]; **migrated to the 7.0 best-50 model 2026-08-31** as `scores/potential.py`. Poll-schedule phase-vs-absolute gotcha + rate-limit-shape question filed 2026-07-24 during a docstring cleanup pass.

## Entry points

[[overview|Overview]] · [[hot|Hot Cache]] · [[log|Log]] · [[ingest-queue|Ingest Queue]] · [[conventions|Conventions]]

## Domains — game + wire knowledge

| Page | Covers |
|---|---|
| [[catalog\|Catalog]] | Songs, difficulties, packs, level `×2`/`×2+1`/`-1` encoding, CC `×10`, override resolution, **§Ownership** — the OWNED/UNLOCKED model, what `/me` reports, and why 66 of 67 Beyonds are gated |
| [[scoring\|Scoring]] | Score formula, pure/far/lost, grades, `clear_type`/`modifier`, gauge |
| [[potential\|Potential]] | Play rating + 7.0 clear bonus (`+0.2`, `clear_type` boundary still open), best-50/top-10-doubled PTT `/60`, PTT `×1000`, hidden sentinel. **Ported to code 2026-08-31**. Pre-7.0 b30/r10/recent-30 model archived §Historical |
| [[score-mapping\|Score Mapping]] | Wire `(song_id, difficulty)` → `song_difficulties`, difficulty ints, `byd_2` |
| [[auth-and-sessions\|Auth & Sessions]] | Endpoints, envelopes, `error_code` taxonomy, session lifetime, friend-slot cap |
| [[tournaments\|Tournaments]] | `tournament → match → round`; rounds as chart **set** + window, casual song mode (`class: any`), raw-score ranking, all three state machines, thread-only rooms, head-to-head pick/ban, configuration policy — **match layer BUILT 2026-09-02** ([[tournaments-module]]); the formats layer ([[handoff-14-tournament-formats\|14]]) is not |
| [[chardle\|Chardle]] | Wordle-over-the-catalog minigame — three modes (daily / free play / custom); overview + build notes. Split 2026-07-29 into [[chardle-clue-columns\|Clue Columns]], [[chardle-discord-surface\|Discord Surface]], [[chardle-mechanics\|Mechanics]] |

## Modules — `src/coda/`

[[arcaea]] · [[sessions]] · [[players]] · [[scores]] · [[db]] · [[tournaments-module|tournaments]] · [[ownership-module|ownership]] · [[chardle-module|chardle]] (**planned**)

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
- [[d-r10-impossible-friend-path|r10 cannot be reconstructed on the friend path; b30 can]] — **superseded 2026-08-28**, r10 removed in 7.0; see [[h-7.0-potential-rework]]
- [[d-clear-bonus-impossible-friend-path|The 7.0 clear bonus cannot be reconstructed on the friend path, even approximately; the base formula can]] — filed 2026-08-31, successor to the r10 gotcha above; **enforced in code the same day** (`resolve_clear`, `play_scores.clear_override`), and the owner-facing half (`/potential` review card, `scores/clears.py`) shipped alongside it; see [[h-7.0-potential-rework]] item 4
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
- [[w-login-403-not-status-gated|An origin outage can look exactly like a dead credential on `/auth/login`]]

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
- [[h-manual-score-import-mechanics|Manual score import: single-entry first, same table + flag, feeds b30 same as t0, self-service]] (design only)
- [[h-b30-cache-stores-sum|b30 backend: on-demand compute, no cache; configurable limit; source-agnostic]]
- [[h-absent-declaration-is-unconstrained|An absent ownership declaration means unconstrained, never "owns nothing"]]

**Discord surface**
- [[h-owner-surface-is-run-terminal|Owner-only operations live behind one `/run` terminal, not owner-gated slash options]] (**not built**)
- [[h-config-audience-declared-on-key|A config key declares its own audience; every user-facing picker filters on it]] (**not built**)
- [[h-spoiler-is-a-render-mode|A spoilered version changes how a chart renders and who sees it, never whether it is found]]

**Chardle**
- [[h-chardle-puzzle-rows-not-modes|A Chardle mode is a shape of rows, not a class]] (partly superseded)
- [[h-chardle-boards-are-channel-owned|A Chardle board is owned by where it lives; only dailies are per-user]]
- [[h-chardle-puzzle-number-not-date|Dailies are numbered globally; guild timezone moves only the unlock instant]]
- [[h-chardle-closest-match-always-costs|Ambiguous guesses resolve to the answer if possible, else to the closest match — and always cost an attempt]]
- [[h-chardle-extra-pool-hides-class|The extras pool merges Beyond and Eternal and reveals only "Extra"]]
- [[h-chardle-err-is-an-event|`err` is a dated event: guaranteed April 1, 25% that week, 0.3% otherwise, never a random daily]]
- [[h-chardle-cooldown-and-attribution|Guess cooldown (3s, universal), non-ephemeral chart-name replies, finished-daily sticky refresh]]
- [[h-chardle-play-options-settled|`/chardle play`: hide `side`, weighted random tier, column count only]]

**Tournaments** (design only — nothing built)
- [[h-score-is-the-only-ranking-value|Raw score is the only value that decides a tournament; never play rating]]
- [[h-every-valid-score-counts|Every score inside the window counts; a hard-gauge death is a real score]]
- [[h-first-score-is-the-only-rule|First score counts; `best` mode is retired]]

## Questions — open

| Question | Blocks |
|---|---|
| [[h-world-unlock-corrections\|Which `world_unlock` rows are wrong, and what should they be?]] | **DECIDED 2026-09-03, UNAPPLIED** — 18 rows + one pack rename; blocks declaration sizing and any read of the flag |
| [[h-tournament-clock-skew\|How far does the bot's clock skew from lowiro's?]] | tournaments |
| [[h-tournament-window-and-clock\|How long is a round's window, and what tells a player it opened?]] | **ANSWERED + BUILT 2026-09-03** — flat 300 s window, the break as a rest, and the two beats a round posts |
| [[h-tournament-quit-rerolls-first\|Quitting doesn't submit — so what stops the round from being a reroll budget?]] | **tournaments — an open hole in the shipped default.** A quit submits nothing, so the 300 s window is worth ~3 blind-free rerolls against a board that shows the target; proposes co-submission bands + a roll call |
| [[h-tournament-sticky-board\|Should the match board be sticky?]] | tournaments — `/tournament board`, the orphaned board, the lock; **the old board is now KEPT, not deleted**, and the beats already close its "nothing notifies" motivation |
| [[h-tournament-untracked-participants\|Should score tracking gate a match?]] | tournaments, scores — `_playable`, and whether a live round is a persistence exception |
| [[h-tournament-one-match-per-thread\|What does a thread's match mean when a second one is started in it?]] | tournaments — a live match can be shadowed and stranded |
| [[h-tournament-pool-sizing\|How big should a match's pool be?]] | tournaments — bans-off draws two charts it never plays |
| [[h-tournament-spot-check-leftovers\|What did the handoff 13 spot check leave unfixed?]] | tournaments — the residue; the sweep and the option tables were fixed on the day |
| [[h-7.0-potential-rework\|What changed in Arcaea 7.0's potential/PTT rework?]] | **built 2026-08-31**; only the `clear_type` boundary in `resolve_clear` is still blocked |
| [[h-7.0-clear-bonus-investigation-plan\|7.0 clear-bonus investigation plan]] | [[h-7.0-potential-rework]] item 4; the bonus is ported, so this now blocks only confirming `resolve_clear`'s `TRACK_LOST` boundary |
| [[h-recent-config-ptt-b30-r10\|Should /recent be configurable to show ptt/b30/r10 impact?]] | /recent rating-impact config — **superseded 2026-08-28**, r10 removed, b30 half shipped 2026-08-10 |
| [[h-r30-queue-view\|What does a comprehensive r30 queue view need?]] | /r30 command |
| [[h-course-mode-ptt-detection\|How do we detect a play was made in course mode, so it can be excluded from PTT?]] | best-50 backend correctness, score ingest |
| [[h-real-rate-limit-shape-unknown\|What does a real rate limit or Cloudflare challenge from lowiro actually look like?]] | removing `arcaea/client.py`'s temporary diagnostic-logging block |
| [[h-chardle-board-rendering\|How is a Chardle board rendered?]] | chardle — every other rule is settled |
| [[h-chardle-shared-board-modes\|What should Chardle's daily relocation and public-board modes look like?]] | chardle — only relocation-while-unbeaten is still open; attribution, cooldown and sticky refresh shipped 2026-07-30 |
| [[h-1v1-casual-ranked-structure\|What should the 1v1 casual/ranked match structure look like?]] | 1v1 module — sketch; Elo, matchmaking, HP attrition over the shipped `tournaments/` match; `SCALE_CONSTANT` unset |
| [[h-chardle-build-time-leftovers\|What is still unsettled in Chardle at build time?]] | chardle — sweep policy, `bpm`/`note` thresholds, ephemeral fallback, answer-deletion path (private-thread item answered 2026-07-27) |
| [[h-run-terminal-build-time\|What is still unsettled about `/run` before it is built?]] | `/run`, settings — autocomplete replacement capture, the `set_value` no-coercion bug, first verb set, DM `contexts`, audience for the existing 11 keys |
| [[h-clear-override-review-queue\|What should the clear-override review surface look like?]] | **answered + built 2026-08-31** — `/potential` → *Review N assumed*; kept for the placement/layout/reversibility reasoning |

## Questions — answered

| Question | Answer |
|---|---|
| [[h-backfill-unsubscribed-failure-mode\|What do the score endpoints return with no subscription?]] | `400 {"success":false,"error_code":1401}` on both `score/rating/me` and `score/song/me/all` — verified 2026-07-23 |
| [[h-song-me-all-log-vs-record\|Is `score/song/me/all` a play log or one row per chart?]] | Per-chart record, confirmed by replay — worse attempt left row unchanged except `yearly_play_count` — verified 2026-07-23 |
| [[h-backfill-worth-building\|Are there enough tier-3 users to justify backfill at all?]] | ~4 total (owner+3) — worth it scoped to the cheap `rating/me` path, not the heavy `song/me/all` walk — 2026-07-23 |
| [[h-credentials-changed-server-side\|Can a stored credential go stale server-side?]] | Already resolved 2026-07-18 in `errors.py`/[[w-third-auth-envelope]] — just never cross-linked; handling is correct as shipped |
| [[h-welcome-message-update\|What should the post-registration welcome message say now?]] | Shipped 2026-07-23 in `_send_welcome` — explicit tracking-on/live-updates-off callout, inline enable button when the channel is allowlisted |
| [[h-live-update-post-filters\|What filters decide whether a play is worth posting?]] | Triggers OR-ed (`all`/`pb`/`bX`/`pm`/`fr`/`grade_up`), gates AND-ed (`min_level` + per-channel guild floor); per-user columns on `live_update_prefs`; default `pb`; b30 aggregate never printed. **Built 2026-07-24** in `scores/filters.py` — 2026-07-24 |
| [[h-recent-duplicate-suppression\|Suppress or merely delay a play `/recent` already showed?]] | Suppress. `/recent` *causes* the duplicate by triggering the poll; marker keyed `(destination, play_score_id)`, TTL 15 min. **Built 2026-07-24** in `scores/suppression.py` — 2026-07-24 |
| [[h-ownership-blob-open-before-building\|What must settle before the ownership blob is built?]] | **Its premise was wrong** — `/webapi/user/me` reports ownership exactly for t2/t3, so no blob is needed at song grain. 63 packs (not ~110); 49 one-checkbox packs, 14 needing per-song answers; chart grain; pool filter confirmed wanted. Replaced by the owner's **OWNED / UNLOCKED** split — see [[ownership-worksheet-2026-09-03]] — 2026-09-03 |
| [[h-tournament-attempt-overhead\|How long is song-select → load → results, really?]] | **SUPERSEDED 2026-09-05** — it only sized a `best` window, and `best` is retired ([[h-first-score-is-the-only-rule]]). Overhead is still an unmeasured 20–40 s estimate that nothing reads |
| [[h-manual-score-import\|What does manual score importing need before it can be built?]] | Design settled 2026-07-29 by [[h-manual-score-import-mechanics]]; the `/addscore`-style command is unbuilt |
| [[h-chardle-play-options-rework\|What should `/chardle play`'s option set become?]] | Settled + built 2026-07-30 — [[h-chardle-play-options-settled]] |
| [[h-catalog-schema-open-questions\|What is unresolved in the catalog schema design?]] | 12/14 override fields used (name_jp, remote_download never fire); artist/charter seeded automatically in `seed.py`; search-config still placeholder values, never tuned; `packs.release_date` is manual-only, not derived — 2026-07-23 |

## Sources — archived originals

These pages are what survives of the research/design documents the vault was built
from; the originals are archived outside this repository.

Measurement + owner-answer sessions: [[ownership-worksheet-2026-09-03|ownership worksheet (2026-09-03)]] — the whole catalog diffed against one live `/webapi/user/me`, plus 146 owner answers; supersedes [[handoff-11-ownership-blob|handoff 11]]

Domain + implementation docs: [[arcaea-domain-reference]] · [[arcaea-scoring]] · [[arcaea-potential]] (superseded on formula by [[arcaea-7.0-potential-notes]]) · [[arcaea-score-mapping]] · [[arcaea-auth-behavior]] · [[arcaea-api-layer]] · [[arcaea-api-research-tasks]] · [[arcaea-bot-db-schema]] · [[arcaea-tournament-layer]]

Handoff notes (designed-but-unbuilt work units): [[handoffs-readme]] · [[handoff-06-credentials-changed-server-side|06 — credentials changed server-side]] · [[handoff-08-live-updates-poster|08 — live-updates poster]] · [[handoff-09-b30|09 — b30]] · [[handoff-10-score-history-backfill-research|10 — score-history backfill]] · [[handoff-11-ownership-blob|11 — ownership blob]] (**SUPERSEDED 2026-09-03** by [[ownership-worksheet-2026-09-03]] — its premise that the wire never reports unlocked state is wrong) · [[handoff-12-recent-b30-config|12 — /recent b30 stat config]] · [[handoff-13-tournaments|13 — quick match]] (**BUILT 2026-09-02**, with six deltas — see [[tournaments-module]]; the match and below — schema, surface, board contract, config keys) · [[handoff-14-tournament-formats|14 — tournament formats]] (**unbuilt**; registration, brackets, round robin, lobby, seeding, async scheduling)

`docs/`: [[sources/self-hosting|self-hosting]]

**Not yet ingested**: the 2026-07-19 API-layer findings writeup, since archived out of the repo — see [[ingest-queue|Ingest Queue]].

## Known stubs

Linked from real pages but not written yet. These links are deliberate markers, not breakage —
lint treats a target listed here as intentional.

| Target | Would live in | Linked from |
|---|---|---|
| `Score history backfill` | `flows/` | 4 pages |
| `h-manual-bot-account-creation` | `decisions/` | `sources/self-hosting` ×2 |
| `h-no-catalog-inferred-ownership` | `decisions/` | tournaments ×2, [[h-score-is-the-only-ranking-value]], lint-report |

## Meta

- [[conventions|Conventions]]
- [[lint-report|Lint Report]] — 2026-07-21 health check, plus what was fixed after it
