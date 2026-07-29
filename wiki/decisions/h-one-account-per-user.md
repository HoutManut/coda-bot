---
type: decision
status: active
date: 2026-07-18
reverses: "handoff 03's original design ('newest wins' — a later registration silently supersedes an earlier link). That design never reached a *.md doc; it existed only in the now-deleted handoff 03 and is recorded here as the reversed alternative."
created: 2026-07-21
updated: 2026-07-21
tags: [decision, registration, player-links]
aliases: ["One account per Discord user; no atomic switching"]
---

# One account per Discord user; no atomic switching

## Context

A Discord user registering while already linked to an Arcaea account needs a
rule. The original handoff-03 design (deleted once revised) was "newest
wins" — a second registration would silently replace the first link. That
was reversed before landing.

## Alternatives

| Option | Why not |
|---|---|
| "Newest wins" (original design) | Silent data loss — a user's prior link (and whatever expectations depended on it) disappears without confirmation on a single new registration attempt, accidental or not. |
| Allow many simultaneous links per Discord user | Breaks "who does `/b30`, `/recent` etc. mean" — every score-reading command would need a target-account disambiguation step that does not otherwise exist. |
| Silent atomic switch (delete old link, create new, in one step) | Still a silent destructive action on the old link; conflates "I want a different account" with "I'm confirming that". |

## Decision

`player_links` carries `UniqueConstraint("discord_id")`: a Discord user holds
**exactly one** link, always. Registering a **different** account while
linked is refused with `AlreadyLinkedElsewhere` — and that refusal fires
**before any friend slot is consumed or, on the credentials path, before any
new row is created** (the login still happens on that path, since `/me`'s
`arc_user_id` is needed to know who to compare against, but nothing is
persisted). There is **no atomic switch**. Changing accounts is
`/unregister` (which [[h-straying-preserves-history|strays]] the old account
if it was its last link) followed by a fresh `/register`.

The reverse cardinality — **many Discord users → one Arcaea account** —
stays legal, created only through the consent flow
([[h-owner-consent-on-second-claim]]), not through this rule.

## Consequences

- A user cannot "just switch" in one command; `/unregister` then `/register`
  is two explicit steps, each independently confirmable.
- The refusal-before-consumption ordering means a *rejected* switch attempt
  never wastes a bot account's scarce (~10) friend slots or creates orphan
  rows to roll back.
- `RegistrationService.current_account` (one query, `UniqueConstraint`-backed)
  is the single source of truth for "does this user already link something,
  and what" — both register paths call it before doing anything else.
- Logging in as an account already **code**-linked by the same user is
  explicitly **not** a switch — see [[h-login-upgrades-link-in-place]].

## Enforced at

`src/coda/db/models/arcaea_account.py:88` (`UniqueConstraint("discord_id")`
on `PlayerLink`), `src/coda/players/service.py`
(`RegistrationService.register_by_code:199-201`,
`register_by_credentials:272-274`, both via `current_account`).
