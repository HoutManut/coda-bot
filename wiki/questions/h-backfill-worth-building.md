---
type: question
status: answered
blocks: ["[[Score history backfill]]"]
source: 10-score-history-backfill-research.md
created: 2026-07-21
updated: 2026-07-23
verified: 2026-07-23
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

**Owner-stated, 2026-07-23**: ~3 subscribed players beyond the owner — roughly 4 tier-3
users total out of the <50-user scale ceiling. Not "one, the owner", but still small.

That headcount alone doesn't settle it, though — this question was framed against the
source doc's ~250-request-per-player design (walking `score/song/me/all`), and that's
no longer the only option. [[handoff-10-score-history-backfill-research]] now has a
wire-verified cheaper path: `GET /webapi/score/rating/me` returns server-precomputed
b30+r10 in **one request**. Against a 1-request-per-player cost, a headcount of 4 easily
clears the bar — the original "hobby feature, deprioritize" framing was calibrated for
the heavy design, not the cheap one.

**Verdict: worth building, scoped to the `rating/me` path.** A one-shot backfill (run
once per newly-subscribed player at registration or on-demand, not a recurring job) is
low-risk, low-cost even at this scale. The heavier `song/me/all` walk (full log/note
detail, CC-re-evaluation survival) stays research-only/deferred — its extra cost isn't
justified by 4 users when `rating/me` already covers the b30 seeding use case.
