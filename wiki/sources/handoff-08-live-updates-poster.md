---
type: source
status: active
path: 08-live-updates-poster.md
lines: 160
dated: "2026-07-18, revised note 2026-07-21 once handoff 07 landed"
verified: 2026-07-21
supersedes: []
superseded_by: []
created: 2026-07-21
updated: 2026-07-21
tags: [source, handoffs, live-updates, unbuilt]
aliases: ["08 — Live-updates poster"]
---

# 08 — Live-updates poster

## Covers

The design for the posting half of score tracking: new play → linked Discord
users → `resolve_destination` → embed, with same-destination staggering and
`/recent` precedence. **Status: designed, not built.** Its dependency (the
poller, handoff 07) landed 2026-07-21; this doc records what that changes for
the poster (hook point is `poller._store`'s `new_plays`, one key per cycle
not the whole sweep).

## Key claims

- `ScoreStore.ingest` already returns exactly the plays that should be
  posted; `LiveUpdateService.resolve_destination` is already built and
  labelled the poller's entry point. **Verified**: both exist with zero
  callers, per source read of `src/coda/scores/service.py` and
  `src/coda/players/live.py` (read for this ingest, matching the doc's line
  citations).
- Reuse `score_embed` from `src/coda/scores/embed.py` — do not write a second
  score format.
- The filter set (which plays deserve a post) is **explicitly undesigned**;
  only one filter is settled, fed by handoff 09 (b30 delta), and it must
  never leak a hidden player's numeric value even when the flag fires.
- Ordering: stagger same-destination bursts, order by `time_played` not
  ingest order, `/recent` jumps the queue. Whether a trailing live update for
  a play `/recent` just showed should be **suppressed** (vs. merely delayed)
  is explicitly left undecided.
- No double-posting across cycles is a structural guarantee (`ingest` returns
  first-inserts only), not something the poster must implement.

## Contradicts / reversed by

None. This doc is additive on top of the landed poller (07) and does not
reverse any source-doc claim.

## Feeds

`[[Live Updates]]`, `[[h-live-update-post-filters]]`,
`[[h-recent-duplicate-suppression]]`
