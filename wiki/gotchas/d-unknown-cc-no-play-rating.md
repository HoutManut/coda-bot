---
type: gotcha
status: active
severity: high
area: catalog
verified:
created: 2026-07-21
updated: 2026-07-21
tags: [gotcha, potential, catalog, sentinel]
aliases: ["An unknown chart constant yields NO play rating — never substitute 0"]
---

# An unknown chart constant yields NO play rating — never substitute 0

## Symptom

A newly-released chart with a TBA chart constant (`rating <= 0`, see [[catalog|Catalog]]) shows a play
rating of `cc + 2` = `2.0` (or similarly nonsensical low number) for a MAX play, or silently
enters the b30/r10 pool computation with a wrong low rating instead of being excluded.

## Cause

Play rating is `cc + f(score)` (see [[potential|Potential]] §Encoding) — it is **undefined**, not zero,
when `cc` itself is unknown (`rating <= 0`, the TBA/`err`-only sentinel band shared with
[[d-level-cc-sentinel-values]]). Treating the sentinel as `cc = 0` produces a plausible-looking
but fabricated play rating (e.g. `0 + 2 = 2.0`) for what should be "cannot compute" — and that
fabricated number is low enough to look like a real (bad) chart rather than an error, so it
passes silently into any downstream max/average/sort.

## The wrong fix

Defaulting the chart constant to `0` (or any other numeric placeholder) before computing play
rating "so the formula doesn't crash on a null". This produces a real floating-point value that
looks legitimate and will happily enter a b30/r10 computation, a leaderboard, or a `/song`
embed's "your best play rating here" line — there is no downstream signal left that the number
was fabricated.

## The right handling

Check `rating <= 0` on the chart **before** calling the play-rating formula and short-circuit to
an explicit "no play rating" state (`None`, not `0`) for that chart. Newly-released songs with
TBA CC are a real, expected hole — [[potential|Potential]] §"Inputs are cheap" calls this out directly: a
chart with unknown CC "yields **no** play rating and simply cannot enter either pool" until the
catalog is updated with the real value.

## Regression signal

A b30/r10 entry, or a computed PTT, referencing a chart known to have a TBA constant; a play
rating of exactly `2.0`/`1.0`/`0.0` on a MAX/EX/low-score play for a song that just released.
