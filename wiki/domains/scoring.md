---
type: domain
status: active
source: arcaea-scoring.md
verified: 2026-07-17
created: 2026-07-21
updated: 2026-07-21
tags: [domain, arcaea, scoring]
---

# Scoring

## Model

Every note in a chart resolves to one of three judgements. **This project uses the in-game
terms internally — pure / far / lost.** The lowiro API uses `perfect`/`near`/`miss`; translate
at the DTO boundary in `src/coda/arcaea/` and never let the wire names leak past it.

| In-game term | API field       | Score weight    |
|--------------|-----------------|------------------|
| Pure         | `perfect_count` | full             |
| Far          | `near_count`    | 50% of a pure    |
| Lost         | `miss_count`    | 0                |

A **shiny pure** (`shiny_perfect_count`) is a pure hit in the tighter inner window — a
**subset** of pures (`pure_count >= shiny_pure_count` always), not a fourth judgement. It earns
full pure weight plus exactly 1 extra point.

```
pure_count + far_count + lost_count == chart note count
```

## Encoding

### Score formula

```
base  = floor(10_000_000 * (pure_count + far_count / 2) / note_count)
score = base + shiny_pure_count
```

- All non-shiny pures → exactly `10,000,000`.
- MAX (every note shiny) → `10,000,000 + note_count`.
- Minimum → `0` (all lost).
- Score is an **8-digit** value. `note_count` comes from `song_difficulties.note` — never
  derivable from the score itself (see [[Score Mapping]] §5).

**Verified against a captured own-credentials play** (Vexaria FTR, 2026-07-17):
`pure=656 far=31 lost=47 shiny=602`, `note_count=734` →
`base = floor(10_000_000 * (656 + 15.5) / 734) = 9_148_501` → `score = 9_148_501 + 602 =
9_149_103`, matching the observed value exactly. Confirms `floor` (not round), and shiny
additive **after** flooring.

Score is **lossy** — many `(pure, far, lost, shiny)` combinations map to the same score; it
cannot be inverted to recover a breakdown. This is why the friend path can never show accuracy:
it returns `score` and nothing else about the play.

### Grades

Thresholds on score alone, independent of gauge/clear type/CC:

| Grade | Score |
|-------|-------|
| EX+   | ≥ 9,900,000 |
| EX    | ≥ 9,800,000 |
| AA    | ≥ 9,500,000 |
| A     | ≥ 9,200,000 |
| B     | ≥ 8,900,000 |
| C     | ≥ 8,600,000 |
| D     | below 8,600,000 |

Grade boundaries do **not** all line up with the play-rating breakpoints (9.8M and 10M — see
[[Potential]] §Encoding). EX at 9.8M is shared; EX+ at 9.9M has no rating significance.

### Clear types

`clear_type` (this attempt) / `best_clear_type` (best ever). **Own-credentials only — absent
from friend scores.**

| Value | Name        | Meaning |
|-------|-------------|---------|
| `-1`  | unknown     | App sentinel — not a wire value |
| `0`   | track_lost  | Failed the chart |
| `1`   | clear       | Complete on normal gauge |
| `2`   | full_recall | No lost notes |
| `3`   | pure_memory | All pures (no far, no lost) |
| `4`   | easy_clear  | Cleared on easy gauge |
| `5`   | hard_clear  | Cleared on hard gauge |

### Gauge modifier

`modifier` records the gauge used. **Own-credentials only.**

| Value | Name    |
|-------|---------|
| `-1`  | unknown (app sentinel) |
| `0`   | normal  |
| `1`   | easy    |
| `2`   | hard    |

`health` is HP at the end of the play. Clear rule of thumb (not a validation rule — server
`clear_type` is authoritative, partner-specific gauge variants can legitimately violate this):
easy/normal clear needs `health >= 70` at the end; hard clear needs any `health > 0` at the end,
because reaching 0 ends the play immediately.

**Gauge never affects `score`** — score is pure/far/lost arithmetic only (§Score formula).
`modifier` is about clear validity, not scoring. Two identical scores are not comparable without
`modifier`.

### What each path can show

| Data                       | Own credentials | Friend |
|-----------------------------|:---:|:---:|
| `score`                     | yes | yes |
| Grade (derived from score)  | yes | yes |
| Pure / far / lost / shiny   | yes | **no** |
| Clear type                  | yes | **no** |
| Gauge, HP                   | yes | **no** |

A friend-path 9,872,937 could be a clean run or a near-fail scrape — indistinguishable. Product
constraint, not an implementation gap.

## Traps

- **`score: 0` is a real score** (all notes lost) — not a missing/null sentinel. See
  [[d-score-zero-is-real]].
- **A hard-gauge loss submits early** — HP hitting 0 ends the play instantly and the score
  submits then, seconds into the chart, not at song length. It's the only sub-song-length score,
  and the only play excluded from the PTT recent-30 pool (discriminator `clear_type==0` **AND**
  `modifier==2`, never `clear_type==0` alone). See [[d-hard-gauge-early-submit]] and
  [[Potential]] §Traps.
- **Both `clear_type` and `modifier` are own-credentials only** — the friend path cannot
  identify a hard-gauge loss or any other clear/gauge detail at all, which is what makes r10
  reconstruction impossible on that path. See [[d-r10-impossible-friend-path]].
- Do not conflate `clear_type == 0` (track_lost, any gauge) with the hard-gauge-only recent-30
  exclusion — a full-length normal/easy-gauge track lost still enters the pool normally.

## Source

[[arcaea-scoring]] — authoritative and more detailed than this page. See
[[arcaea-scoring]] (source page).
