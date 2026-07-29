---
type: source
status: active
path: arcaea-api-research-tasks.md
lines: 310
dated: 2026-07-17
verified: 2026-07-17
supersedes: []
superseded_by: []
created: 2026-07-21
updated: 2026-07-21
tags: [source, research, history, arcaea]
aliases: ["arcaea-api-research-tasks.md"]
---

# arcaea-api-research-tasks.md

## Covers

Pre-implementation research tasks 1–15 for the API layer, kept as a **historical record**
of what was asked and how it was answered — the document's own header states "ALL TASKS
CLOSED. This document is history" and explicitly redirects: `arcaea-auth-behavior.md` is
the authoritative wire reference, `arcaea-api-layer.md` documents what was built. Grouped
1) login/session mechanics, 2) API behavior (add_friend errors, remove_friend, friends
pagination, own-vs-friend `/me` shape), 3) aiohttp compatibility (cookie replay, multipart
form-data), 4) design decisions (Fernet key strategy, bot-account seeding, credential
registration UX, `max_friend` in practice).

## Key claims

- All of tasks 1–5, 7, 9, 15 resolved by direct HTTP Toolkit capture. Task 6 partial (602
  confirmed at the time; cap-exceeded deprioritized as a design non-blocker — later
  generalized in code to "any unrecognized error_code on add ⇒ try next account"). Task 8
  closed — no pagination, ever (structurally capped at 25 by `max_friend`). Task 10 closed —
  `sid` alone replays fine, sent as an explicit `Cookie` header rather than through a cookie
  jar (verified against shipped code: `client.py::_get_session` uses
  `aiohttp.DummyCookieJar()` specifically to prevent jar-based cross-account sid leakage —
  a design detail this doc's task 10 answer does not go into but the shipped code motivates
  more strongly than either doc: `Domain=lowiro.com` parent-domain matching would otherwise
  merge one bot account's sid into another's request). Task 11 closed, and **failed** —
  `aiohttp.FormData` is unusable; see [[w-formdata-504]].
- Task 12 (Fernet key strategy) decided: one `FERNET_KEY`, no rotation path — see
  [[w-single-fernet-key]].
- Task 13 (bot account seeding) built as a CLI script, matching
  `scripts/seed_bot_account.py`.
- Task 14 (credential registration UX) built as an ephemeral modal, not a DM-only or
  out-of-band form.
- Task 15 (`max_friend` in practice) answered 10 on a fresh account, ladder to 25 — feeds
  the pool sizing claim in [[Auth & Sessions]].

## Contradicts / reversed by

Nothing in this document is itself reversed by anything downstream — it is explicitly
superseded-by-design (its own header says so) in favor of `arcaea-auth-behavior.md` and
`arcaea-api-layer.md`. No open items remain in it; do not treat it as a work list per its
own instruction.

## Feeds

[[arcaea-auth-behavior]], [[arcaea-api-layer]], [[w-formdata-504]],
[[w-single-fernet-key]]
