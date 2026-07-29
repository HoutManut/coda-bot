---
type: flow
status: active
entrypoint: "extensions/recent.py (set rule) / scores/poster.py (check rule, before send)"
touches: [scores (poster, suppression), players (live.py), db (play_scores)]
created: 2026-07-29
updated: 2026-07-29
verified: 2026-07-28
grade: A
tags: [flow, live-updates, score-tracking]
aliases: ["Live Updates Suppression", "Live Updates — Suppression", "/recent Duplicate Suppression"]
---

# Live Updates — Suppression

Split out of [[live-updates|Live Updates (poster)]] 2026-07-29 (that page had grown past the
vault's 300-line soft threshold — see `meta/lint-report-2026-07-29.md`). Covers `/recent`
duplicate suppression: the in-memory marker, the set rule (`/recent`), and the check rule
(poster, immediately before send). Trigger/gate filter logic lives in
[[live-updates-filters|Live Updates — Filters]]; poster routing/send mechanics live in
[[live-updates-poster|Live Updates — Poster]].

---

## `/recent` duplicate suppression

**Decision: suppress, not merely delay.** The duplicate is the common case (a play surfaced by
`/recent` before the poller had processed it is the routine case, not the exception — see
[[live-updates|Live Updates (poster)]] §1 Facts that constrain the design), which is what tips
this past "delay-only, zero machinery". Answers [[h-recent-duplicate-suppression]].

### The marker

In-memory, process-local, `ObservationCache`-sized:

```
(destination, play_score_id) -> monotonic timestamp
```

`destination` is the same key the poster sends on: a `channel_id`, or
`("dm", discord_id)`.

**Keyed per destination, and that is sufficient.** `/recent`'s reply is public
([[live-updates|Live Updates (poster)]] §1), so the channel it replied in has genuinely shown
the play to everyone watching — including co-linkers, who would otherwise have received the
same single message under [[live-updates-poster|Live Updates — Poster]] §Whose play is it's
per-destination send. If the user's live destination is a *different* channel, that channel
has shown nothing and still gets the post. A DM destination carries the `discord_id` inside
the key, so one user running `/recent` never suppresses another's DM.

This is simpler than it looked before the per-destination send design: with one message per
destination rather than one per linked user, "who requested it" stops mattering — the
question is only whether that surface already displayed the play.

### Set rule (`/recent`)

After `request_refresh` returns and the play to display is known, but **before**
`ctx.respond`:

- call `resolve_destination(db, discord_id)`;
- mark only if `enabled` **and** the resolved destination matches where the reply
  is going — in a guild, `channel_id == ctx.channel_id`; in a DM,
  `channel_id is None`, marked as `("dm", discord_id)`;
- mark on the stored row's id. A play rendered from `ObservationCache` alone
  (tracking off, no stored row — `recent.py:100`) has no id, and nothing will
  ever post it, so there is nothing to mark.

### Check rule (poster)

Checked **immediately before send**, after the stagger sleep — not at enqueue
time. With `INITIAL_DELAY` ([[live-updates-poster|Live Updates — Poster]] §Ordering and
stagger) this leaves no practical race: the poster cannot send before `/recent`'s own read
completes.

**TTL 15 minutes**, pruned lazily on insert. The TTL bounds memory only; it can
never suppress a *later* sighting, because there is no later sighting.

### Deliberately not done

- No suppression across destinations — the DM keeps its copy when `/recent` ran
  in a channel, since the DM is the user's archive.
- Does not survive a restart. A restart mid-window costs one duplicate.

---

## Related

[[live-updates|Live Updates (poster)]] · [[live-updates-filters|Live Updates — Filters]] ·
[[live-updates-poster|Live Updates — Poster]] · [[h-recent-duplicate-suppression]]
