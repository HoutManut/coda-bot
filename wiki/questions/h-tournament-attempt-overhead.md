---
type: question
status: superseded
blocks: []
source: arcaea-tournament-layer.md
created: 2026-07-21
updated: 2026-09-05
tags: [question, tournaments, low-priority]
aliases: ["How long is song-select → load → results, really — and does `2t` buy one attempt or two?"]
---

# How long is song-select → load → results, really — and does `2t` buy one attempt or two?

> [!warning] Closed 2026-09-05 — the rule it sized a window for is gone
> This question only ever mattered for `best`, and `best` is retired:
> [[h-first-score-is-the-only-rule]]. A round counts the first valid score, so
> the window is a forfeit timeout and never a budget anyone spends attempts
> from — there is no format left whose attempt count an overhead figure would
> decide. Overhead may come back as an *input* to
> [[h-tournament-quit-rerolls-first]], which is about how many rerolls a quit
> buys under the only rule there is; that is a different question and is open
> on its own page. Everything below is kept as the reasoning that reached here.

## Why it was open

The tournament window formula — `clamp(2t, 200s, 500s)` since 2026-09-02
([[tournaments|Tournaments]] §3) — assumes an "overhead" figure (song select,
load, results screen) of 20–40s, used only as a rough estimate:
`attempts ≈ floor(D / (t + overhead))`. The real overhead value decides
whether a round format that wants two attempts per player actually delivers on
that promise, or silently gives everyone one.

**Narrowed 2026-09-02.** Under the current bounds neither end clamps any
catalog chart, so every real round is a plain `2t`, and
`floor(2t / (t + o))` evaluates to **1 across the entire catalog
(`t` = 100–189s) and the entire overhead estimate (20–40s)**. So the open
figure no longer changes the attempt count, and it no longer makes the budget
inconsistent between short and long songs — that caveat came from the old 5m
ceiling and is retired. What stays open is only whether a *two*-attempt format
is reachable at all, which would need a window wider than `2t`, not a better
overhead estimate.

**This only mattered under the `best` scoring rule** — which is why it closed
with it. Under the rule that shipped, the window is never consumed: it
functions purely as a forfeit timeout, since a retry cannot change a result
already bound to the first score.

## What would answer it

Time an actual song-select → load → results round-trip in the live client a
few times and replace the 20–40s estimate with a measured range. Cheap to
do. Nothing needs it now; if [[h-tournament-quit-rerolls-first]] takes an
attempt-cost approach, measure it then.

## Current best guess

20–40s, as stated in the source doc — an estimate, not a measurement.

## Answer

Superseded rather than answered: the overhead figure is still an estimate, and
nothing reads it. See [[h-first-score-is-the-only-rule]].
