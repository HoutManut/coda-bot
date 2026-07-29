---
type: decision
status: active
date: 2026-07-18
reverses:
created: 2026-07-21
updated: 2026-07-21
tags: [decision, straying, play-scores, retention]
aliases: ["Straying keeps `play_scores`; it is fixed policy, not a keep-or-drop tradeoff"]
---

# Straying keeps `play_scores`; it is fixed policy, not a keep-or-drop tradeoff

## Context

`/unregister` can leave an `ArcaeaAccount` with no remaining `PlayerLink` —
"straying." Something has to happen to its friend slot, its active flag, its
stored credential (if any), and its accumulated `play_scores`. Four separate
resources, four separate questions, easy to answer inconsistently.

## Alternatives

| Option | Why not |
|---|---|
| Delete `play_scores` on stray (mirror the credential deletion) | Friend/free-own tiers have **no score backfill** — a dropped history is irrecoverable. A relink later (same `arc_user_id`) would start from zero for no reason. |
| Cascade-delete `play_scores` on any future `ArcaeaAccount` delete | Silently destroys irreplaceable history as a side effect of an unrelated cleanup; a delete should be a conscious act that deals with scores first. |
| Keep scores only for own-credentialed (tier 2+) accounts | Arbitrary — the friend-tier data is exactly the data with no backfill, so it needs the protection *more*, not less. |

## Decision

`RegistrationService._stray` (fired by `unregister` when a link was the
account's last):

1. Releases the pool slot — `SessionPool.release`: **unfriend by
   `arc_user_id` first, then NULL `bot_account_id`** (order matters, see
   [[db]] and the multipart-style-drift note in `CLAUDE.md`).
2. Sets `ArcaeaAccount.is_active = False`.
3. **Deletes** `PlayerCredential` — the one genuinely private item.
4. **Keeps** the `ArcaeaAccount` row and every `play_scores` row pointing at
   it.

Enforced at the schema level, not just in service code: `play_scores.
arcaea_account_id → arcaea_accounts.id` is `ondelete=RESTRICT`, not
`CASCADE` (see [[db]]). A relink of the same friend code reattaches to the
same `arc_user_id` and the kept history becomes visible again immediately —
no reconstruction step.

## Consequences

- b30 ([[b30]], unbuilt) survives `/unregister` → `/register` for free — no
  special-casing needed in its query, since it just reads whatever
  `play_scores` rows exist for the account.
- A future "delete an account entirely" feature cannot be a plain `DELETE` —
  the `RESTRICT` FK will reject it until the scores are explicitly handled
  (deleted or reassigned). This is the point of the constraint, not an
  oversight to work around.
- Straying is *reversible* for history but *not silent* for the account
  itself — `is_active=False` still needs surfacing somewhere a user can see
  it (registration UX, out of scope for this page).

## Enforced at

`src/coda/players/service.py` (`RegistrationService._stray`),
`src/coda/db/models/play_score.py:84-90` (`ondelete="RESTRICT"`),
`src/coda/db/models/arcaea_account.py:60-67` (`is_active` field + docstring).
