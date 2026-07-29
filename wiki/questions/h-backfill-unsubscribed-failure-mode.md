---
type: question
status: open
blocks: ["[[Score history backfill]]"]
source: 10-score-history-backfill-research.md
created: 2026-07-21
updated: 2026-07-21
tags: [question, backfill, tier-3, wire, unresearched]
aliases: ["What does `score/rating/me` or `score/song/me/all` return for an account with no Arcaea Online subscription?"]
---

# What does `score/rating/me` or `score/song/me/all` return for an account with no Arcaea Online subscription?

## Why it is open

Both candidate backfill endpoints are tier-3-only (subscription required).
The failure mode for calling them from a tier-1 or tier-2 (unsubscribed)
account is **untested** — likely a 403, possibly a `success: false` envelope
carrying an `error_code`, per [[arcaea-auth-behavior]] §7.5 (Tier 2,
not re-verified in this ingest). The source doc names this explicitly as
*"the only thing gating a correct fallback path"* for backfill — without it,
there is no way to distinguish "not subscribed, fall back gracefully" from
"a real error, surface it."

## What would answer it

Call the route on a throwaway (non-subscribed) account and capture the exact
response. Until then, gate eligibility on `arcaea_online_expire_ts` from
`GET /webapi/user/me` (`0` = no subscription) rather than inferring failure
from a sibling route's error shape — the source doc is explicit that gating
is per-route, not per-prefix, so a captured response from one candidate
endpoint cannot be assumed to apply to the other.

## Current best guess

Likely a 403, by analogy with other tier-gated endpoints elsewhere in the
API — **explicitly an unverified guess**, not a claim.

## Answer

Not yet answered.
