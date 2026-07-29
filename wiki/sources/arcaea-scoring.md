---
type: source
status: active
path: arcaea-scoring.md
lines: 203
dated: 2026-07-17
verified: 2026-07-17
supersedes: []
superseded_by: []
created: 2026-07-21
updated: 2026-07-21
tags: [source, arcaea, scoring]
aliases: ["Arcaea — Scoring"]
---

# Arcaea — Scoring

## Covers

Authoritative on how a play's judgement counts turn into a `score`, grade thresholds,
`clear_type`/`modifier` enums, gauge clear rules, the hard-gauge early-submit behavior, and
exactly what data each score path (own-credentials vs. friend) can show. Game domain only —
no bot behavior. Companion to `arcaea-domain-reference.md` (catalog) and `arcaea-potential.md`
(rating).

## Key claims

- `score = floor(10_000_000 * (pure + far/2) / note_count) + shiny_pure_count` — **FACT**,
  reproduced exactly against a captured own-credentials play (Vexaria FTR, 2026-07-17):
  pure=656 far=31 lost=47 shiny=602, note_count=734 → score 9,149,103, matching the observed
  value. Confirms `floor` (not round) and that shiny is additive *after* flooring. See [[scoring|Scoring]].
- Score is **lossy** — many (pure, far, lost, shiny) combinations map to one score; it cannot
  be inverted to recover a note breakdown. Structural reason the friend path can never show
  accuracy.
- `score: 0` is a valid, real result (all notes lost), not a "no data" sentinel — see
  [[d-score-zero-is-real]].
- Grade thresholds (EX+/EX/AA/A/B/C/D) are on score alone, independent of gauge/clear
  type/CC, and do **not** all align with the play-rating breakpoints in `arcaea-potential.md`
  (9.9M has no rating significance).
- `clear_type` and `modifier` (gauge) are **own-credentials only** — absent from friend scores.
  This is the root cause of [[d-r10-impossible-friend-path]].
- **OWNER-STATED (2026-07-17)**: a hard-gauge loss submits its score the instant HP hits 0 —
  seconds into a chart, not at song length. It is the only play that can appear in
  `recent_score` faster than a song's duration, and the only play excluded from the PTT
  recent-30 pool. See [[d-hard-gauge-early-submit]].
- Gauge never affects `score` — it only decides clear validity. Two identical scores are not
  comparable without `modifier`.

## Contradicts / reversed by

None against the other three sources in this slice. Confirms (does not merely repeat) the
hard-gauge-early-submit and r10-discriminator claims that `arcaea-potential.md` §3 also states —
both are consistent and cross-reference each other in the source text itself.

## Feeds

[[scoring|Scoring]], [[d-score-zero-is-real]], [[d-hard-gauge-early-submit]], [[d-r10-impossible-friend-path]]
