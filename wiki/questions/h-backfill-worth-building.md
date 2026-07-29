---
type: question
status: open
blocks: ["[[Score history backfill]]"]
source: 10-score-history-backfill-research.md
created: 2026-07-21
updated: 2026-07-21
tags: [question, backfill, scale, product]
aliases: ["Does the project have enough subscribed (tier-3) users to justify building backfill at all?"]
---

# Does the project have enough subscribed (tier-3) users to justify building backfill at all?

## Why it is open

Backfill only ever benefits players with an active Arcaea Online
subscription — the friend path and free credentialed users are structurally
excluded (tier-3-only endpoints). Combined with the project's hard scale
constraint (fewer than 50 users total, roughly 5 hand-made bot accounts, no
automated signup), the source doc asks directly: *"If the answer is 'one, the
owner', this is a hobby feature and should be prioritised as one."* Nobody
has counted.

## What would answer it

Ask the owner how many currently-registered players (if any beyond the
owner) hold an active Arcaea Online subscription. This is a headcount, not an
engineering task — a five-minute question that determines whether the ~250-
request-per-player backfill design (§ traffic-shape constraints in the
source doc) is worth building at all versus staying research-only
indefinitely.

## Current best guess

Unknown. Given the project's explicit <50-user, mostly-friend-path framing
(`CLAUDE.md` §Arcaea domain / scale constraint), a low count is plausible but
not established.

## Answer

Not yet answered.
