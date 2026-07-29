---
type: decision
status: active
date: 2026-07-18
reverses: "the earlier AccountClaimed outright refusal (an unproven second code claim used to be rejected unconditionally); superseded by the owner-consent flow"
created: 2026-07-21
updated: 2026-07-21
tags: [decision, registration, consent, approvals]
aliases: ["A second unproven claim on a linked account asks the owner — silence never means yes"]
---

# A second unproven claim on a linked account asks the owner — silence never means yes

## Context

A friend code is public; anyone can type anyone's. When account A is already
linked by user X and user Y tries `/register` with A's code, nothing on the
wire can tell the bot whether Y is an alt of X, a legitimate second person
sharing the account, or a stranger. The prior design (`AccountClaimed`)
refused this outright — safe, but wrong whenever the second claim was
legitimate (an alt, a shared account).

## Alternatives

| Option | Why not |
|---|---|
| Refuse outright (prior `AccountClaimed` behavior) | Blocks every legitimate second link (alts, shared accounts) as collateral damage from blocking illegitimate ones. |
| Allow it silently | A code proves nothing — this would let anyone claim to track anyone's scores by typing a public code, with no owner awareness at all. |
| Require credentials for any second claim | Forecloses the common legitimate case (a friend/sibling sharing an account by agreement, without necessarily holding the password) unnecessarily. |

## Decision

`register_by_code` returns `NeedsApproval` instead of creating a row when an
unproven code claim targets an account someone else already owns. The caller
(`players/link_approval.py`) creates a durable `PendingRequest`
(`kind="link_approval"`) and DMs the current owner Approve/Deny buttons.

- **Silence never means yes**: a 24-hour TTL, or an owner whose DMs are
  closed (the DM send fails), both **refuse** — the pending row is rolled
  back on a failed DM send rather than left to expire unseen, and the
  requester is told immediately either way.
- **Credentials override and settle it outright**: logging in as the account
  is real proof, promoting the prover to `is_owner` in place — see
  [[h-login-upgrades-link-in-place]]. This consent flow exists only for the
  code path, which can never produce that proof.
- On approval, the requester is **re-checked** against
  [[h-one-account-per-user]] before the link is created — they may have
  linked something else while the request sat open, and the one-account rule
  still applies at resolution time, not just at request time.
- An approved link is still `linked_via=CODE, is_owner=False` — approval
  grants coexistence, not ownership. Ownership only ever moves via proof.

## Consequences

- Every approval decision is durable across a bot restart (`PendingRequest`
  survives it; the requester's original interaction does not, which is
  exactly why this could not be an in-memory component flow).
- A user with closed DMs functionally cannot be asked for consent — the
  system fails toward refusal, not toward an unanswerable pending state.
- This is what makes "many Discord users → one Arcaea account" legitimate
  cardinality rather than an exploit: every non-owner link on a shared
  account was either explicitly approved by the owner or independently
  proven by its own login.

## Enforced at

`src/coda/players/service.py:161-229` (`register_by_code`, the
`NeedsApproval` branch), `src/coda/players/link_approval.py`
(`request_link`, `_LinkApprovalHandler.on_decision`/`on_expire`),
`src/coda/approvals/` (the durable `PendingRequest` machinery),
`src/coda/db/models/pending_request.py`.
