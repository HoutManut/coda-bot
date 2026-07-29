---
type: source
status: active
path: 06-credentials-changed-server-side.md
lines: 48
dated: "recorded 2026-07-17"
verified: 2026-07-21
supersedes: []
superseded_by: []
created: 2026-07-21
updated: 2026-07-21
tags: [source, handoffs, credentials, unresearched]
aliases: ["06 — Stored credentials can be changed server-side"]
---

# 06 — Stored credentials can be changed server-side

## Covers

A single captured-from-the-owner observation: an Arcaea account's password can
stop matching what the bot has stored **without the bot doing anything or
being told**. Explicitly a note, not a design — "everything below the first
section is an open question, not a finding."

## Key claims

- The problem statement itself (server-side credential change can silently
  invalidate a stored password) is the only established fact. Recorded
  2026-07-17.
- Everything else is an open question: whose credentials (bot accounts vs.
  `PlayerCredential`, different blast radii), changed by whom and why, how it
  surfaces on the wire (presumably 403 on `auth.login`, unconfirmed), whether
  current handling (`PlayerCredential.is_valid` terminal-on-403;
  `BotSession`'s own deactivation path) is actually adequate, and how a user
  would ever find out (no notification path exists today).
- Explicit **do not**: never log a password or credential-path exception
  context; never assume `FERNET_KEY` is the cause (a key change orphans every
  encrypted row with no rotation path — a similarly-shaped but distinct
  incident, see [[db]] §FERNET_KEY gotcha).

## Contradicts / reversed by

None — this is a standalone note with no relationship to another doc's
claims.

## Feeds

`[[h-credentials-changed-server-side]]`
