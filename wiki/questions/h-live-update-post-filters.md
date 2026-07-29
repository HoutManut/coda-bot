---
type: question
status: open
blocks: ["[[Live Updates]]"]
source: 08-live-updates-poster.md
created: 2026-07-21
updated: 2026-07-21
tags: [question, live-updates, filters, unbuilt]
aliases: ["What filters decide whether a new play is worth posting?"]
---

# What filters decide whether a new play is worth posting?

## Why it is open

Handoff 08 states plainly: *"Posting is filtered, and the filter set is NOT
designed yet... Design the filters as their own piece of work when this doc
is picked up — plural, layered, probably user-configurable."* Not every
genuinely-new play (a first-insert row from `ScoreStore.ingest`) should
generate a Discord message — but nothing says which should, beyond the one
settled case below. Posting *everything* would flood a channel with routine
grinding; posting *nothing but PBs* might miss what users actually want
notified about.

Exactly one filter is settled: did this play raise the account's tracked b30
sum ([[b30]], §8 of [[handoff-09-b30]])? Even that one carries a
constraint that must survive whatever filter design lands on it: it must use
the bot's own computed b30 sum, never the server's `reported_rating`
(quantized to 0.01 PTT, permanently NULL for a hidden player) — and for a
hidden player the flag may fire while the number must never be printed, in
any recoverable form.

## What would answer it

A design session (owner + implementer) once handoff 08 is picked up, deciding
at minimum:

- What other conditions exist beyond "raised b30" — e.g. any new play at all
  (opt-in noisy mode), a personal best on a specific chart, a clear-type
  milestone (own-path only, since friend-path plays have no `clear_type`).
- Whether filters are global defaults, per-server, or per-user configurable
  — "probably user-configurable" is a hint, not a decision.
- How filters compose when several would independently fire on one play.

## Current best guess

No guess ventured in the source — explicitly deferred to its own design
pass rather than defaulted.

## Answer

Not yet answered.
