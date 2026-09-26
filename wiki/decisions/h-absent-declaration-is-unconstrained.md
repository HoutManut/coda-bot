---
type: decision
status: active
date: 2026-09-06
reverses:
created: 2026-09-06
updated: 2026-09-06
tags: [decision, ownership, tournaments, catalog]
aliases: ["A player who never declared is unconstrained, not empty-handed"]
---

# An absent ownership declaration means unconstrained, never "owns nothing"

## Context

`/owned` is opt-in, and on the day it shipped every account had zero rows. The
tournament pool filter ([[tournaments|Tournaments]] §pool, `pool.owned_by_all`)
intersects the roster's playable sets, so it has to answer a question the
storage cannot: is an account with no rows a player who owns nothing, or a
player who has not been asked?

This is the same shape as the wire finding in [[catalog|Catalog]] §Ownership —
**neither `packs` nor `world_songs` may be read as a denial** — one level up,
applied to our own table instead of lowiro's arrays.

## Alternatives

| Option | Why not |
|---|---|
| Empty set = owns nothing | Intersecting it empties every pool that contains one undeclared participant, which on day one is every pool. The failure is total and looks like a broken command, not like missing data. |
| Refuse to open a match until everyone has declared | Turns a nice-to-have into a hard gate on the feature people actually came for, to buy precision nobody asked for. |
| A `declared_at` column to tell the two apart | A third state to keep in sync with the rows, for a distinction whose safe answer is the same either way: a player who declares literally nothing owns `base` at minimum, so "declared nothing" is not a real position. |

## Decision

`playable_chart_ids` returns **`None`** — not `set()` — for an account with no
`owned_charts` rows, and every reader treats `None` as *contributes no
constraint*. `owned_by_all` skips those accounts entirely and returns the
unfiltered chart list when the whole roster is undeclared.

Declared-ness is therefore derived from row presence alone, with no flag column.
The two indistinguishable cases — never asked, and asked but cleared — collapse
into the same safe answer, which is why the distinction is not worth storing.

`clear_all` deliberately returns an account **to** unconstrained rather than to
"owns nothing", so undoing a declaration can never be worse than never making
one.

## Consequences

- The filter's precision rises with adoption instead of gating on it. One
  declared participant already narrows a pool; the rest are simply not asked.
- **A false negative is the cheap error here and a false positive is not**, which
  is also why a pack tick never grants Beyond (see
  [[ownership-module|ownership]]): a pool missing a chart costs one absent
  option, a pool containing an unplayable one costs the match.
- `has_score` is unioned in for the same reason — a chart the account has
  actually played is playable whatever was declared, so the filter can never
  exclude something demonstrably reachable.
- Any future reader of ownership must handle `None` explicitly. A reader that
  does `playable_chart_ids(...) or set()` reintroduces exactly the bug this
  decision exists to prevent.

## Enforced at

`src/coda/ownership/service.py::playable_chart_ids` (returns `None`) ·
`src/coda/tournaments/pool.py::owned_by_all` (skips `None`) ·
`tests/test_ownership.py::test_no_declaration_reads_as_unconstrained`,
`::test_clearing_returns_to_unconstrained`
