---
type: question
status: answered
source: conversation 2026-08-31
created: 2026-08-31
updated: 2026-08-31
tags: [question, potential, ptt, 7.0, discord-surface]
aliases: ["What should the clear-override review surface look like?"]
---

# What should the clear-override review surface look like?

## Why it is open

[[d-clear-bonus-impossible-friend-path]] settles that a tier-1 row's clear status defaults to a
score-threshold heuristic (`>= 9,000,000` assumed cleared) with a per-row `clear_override` the
account owner can set. What it deliberately leaves open is *how the owner is asked* — putting a
toggle on every `/score` chart lookup was rejected as UI clutter (owner, 2026-08-31): most rows
never need a correction, so a control on every row asks the wrong ratio of questions to answers.

The agreed scoping (owner, 2026-08-31) is a filtered **review queue**, not a blanket toggle: only
rows that are simultaneously tier-1, currently the chart's *resolved-best* entry (the one actually
feeding the rating calc — a buried non-winning row isn't asking anything of anyone), currently
inside the counted pool (top-50, or top-10 within it), and unconfirmed (`clear_override is None`).
That bounds the queue to at most pool-size (50) and in practice far fewer after first use — it only
regrows when a new PB or an override flip promotes a different, previously-buried row into a
chart's resolved-best slot (the cascade described in [[d-clear-bonus-impossible-friend-path]]'s
worked example).

Also settled (owner, 2026-08-31): **pull-only for now** — no passive hint on the aggregate b50/PTT
embed pointing at the queue. The review surface has to be something the owner goes and checks, not
something that gets pushed at them. Revisit the passive-hint question once the pull-only surface
has shipped and it's clear whether people actually remember to check it.

## What would answer it

- Where the review surface lives: a `/score` subcommand (`/score review`), or does this justify
  standing up the future b50/potential command earlier than planned and hanging it there instead?
- Row layout: one compact list (song — chart — score — assumed status) with confirm/deny buttons
  per row, vs. one-row-at-a-time paging. Discord's per-message component limits cap how many rows
  can carry interactive buttons at once regardless.
- Whether confirming/denying one row should immediately re-render the queue with a newly-promoted
  row appended (the A/B cascade), or require a manual re-check.
- Whether this reuses `/score`'s existing invoker-gated persistent-component pattern
  (`_on_score_component` in `src/coda/extensions/score.py`) or needs its own listener.

## Current best guess

A `/score review` subcommand, compact list layout capped by Discord's component limits with
pagination if the queue ever exceeds them (unlikely in practice — bounded by pool size), reusing
the existing owner-gated custom-id pattern from `score.py`. Re-render the queue in place after each
confirm/deny so a cascade-promoted row is visible without a second command invocation. Not
designed in code-level detail yet — filed to hold the scoping decision, not to lock the layout.

## Answer

**Answered and built 2026-08-31** (owner decisions, same session). `src/coda/extensions/potential.py`
and `src/coda/scores/clears.py`.

- **Placement**: a new top-level **`/potential`** rather than `/score review`. `/score` is a flat
  command, so hanging a subcommand off it would turn every lookup into `/score chart q:…` — a
  regression on the far commoner path. `/potential` also closes the *other* unbuilt half of the
  rework (the aggregate had no home outside the `/recent` impact line), and the queue is a list of
  pool entries, so it is a potential view. Still pull-only: the entry point is a button on
  `/potential` itself, never a hint pushed from a score embed.
- **Row layout**: one card at a time — score, rating line, jacket, `[Cleared] [Failed] [Skip]`,
  with `#rank in your pool · n of N`. Chosen over a compact multi-row list because Discord's
  five-action-row cap leaves a 5×2-button list no room for paging controls, and over a select menu
  because that costs two interactions per correction.
- **Cascade**: the queue is rebuilt from source on every interaction and answering re-renders at
  the *same index*, so the answered row drops out and the next one — including a newly-promoted
  buried row — appears in place. Nothing about the queue is carried in a custom id but the index.
- **Bulk**: an `Accept all N guesses` button writes each entry's assumed status as an explicit
  answer. Numerically a no-op; the point is that the rows stop being questions.
- **Reversibility** (not in the original scoping, added because bulk-accept made it load-bearing):
  the card has two modes. `unconfirmed` is the queue proper; `all` also lists rows already
  answered, so an override can be flipped back. Without it, setting one — and accept-all
  especially — would be a one-way door, since an answered row leaves the queue forever.
- **Listener**: its own `pot:` custom-id contract mirroring `score.py`'s invoker-first shape, not
  a reuse of `_on_score_component` — the two dispatch tables have nothing in common.
