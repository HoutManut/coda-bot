---
type: gotcha
status: active
severity: medium
area: dto
verified: 2026-07-17
created: 2026-07-21
updated: 2026-07-21
tags: [gotcha, scoring, sentinel]
aliases: ["`score: 0` is a real score (all notes lost), not a missing-data sentinel"]
---

# `score: 0` is a real score (all notes lost), not a missing-data sentinel

## Symptom

A play where every note was lost gets silently dropped from tracking, skipped in a poll diff, or
treated as "no score yet" for a chart the player has actually attempted and failed completely.

## Cause

`score = floor(10_000_000 * (pure + far/2) / note_count) + shiny_pure_count` (see [[Scoring]])
is a real formula with a real minimum: if `pure_count == far_count == shiny_pure_count == 0`
(every note lost), the formula evaluates to exactly `0`. That is a legitimate, fully-formed
result — the chart was played and the score is `0` — not an absence of data. This sits alongside
the project's general DTO rule (`dto/` is the volatility absorber — see project `CLAUDE.md`
§Security) that other sentinel-looking values in the same response shapes (e.g. `-1` for hidden
PTT, `-1`/`0` for level/CC) really *do* mean "missing" or "unknown" — `score` is the one field in
this neighborhood where `0`/falsy is not a sentinel at all.

## The wrong fix

Applying a generic "falsy means absent" check to `score` the same way it's correctly applied
elsewhere in the DTO layer (e.g. `if not data.get("score"): skip`). That pattern is right for
genuinely absent fields but wrong here — it silently discards every all-lost play, which is
indistinguishable in code from "field wasn't in the response" but means something completely
different in the domain (a real, terrible play, not a missing one).

## The right handling

Distinguish "key absent / `None`" from "key present with value `0`" explicitly when parsing a
score DTO — `.get("score")` returning `None` means the field truly wasn't sent; `0` is a value.
Never write `if not score:` as a stand-in for "was a score reported".

## Regression signal

A player's poll history or `/recent` output is missing an all-lost attempt they can confirm they
played; a chart's "first attempt" tracking never records a `0` as the baseline.
