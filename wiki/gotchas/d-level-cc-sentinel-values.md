---
type: gotcha
status: active
severity: high
area: catalog
verified:
created: 2026-07-21
updated: 2026-07-21
tags: [gotcha, catalog, sentinel]
aliases: ["Level/CC sentinel values (`0` = TBA, `-1` = err-only `?`) collide with \"missing\" decoding"]
---

# Level/CC sentinel values (`0` = TBA, `-1` = err-only `?`) collide with "missing" decoding

## Symptom

A chart's level renders as `-0.5` or `"level 0"` instead of `"?"`/`"TBA"`; a chart constant
renders as `-0.1` instead of `"?"`; or `err`-difficulty rows get treated as if they had a real
level/CC of `0` and sort into the catalog next to genuinely easy/low-CC charts.

## Cause

Both `level` and `rating` (chart constant, see [[catalog|Catalog]]) are stored as plain integers with
two **distinct** sentinel meanings sharing the same small-integer space as real data:

| Stored | Meaning |
|--------|---------|
| `-1`   | N/A — `err` difficulties only, displayed `"?"` |
| `0`    | TBA — chart exists, value not yet revealed, displayed `"TBA"` |
| `>0`   | Real value, decode normally |

A naive decode (`stored / 10.0` for CC, `stored // 2` / `stored % 2` for level) run without a
sentinel check first turns `-1` into `-0.1` or a nonsensical negative level, and silently treats
`0` as a real "level 0" or "CC 0.0" instead of "not yet revealed".

## The wrong fix

Treating `<= 0` as a single "unknown, skip it" bucket and short-circuiting before checking which
sentinel it is. This conflates two operationally different states: `0` (TBA) is a chart that
**will** get a value and should show as pending; `-1` (err-only `?`) is a chart that **never**
will, and only ever appears on `err` rows. Code that branches on `<= 0` without also checking
`== -1` vs `== 0` separately will render the wrong placeholder for one of the two cases the
moment they diverge (e.g. a future feature that lists "upcoming CC reveals" — that must include
`0`-sentinel rows and must exclude `-1`-sentinel `err` rows, and a merged `<=0` check cannot
distinguish them).

## The right handling

Check the sentinel **before** applying the arithmetic decode, and branch on the exact value:

```
if stored == -1: display "?"      # err-only
elif stored == 0: display "TBA"   # not yet revealed
else: display decode(stored)      # real value
```

For play-rating purposes specifically, `rating <= 0` (both sentinels) collapses to "no computable
play rating" — see [[d-unknown-cc-no-play-rating]] for why that merge is *correct* in that one
context but must not be generalized to every consumer of the field.

## Regression signal

A catalog listing or `/song` embed showing a negative level/CC, or an `err` chart appearing in a
"charts with unrevealed level" filter meant only for `0`-sentinel rows.
