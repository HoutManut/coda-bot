---
type: decision
status: active
date: 2026-07-29
reverses:
created: 2026-07-29
updated: 2026-07-29
tags: [decision, scores, potential, unbuilt]
aliases: ["manual score import: scope, storage, linked-account b30, access"]
---
# Manual score import: single-entry first, same table + flag, feeds b30 same as t0, self-service

## Context

[[h-manual-score-import]] left four sub-questions open after
[[h-t0-manual-tier-b30]] settled that t0 manual entries feed b30. This
decision settles the remaining mechanics: scope, storage shape, linked-account
treatment, access control.

## Alternatives

| Option | Why not |
|---|---|
| Bulk import (CSV/JSON) first | Different validation design than single-entry; no concrete external-tool export target yet to design against. |
| Separate table for manual entries | `B30Service.compute` ([[h-b30-cache-stores-sum]]) is already source-agnostic, branching on `play_scores.source`; a second table forces a union at read time for no gain. |
| Linked accounts reconcile manual vs wire number | Adds merge logic for a self-facing tool where a bad entry only misleads its own owner — same reasoning [[h-t0-manual-tier-b30]] already used for t0, no reason to treat linked differently. |
| Admin-only entry | Inconsistent with rest of bot at <50-user scale; no concrete abuse case to justify an approval workflow. |

## Decision

- **Scope**: build single-entry first. Bulk import stays a future path, not
  designed yet.
- **Storage**: same `play_scores` table, new `source='manual'` value (or
  equivalent flag) — no separate table.
- **Linked accounts**: manual entries feed b30/r10/PTT the same way t0's do —
  no reconciliation against wire data, no verification/trust marking.
- **Access**: self-service, no admin approval workflow.
- **Command shape**: `/score` group — `add`, `delete`, `get`, and likely
  `update` subcommands — rather than one flat `/addscore` command. `add`
  targets a `(song, difficulty)`; resubmitting `add` for an existing pair is
  the de-facto edit path (see duplicate handling below), so `update` may
  turn out to just be an alias for `add`'s overwrite behavior rather than
  distinct logic — not settled, low-risk either way. `delete` exists as its
  own subcommand because overwrite can't express "this entry shouldn't
  exist" (e.g. wrong song/difficulty was picked, not just a wrong score).
- **Fields**: song, difficulty, score only. Grade/clear-type/PM-MPM derive
  from score per existing scoring domain rules ([[scoring]]) — no separate
  clear-type input, no pure/far/lost breakdown.
- **Duplicate handling** (`add` on a `(song, difficulty)` that already has a
  manual entry): backend allows the write unconditionally, including a lower
  score than what's stored — no hard block. The command layer is
  responsible for prompting the user to confirm before writing when the new
  score is lower than the existing one. A higher score overwrites without a
  confirmation prompt.

## Consequences

- b30 read side needs zero changes — `'manual'` slots in next to
  `'friend'`/`'own'`.
- Write side still needs: the `/score` command group itself, validation
  reusing chart-resolution ([[chart-resolution]], score-mapping's `byd_2`/
  `game_song_id` handling), the lower-score confirmation prompt (command
  layer, not backend), and — for linked accounts — a decision on what
  happens when a manual entry and a later wire-sourced score for the same
  `(song, difficulty)` both exist (not addressed here, same open edge as t0's
  wire-replaces-manual rule in [[h-t0-manual-tier-b30]]).
- Bulk import, when eventually designed, is additive on top of this — same
  storage shape, different entry path, and would need its own confirmation
  model since bulk submissions can't prompt per-row the way a single command
  can.

## Enforced at

Not yet built.
