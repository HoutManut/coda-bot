---
type: decision
status: active
date: 2026-07-18
reverses:
created: 2026-07-21
updated: 2026-07-21
tags: [decision, registration, tiers, player-links]
aliases: ["Logging in as an already code-linked account upgrades that link in place — it is not a switch"]
---

# Logging in as an already code-linked account upgrades that link in place — it is not a switch

## Context

`bot_account_id` (friend path) and `PlayerCredential` (own path) are
orthogonal, not tiers of one thing — a player can have neither, either, or
both. A user who code-linked an account (an unproven claim) and later logs in
as that *same* account has proven ownership. [[h-one-account-per-user]]
forbids a second link for one Discord user, so this proof cannot create a
second row — but it must not be silently discarded either, since it is the
one proof the friend-code path can never provide.

## Alternatives

| Option | Why not |
|---|---|
| Treat it as `AlreadyLinkedElsewhere` (same rule as a different account) | Wrong — it is the *same* account, and the whole point of logging in is proving it. Refusing would make ownership unprovable for anyone who registered by code first. |
| Create a second `PlayerLink` row for the same Discord user | Violates `UniqueConstraint("discord_id")` outright, and there is nothing a second row for the same user would even mean. |
| Delete the code link, insert a fresh account-proven one | Loses `linked_at` history and complicates the partial-unique `is_owner` index update for no benefit over an in-place field flip. |

## Decision

`RegistrationService._link` finds the caller's own existing link (`own`) among
an account's links. If `via is ACCOUNT` (they just logged in) and `own` is
found, it calls `_prove_in_place`, which:

1. Flips `own.linked_via` from `CODE` to `ACCOUNT` (idempotent if already
   `ACCOUNT` — a re-login on an already-proven link is a no-op ownership-wise).
2. If a **different** link on the same account is already a proven owner
   (`is_owner=True, linked_via=ACCOUNT`), `own` **coexists** without seizing
   ownership — two people who both hold the real password is a legitimate
   state, not a conflict to resolve.
3. Otherwise (no owner, or only an unproven code-owner), the newly-proven
   link **seizes ownership**: the prior code-owner's `is_owner` is cleared
   first (flushed before the flip, so the partial unique index
   `uq_player_links_owner` never observes two owners at once), then `own.
   is_owner = True`.

## Consequences

- `player_links.linked_at` for this link is untouched by the upgrade — the
  row's identity survives the tier change.
- The partial unique index enforces "at most one owner per account" even
  across this write, because the demotion is flushed strictly before the
  promotion within the same transaction.
- This is the mechanism that makes ownership provable *after the fact*: a
  user who registered by code first loses nothing by later proving
  themselves with credentials.

## Enforced at

`src/coda/players/service.py:553-581` (`_link`, the `own is not None` branch)
and `:633-662` (`_prove_in_place`).
