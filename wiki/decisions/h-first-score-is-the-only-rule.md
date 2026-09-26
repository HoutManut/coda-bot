---
type: decision
status: active
date: 2026-09-05
reverses: h-tournament-scoring-rule-parameter
created: 2026-09-05
updated: 2026-09-05
tags: [decision, tournaments, scoring]
aliases: ["First score counts; `best` mode is retired"]
---

# First score counts; `best` mode is retired

## Context

The first design pass ([[arcaea-tournament-layer]], carried into
[[handoff-13-tournaments|handoff 13]] decision 7) made the scoring rule a
**parameter**: `first` (default) or `best`, authored onto a match and copied
onto every round it spawns. Both shipped. `first` was the default everywhere and
the only value anything actually ran with.

`best` never paid for itself. It cost, in the shipped code:

- a `scoring_rule` enum type and a column on **two** tables
- a branch in the standings query (`ORDER BY score DESC` vs `time_played ASC`)
- two rule gates in the sweep — the early `open → grace` exit and the early end
  of grace — each of which had to explain in a comment why it was `first`-only
- a `rule:` option on `/tournament quick`, an entry in `options.RULE`, and a
  resolver branch in `defaults.py`
- a line on every board that read either "first score counts" or "best score
  counts"

and it owed, unbuilt: **a timing model of its own**. `WINDOW_SECONDS` is flat
because a `first` window ends the moment both sides have scored; a `best` window
runs its full 300 s, which on a long chart is one attempt and sometimes none —
the warning [[h-tournament-window-and-clock]] recorded and the owner accepted at
the 2026-09-03 spot check. `best` was a mode you could pick that behaved worse
than the default and had an open design question underneath it.

## Alternatives

| Option | Why not |
|---|---|
| Keep `best`, design its window | Buys a second timing model, a second set of board copy, and a second thing every future format has to be correct under — to offer a rule nobody asked for |
| Keep the column, hide the option | The column is the branch. Standings, the sweep and the board all still read it, so nothing simplifies and the dead value can still be written straight into the DB |
| Keep the enum with one member | An enum with one value is a column that can only say one thing. It is the parameter, minus the parameter |

## Decision

**A round counts each player's FIRST valid score inside the window. That is the
rule, not a setting.**

Removed outright: `ScoringRule`, `scoring_rule_type`, the `scoring_rule` column
on `tournament_matches` and `tournament_rounds` (migration
`d7b2f4c19e83`), `options.RULE`, `DEFAULT_RULE`, `Chosen.rule`,
`MatchOptions.scoring_rule`, `MatchView.scoring_rule`, and the `rule:` option on
`/tournament quick`. The board still prints "first score counts" — it changes
how you play, so [[tournaments|Tournaments]] §config requires it on the board —
but it is now a constant, not a rendered value.

`last`-counts remains unoffered, for the reason it always was: instant exit is
arbitrary and nobody asked for it.

## Consequences

- **The early exits stop being conditional.** `_maybe_close_window` and
  `_grace_over` end on `all_scored` with no rule gate, and `WINDOW_SECONDS`
  being flat needs no caveat: the window ends when both sides have scored, full
  stop.
- **The standings query has one `ORDER BY`.** `DISTINCT ON (account)` picks the
  earliest play, and a later play is never read whatever it scored. Pinned by
  `test_only_the_first_play_counts`.
- **[[h-tournament-attempt-overhead]] is moot.** It only ever mattered for
  sizing a `best` window. Attempt overhead may return as an input to
  [[h-tournament-quit-rerolls-first]], which is about `first` and still open.
- **The `best` half of [[h-every-valid-score-counts]] falls away.** A hard-gauge
  death is a real score under the only rule there is; there is no longer a mode
  where the question is inert.
- **Restoring it means restoring the timing model too.** The downgrade of
  `d7b2f4c19e83` recreates the column with every row reading `first`; it does
  not recreate a design for what `best` should do with a clock.

## Enforced at

`src/coda/tournaments/results.py` (one `ORDER BY`),
`src/coda/tournaments/service.py` (ungated early exits), and the absence of the
column — there is nothing left to set.
