---
type: decision
status: active
date: 2026-07-17
reverses:
created: 2026-07-21
updated: 2026-07-21
tags: [decision, wire, validation, registration]
aliases: ["Validate friend-code shape locally, before any network call"]
---

# Validate friend-code shape locally, before any network call

## Context

lowiro's `add_friend` endpoint does not validate friend-code shape server-side. Live capture
(`arcaea-auth-behavior.md` §7.4.1) submitted three deliberately bad inputs — a well-formed
but nonexistent code, a too-short code, and a 16-character alphanumeric string — and all
three returned the **identical** `404 {"success":false,"error_code":401}`. There is no
distinct malformed-input error code; lowiro treats "not a real code" and "not even a code"
identically.

## Alternatives

| Option | Why not |
|---|---|
| Send whatever the user typed straight to `add_friend` and surface lowiro's `401` verbatim | The response is indistinguishable from a legitimate typo'd-but-well-formed code — the user gets "no such player" for something that was never a code at all, which is confusing and unactionable |
| Validate shape locally but strip *every* non-digit character to be maximally forgiving of copy-paste noise | Manufactures a plausible 9-digit code out of garbage input (`00000002ie1oi2ee` → `000000022`) rather than rejecting it — see [[w-friend-code-strip]] for the full failure story. Rejected explicitly; do not reintroduce |
| Validate shape locally, but only as a UX nicety with a fallback that still sends non-conforming input if validation "seems overly strict" | Defeats the point — the entire value of local validation is that it is the *only* thing able to say "that's not a friend code" instead of the wire's uniformly unhelpful `401` |

## Decision

Reject non-9-digit input **before any request leaves the process** — not because lowiro
requires it (it demonstrably does not enforce shape at all), but because lowiro's uniform
`401` for "malformed" and "well-formed but fake" makes local validation the *only* source of
a useful distinction. Normalization strips **separators only** (`123 456-789` →
`123456789`); anything else that fails to leave exactly 9 digits is rejected outright as
`InvalidFriendCode`, surfaced as "that's not a friend code" rather than "no such player".

## Consequences

- This is "our business" entirely — lowiro's behavior does not motivate any particular
  validation strictness, since it will accept and uniformly reject anything malformed
  server-side regardless. The bot's local rule is free to be as strict as is genuinely useful
  to users, independent of the wire.
- The distinction this buys — "that's not a friend code" vs. "no such player" — is the
  entire reason the check exists ahead of the network call, not merely an optimization to
  save a round trip.
- Reserved-code checks (`reserved.check_static`, `reserved.is_bot_account`) run **after**
  this validation but still before any network call, for the identical reasoning: lowiro's
  answer for a reserved code would also be unhelpful (`401` for the easter eggs, a real
  friend-add for a bot account), so deciding locally is what buys an honest message in both
  cases.

## Enforced at

`src/coda/utils/friend_code.py::clean_friend_code` — called from
`players/service.py::register_by_code` as the very first step, before `reserved.check_static`,
before `current_account`, before any `SessionPool` involvement. See
[[w-friend-code-strip]] for the specific garbage-input failure mode this prevents.
