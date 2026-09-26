---
type: decision
status: active
date: 2026-07-29
reverses:
created: 2026-07-29
updated: 2026-07-29
tags: [decision, recent, potential, unbuilt]
aliases: ["/recent ptt/b30/r10 config: r10 omitted on friend path, not shown as unavailable"]
---
# `/recent` rating-impact config: friend-path scores omit r10 entirely, don't show a placeholder

## Context

[[h-recent-config-ptt-b30-r10]] left the friend-path degradation choice open:
[[d-r10-impossible-friend-path]] means r10 delta cannot be computed for
scores that came in via the friend read path (tier-1 recent tracking is
dropped, not approximated). The config toggle needs one consistent behavior
rather than silently lying on some rows.

## Alternatives

| Option | Why not |
|---|---|
| Show "unavailable" placeholder | Extra UI state for every friend-path row, permanently — the gap is structural (never resolves), so a placeholder just becomes visual noise the user learns to ignore. |
| Restrict config option to owner/self-tracked accounts only | Also hides b30/ptt impact (which *is* computable on friend path) — punishes the whole feature for r10's gap instead of degrading the one field that's actually blocked. |

## Decision

`/recent` PTT/b30/r10 config always shows b30/ptt impact when computable.
r10 impact is shown when computable (self-tracked path) and simply omitted
— no field, no placeholder — on friend-path scores.

## Consequences

- Embed layout must not reserve a fixed r10 line — it's conditional per-row,
  not per-user, since a single account can have both friend-path and
  self-tracked scores.
- No new privacy/consent surface: reuses [[potential]]'s existing
  self-invoke-is-consent rule, unaffected by this decision.
- [[h-r30-queue-view]] inherits the same per-row omission once it depends on
  this page's r10 computation.

## Enforced at

Not yet built.
