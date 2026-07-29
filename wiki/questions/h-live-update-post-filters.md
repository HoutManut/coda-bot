---
type: question
status: answered
blocks: ["[[live-updates|Live Updates]]"]
source: 08-live-updates-poster.md
created: 2026-07-21
updated: 2026-07-24
tags: [question, live-updates, built, filters]
aliases: ["What filters decide whether a new play is worth posting?"]
---

# What filters decide whether a new play is worth posting?

> [!success] Built
> Built 2026-07-24 in `src/coda/scores/filters.py`. See [[live-updates|Live Updates (poster)]] §11 for where the code is more specific than this answer.

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

**Answered 2026-07-24** in a design session. The full design lives in
[[live-updates-filters|Live Updates — Filters]]; this is the summary.

**Two premises in "Why it is open" above are wrong**, and correcting them is most
of the answer:

- *"Posting everything would flood a channel"* — mis-scoped. The bounding unit is
  the **player**, not the poll key: one `/friend/me` returns a play per friend, so
  a bot key can yield many plays at once, but any one account surfaces at most its
  single latest play per cycle (~40 messages/hour at the 90 s default). A channel
  K users point at can burst K posts, which the per-destination stagger and the
  guild floor handle. No individual can be flooded, so the real question is what
  is *worth* a message.
- *"did this play raise the tracked b30 sum"* being **the** settled filter — it
  is one trigger among several, and not the default.

**The algebra: triggers OR-ed, gates AND-ed.** This is what answers "how do
filters compose". Triggers are reasons to post (`all`, `pb`, `bX`, `pm`, `fr`,
`grade_up`) and any one firing is enough. Gates are restrictions (`min_level`,
plus a per-channel guild floor) and all must pass. OR-ing everything would make
"10+ charts only" a *reason* to post, so a level-3 PM still posts; AND-ing
everything makes two selected triggers mean silence.

**Per-user, not global or per-server** — stored as columns on
`live_update_prefs`, not in `REGISTRY` (`ConfigKey.type` cannot express a
combinable set plus three numbers without a hand-parsed CSV). A guild's only
lever is **gates** on its own allowlisted channels, never triggers: intersecting
two trigger sets can silently void a user's whole selection.

**Default is `pb`**, not b30. Live updates themselves stay opt-in
(`DEFAULT_ENABLED = False`).

**The b30 constraint survives intact**: `bX` uses the bot's own computed ranking
via `B30Service`, never `reported_rating`, and the **aggregate is never printed**
in a live post — it is filter input only. The per-chart play-rating line stays,
being derivable from a public score and a public CC.

**Clear-type milestones stayed out** (own-path only, deserves its own pass).
Grade milestones came *in* as `grade_up`, restricted to AA/EX/EX+ and defined as
*beating your previous best grade on that chart* rather than "any play at ≥ that
grade" — the latter fires on nearly every play a strong player makes.

Still open, deliberately: whether `min_level` should fail closed or open on a
chart the catalog does not know yet. Shipping fail-closed.
