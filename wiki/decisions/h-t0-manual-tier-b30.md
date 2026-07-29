---
type: decision
status: active
date: 2026-07-23
reverses:
created: 2026-07-23
updated: 2026-07-23
tags: [decision, scores, potential, registration, unbuilt]
aliases: ["t0 tier: no account link, manual score import only, b30 computed from it"]
---

# t0: no account link, manual-only score entry, b30 computed from it

## Context

[[h-manual-score-import]] left open whether manually entered scores should
feed rating calculations at all, given nothing on the bot's side corroborates
a hand-typed score the way wire data does (catalog CCs are copied from the
game and treated as fact; a manual score has no such corroboration).
Separately,
every existing access path in [[auth-and-sessions]] assumes *some* account
link (friend code at minimum). There was no path for a user who links
nothing at all.

## Alternatives

| Option | Why not |
|---|---|
| Require at least a friend-code link before any score data exists | Locks out users who don't want to link an account at all, or can't (no bot-account friend slot available) — the exact gap this tier closes. |
| Manual entries exist for display only, never feed b30 | Leaves t0 users with zero rating value ever, since they have no other data source — defeats the point of offering them anything. |
| Gate manual entry behind heavy verification/trust marking | b30 is a self-facing tool — a user who types a fake score only degrades the number they themselves see. No shared harm to defend against, so no need to engineer around one. |

## Decision

Introduce **t0**: a tier with no account link at all (no friend code, no
credentials). At t0, manual score import is allowed, and b30 is computed
from manually imported scores only — this is the tier's sole data source.

- No corroboration is possible at t0 by construction, and none is needed:
  b30 is a personal-facing number. A user who lies only lies to themselves —
  self-correcting by nature, not a case that needs verification machinery.
- r10 is not addressed by this decision — [[d-r10-impossible-friend-path]]
  is about the friend path specifically; whether t0 gets an r10 equivalent
  from manual data is open, deferred to [[h-manual-score-import]].
- Mechanics (storage shape, single-entry vs bulk, validation) stay open in
  [[h-manual-score-import]] — this decision settles the tier concept and the
  b30-inclusion policy, not the implementation.

## Consequences

- No source/trust flag or verification UI needed on b30 display — same
  treatment as any other b30, since a bad manual entry only misleads its own
  owner.
- If a t0 user later links an account, wire-sourced data replaces the manual
  entries outright — manual was always a stand-in for data the bot couldn't
  see yet, not a history to preserve alongside the real thing. Same
  treatment as correcting a typo, not a merge.

## Enforced at

Not yet built.
