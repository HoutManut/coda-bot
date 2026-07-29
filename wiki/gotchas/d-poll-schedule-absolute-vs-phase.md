---
type: gotcha
status: active
severity: medium
area: scheduling
path: src/coda/scores/schedule.py
created: 2026-07-24
updated: 2026-07-24
tags: [gotcha, scores, polling]
aliases: ["PollSchedule._spread comparing by absolute due time instead of phase"]
---

# `PollSchedule._spread` must compare neighbours by phase, not absolute due time

## Symptom

No crash, no error. Each poll key's real period slowly grows past `POLL_INTERVAL` over
hours — polling frequency silently rots. Nothing in logs points at it; it only shows up
as accounts polling less often than configured.

## Cause

`reschedule` proposes a key's next due time as `now + interval * jitter` — always
roughly one full interval ahead of every other key's *pending* due time, since every key
polls once per interval and due times don't repeat within a window that short.

`_spread` (`schedule.py:92`) nudges the proposal toward the middle of the gap between its
neighbours, by comparing offsets. If those offsets are computed from **absolute** due
time (`due - proposal`), the proposal reads as later than almost every neighbour, every
time. The correction term then always pushes it later still — a one-directional bias.
Repeated over reschedules, every key's actual period walks past `POLL_INTERVAL` and never
converges back.

## The wrong fix

Comparing neighbours by raw `due` time:

```python
offsets = [due - proposal for other, due in self._due.items() if other != key]
```

Looks equivalent to the phase version, isn't — it drops the wraparound, so it keeps the
one-directional bias instead of fixing it. Easy to reintroduce during a "simplify this"
refactor since it reads as more direct.

## The right handling

Compare by **phase** — offset modulo the interval — so a neighbour's due time is treated
as recurring, not a one-off point in the future. `schedule.py:103-107`:

```python
offsets = [
    (due - proposal) % self._interval
    for other, due in self._due.items()
    if other != key
]
```

Correction then pulls the proposal toward the midpoint of the nearest phase gap
(`CORRECTION = 0.3`, capped well below 1.0 so it stays irregular rather than snapping to
an evenly-spaced lattice — see module docstring, `schedule.py:1-13`).

## Regression signal

Track a poll key's actual inter-poll gap over a long run (hours+); it should hover around
`POLL_INTERVAL` with jitter, not trend upward. A `_spread` diff that drops the `%
self._interval` on the offset computation is the tell — reject it on sight.
