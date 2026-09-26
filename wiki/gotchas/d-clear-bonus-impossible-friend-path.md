---
type: gotcha
status: active
severity: high
area: wire
verified: 2026-08-31
created: 2026-08-31
updated: 2026-08-31
tags: [gotcha, potential, ptt, wire, 7.0]
aliases: ["the 7.0 clear bonus cannot be reconstructed on the friend path — even approximately. the base formula can."]
---

# The 7.0 clear bonus cannot be reconstructed on the friend path — even approximately. The base formula can.

## Symptom

A tier-1 (friend-path-only) registered player's stored best-50/PTT figure quietly diverges from
the game's own value, in a way that isn't explained by "we haven't seen every play yet" — the
tracker is computing a different play-rating formula for every one of that player's rows, not
merely lagging on which plays it has seen. It can also silently pick the *wrong* play as a
chart's best entry, not just attach the wrong number to the right one.

## Cause

The 7.0 play-rating formula needs `clear_type` to apply the flat `+0.2` clear bonus (see
[[potential|Potential]] §Encoding, magnitude confirmed 2026-08-31). `clear_type` is
own-credentials only: `ScoreResult.clear_type` is `None` on every row `from_friend_wire`
produces (`src/coda/arcaea/dto/score.py:64`), by construction of the endpoint, not a modeling
gap — the module's own docstring already states extras are "absent on the friend path as a
property of *the endpoint*, not of the user." A tier-1 player's stored `play_scores` rows are all
`from_friend_wire`-sourced, so every one of that player's rows has `clear_type = None` — there is
no per-row signal, present or absent, that tells a `TRACK_LOST` apart from a `PURE_MEMORY` at the
same score.

Confirmed at the wire level, not just inferred: a live capture of `GET /webapi/friend/me`
(2026-08-31, `new_friend_res.json`, 20 friends) shows every `recent_score` entry as the plain
5-field shape (`song_id`, `difficulty`, `score`, `time_played`, title) — no `clear_type`, no
`modifier`, on any of the 20 (see [[h-7.0-clear-bonus-investigation-plan]] Phase 4). Structurally
identical to the gap that made r10 impossible on the friend path (see
[[d-r10-impossible-friend-path]], now historical alongside r10 itself) — a different mechanic (a
per-entry additive bonus instead of an asymmetric admission rule), the same "own-credentials-only
field the friend path structurally cannot see" shape.

Two consequences beyond "the aggregate PTT is off by up to 0.2 per unresolved chart":

- **Which play is "best" for a chart can flip.** Best-50 ranks per chart by `rating`, and the
  bonus can make a lower-score cleared play outrank a higher-score uncleared one on the same
  chart. Comparing bare scores on the friend path can pick the wrong play as the chart's entry,
  not just compute a slightly-wrong rating for the right one.
- **Pool membership itself can flip**, not just the number attached to an entry already in the
  pool — a chart sitting near the best-50 or top-10 cutoff can be in or out depending on a bonus
  the friend path cannot see.

## The wrong fix

Approximating the bonus on tier-1 rows — e.g. assuming every stored friend-path play "counts as
cleared" (`+0.2` unconditionally) because most submitted plays are clears, or backing it out from
score bands the way a naive friend-path r10 once assumed a score threshold could stand in for the
hard-gauge check. Either guess is *wrong on data the tracker did see*, not merely behind on data
it hasn't — the same category of error [[d-r10-impossible-friend-path]] ruled out, for the exact
same reason.

## The right handling

Same principle the project already settled for r10: an own-credentials-only field must not be
approximated on the friend path by *guessing at the field itself*. Best-50 differs from r10 in one
load-bearing way, though: r10's *admission rule itself* was asymmetric and unrecoverable without
`clear_type`+`modifier`, so there was no safe partial computation and the only sound move was to
drop r10 entirely on tier 1. Best-50's per-chart ranking is still well-defined from `score` alone,
and the failure mode of guessing wrong is bounded (one chart's bonus, not a whole admission rule)
— which opens a second option r10 never had: infer the field from a score threshold, disclose the
inference honestly, and let the player it's about correct it.

**Ruling (revised 2026-08-31, supersedes the same-day baseline-only draft below):** a tier-1 row's
clear status defaults to a score-threshold heuristic — **assumed cleared at `score >= 9,000,000`,
assumed not cleared below it** — rather than always omitting the bonus. The threshold is
deliberately conservative, set lower than the ~9.3–9.4M band where genuine fails mostly stop
appearing in practice (owner observation against a live `best_rated_scores` capture where 0 of 50
pool entries were non-clears), so the common case in an actual best-50 pool resolves correctly by
default instead of every pool entry reading ~0.2 low.

The heuristic is a display default, not a claim of fact, and the row's owner can override it:
`PlayScore.clear_override: bool | None`, nullable, **per stored row, not sticky per chart** — a
later, better play on the same chart carries no override of its own and falls back to the
heuristic, the same way `best_play` (`src/coda/scores/best.py`) already re-picks per row rather
than per chart. `None` uses the heuristic; `True`/`False` is an explicit correction by the account
owner. Only meaningful when `clear_type is None` (tier-1) — a tier-2+ row's `clear_type` is
wire-known, so an override control shouldn't even render for it.

**Not a toggle on every `/score` lookup** (owner, 2026-08-31, rejected as UI clutter — most rows
never need correcting, so a control on every row asks the wrong ratio of questions to answers).
Instead a filtered review queue, scoped to rows that are tier-1, currently the chart's
resolved-best entry, currently inside the counted pool, and unconfirmed — and **pull-only**, no
passive hint on the aggregate embed pointing at it. Surface design (command placement, row layout,
re-render-on-cascade behavior) is deferred — see [[h-clear-override-review-queue]].

The per-chart "best play" comparison must resolve to the *same* value (heuristic or override) that
the rating calc uses, so ranking stays internally coherent even where the heuristic guesses wrong.
Concretely, this rules out reusing a raw `ORDER BY score DESC LIMIT 1` query (what
`best_play` in `src/coda/scores/best.py` does today, correctly, for the pre-bonus/no-rating
`/score` path) for anything that feeds the rating calc: a higher-scoring row that the heuristic
wrongly assumes clear can outrank a lower-scoring row that is a *real* clear, by more than the
bonus alone would ever explain, because the false-positive assumption stacks on top of an already
higher score. Worked example: chart scored 9,900,000 (an actual fail) and 9,890,000 (an actual
clear) — true rating favors the clear (`+1.45+0.2=1.65` vs `+1.5`), but the heuristic assumes both
rows clear (both `>= 9,000,000`), so the higher raw score wins selection (`+1.7` vs `+1.65`) and
the real clear is never selected as the chart's entry, not merely mis-rated. The rating path must
therefore evaluate resolved rating (heuristic/override applied) across *every* stored row for the
chart, not just the top-scoring one, and re-evaluate after any override change — flipping one row's
override must be able to promote a different, previously-buried row into the winning slot, the same
way `_render_chart` already recomputes from source on every interaction rather than caching a
selection. Presentation must always disclose which of the three states applied — wire-confirmed /
assumed-clear / owner-marked — never blend them into one number silently, the same standard
chart rendering already holds to for spoilered state
(see [[h-spoiler-is-a-render-mode|Spoiler decision]]).

**Enforced in code since 2026-08-31** (see [[potential|Potential]] §Implementation status).
`utils/scoring.py::resolve_clear` implements the precedence (wire `clear_type` → owner
`clear_override` → the `>= 9,000,000` heuristic) and is the only place that decides it;
`play_scores.clear_override` is the nullable per-row column; `scores/potential.py` picks each
chart's entry by resolved rating over every stored row, which is the part the worked example
above exists to protect.

**Disclosure is by absence, decided 2026-08-31** (owner, superseding the same-day three-mark
draft): only `ClearBasis.ASSUMED` is marked, with a `~` *prefixed* to the figure
(`utils/scoring.py::ASSUMED_MARK`). Wire-confirmed and owner-marked both go unmarked, because both
are statements of fact — one by lowiro, one by the account's owner — and the earlier `*` for an
override made the mark fire on every state a tier-1 row could be in, which discriminates nothing.
Unmarked now means "known", and the marked rows are exactly the review queue. This satisfies the
"never blend them into one number silently" standard: the three states still resolve separately,
but the display collapses the two *settled* ones, which is a different thing from blending a guess
into a fact. `chart_rating_line` and `potential_stat_line` (via `PotentialResult.assumed_count`)
both apply it. `tests/test_potential.py` pins the worked example, including that flipping an
override promotes the previously-buried row, plus the queue filter itself.

**The setting surface shipped 2026-08-31**: `/potential` → *Review N assumed*, built as designed in
[[h-clear-override-review-queue]] (now closed). `scores/clears.py` is the only module that writes
`clear_override`.

**Earlier draft (2026-08-31, superseded same day):** the first pass at this ruling was
base-formula-only (bonus always omitted), rendered labeled as a lower bound. Reconsidered once
data showed the "lower bound" framing understated the actual problem: for a real best-50 pool the
omitted bonus isn't slack near a boundary, it's a near-fixed ~0.2 systematic *underestimate* on
nearly every counted slot, because a chart good enough to be in someone's best-50 is overwhelmingly
likely to be a clear too. An unconditional "assume clear" default was rejected in turn for the
opposite reason — guessing a field from popularity alone ("most plays are clears") is the same
category of error the r10 page already ruled out. The threshold + override design above keeps the
"don't guess the field outright" spirit while fixing the systematic-bias problem: infer from a
field the friend path *does* have (`score`), disclose the inference, and let the owner correct it
— no guess is left unlabeled or final.

## Regression signal

A best-50/PTT value rendered for a player known to be tier-1 (friend-path only, no linked
credentials) once best-50 exists in code, shown without disclosing which rows are assumed vs.
owner-marked vs. wire-confirmed; a `clear_override` set by the row's owner silently ignored by the
rating calc; a support report of "my potential shows something the game doesn't" that traces back
to a tier-1-sourced `play_scores` row with `clear_type = None`.
