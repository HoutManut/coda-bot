---
type: source
status: active
path: README.md
lines: 51
dated: "2026-07-21 (last updated with the b30 entry)"
verified: 2026-07-21
supersedes: ["arcaea-api-layer.md (bot-code refusal design, account-switching model) — historical target; already reconciled in the live doc, see below"]
superseded_by: []
created: 2026-07-21
updated: 2026-09-02
tags: [source, handoffs, meta]
aliases: ["Handoffs — README"]
---

# Handoffs — README

## Covers

The index of the handoff notes: designed-but-unbuilt work units, each
self-contained and **deleted once landed** (unlike the other source docs, which are
permanent domain references). Authoritative on landed/unbuilt status as of
2026-07-21: `/register` overhaul (01–05, all landed, deleted), score tracking
(07 landed and deleted, 08 unbuilt), b30 (09 unbuilt, 10 research-only), and
two unresearched notes (06, 11).

## Key claims

- **The bot-code not-found oracle is retired and the alt model is dropped**
  (handoff 05, landed 2026-07-18). This doc is explicitly authoritative over
  older docs on this point per the vault's precedence rule.
  **Verified reconciled**: [[arcaea-api-layer]] (lines ~261–271,
  read for this ingest) already states the retirement in its own live text —
  *"the retired fake not-found + mimicked latency... That was dropped on
  purpose (handoff 05)... `mimic_not_found_latency` was deleted; don't
  reintroduce a fake-404 from a stale copy of this doc."* **No active
  contradiction exists today** — the reversal already landed in the target
  doc. The `supersedes` field above records the *direction*, per the vault
  rule ("a doc contradicting a handoff is stale, not authoritative"), for
  whoever next edits `arcaea-api-layer.md` from an older working copy.
- **Account switching was reversed**: the original handoff-03 design was
  "newest wins" (a later registration silently supersedes an earlier link);
  what landed is **no switching** — `AlreadyLinkedElsewhere` refused before
  any friend slot is consumed, `/unregister` then a fresh `/register` is the
  only path. This original "newest wins" design lived only in the now-deleted
  handoff 03, never in a source doc, so there is no external doc left
  to mark stale on this specific point — it is recorded here and in
  `src/coda/players/service.py` (`_link`, `_stray`) as the shipped behavior.
  See [[h-one-account-per-user]].
- Score tracking (handoff 07) landed 2026-07-21: both read paths poll in one
  jittered cycle, keyed `("bot", id)` / `("own", id)`; `PollCoordinator` gates
  on-demand refreshes; reconcile runs as a loop + `/reconcile`; `/recent` is
  the first refresh caller. Durable design now lives in
  [[arcaea-api-layer]] §7–§8 (Tier 2, not this ingest).
- Handoff 08 (live-updates poster) is the **only remaining unbuilt piece** of
  score tracking, depending on landed 07. See [[live-updates|Live Updates]].
- b30 (09) depends on nothing unbuilt; 10 (backfill research) is an
  independent input upgrade, not a blocker for 09.

## Later additions (not in the 2026-07-21 ingest)

The status summary above is frozen at 2026-07-21. Handoffs added since:

| # | Covers | Status |
|---|---|---|
| 12 | `/recent` b30 stat config | landed |
| 13 | **Quick match** — the tournament module's match layer and everything under it: rounds, windows, validity, ranking, pool, pick/ban, threads, the match board, configuration | unbuilt |
| 14 | **Tournament formats** — registration, single/double elimination, round robin, no-elimination lobby, seeding, async scheduling, no-shows, the bracket board | unbuilt |

**13 and 14 are one spec split at the match**, which is the invariant unit —
every format decomposes into matches, so nothing in 14 changes anything in 13.
**Build 13 first**: a quick match exercises every table, query and surface 14
relies on. See [[tournaments|Tournaments]] for the policy layer over both.

## Contradicts / reversed by

None currently active — see the reconciled bot-code point above. The
"newest wins → no switching" reversal has no surviving external doc to mark
stale (the original design was never written to a source doc).

## Feeds

[[db]] (player_links unique-discord-id constraint),
[[h-one-account-per-user]], [[live-updates|Live Updates]], [[tournaments|Tournaments]]
(indirectly, via the landed score-tracking foundation it describes) ·
[[handoff-13-tournaments|13 — quick match]] · [[handoff-14-tournament-formats|14 — tournament formats]]
