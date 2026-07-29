---
type: question
status: open
blocks: []
source: arcaea-tournament-layer.md
created: 2026-07-21
updated: 2026-07-21
tags: [question, tournaments, low-priority]
aliases: ["How long is song-select → load → results, really — and does `2t` buy one attempt or two?"]
---

# How long is song-select → load → results, really — and does `2t` buy one attempt or two?

## Why it is open

The tournament window formula `clamp(2t, 100s, 5m)` ([[Tournaments]] §3)
assumes an "overhead" figure (song select, load, results screen) of
20–40s, used only as a rough estimate: `attempts ≈ floor(D / (t + overhead))`.
At `t=120, D=240, o=30` that floors to exactly 1 attempt; the real overhead
value decides whether a round format that wants two attempts per player
actually delivers on that promise, or silently gives everyone one.

**This only matters under the `best` scoring rule.** Under the `first`
default, the window is never consumed — it functions purely as a forfeit
timeout, since retrying cannot change a `first` result, so the exact overhead
figure is currently inert in the shipped default.

## What would answer it

Time an actual song-select → load → results round-trip in the live client a
few times and replace the 20–40s estimate with a measured range. Cheap to
do, but only worth doing once a `best`-scored tournament format is actually
being planned.

## Current best guess

20–40s, as stated in the source doc — an estimate, not a measurement.

## Answer

Not yet answered. Not blocking anything under the `first` default.
