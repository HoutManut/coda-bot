---
type: decision
status: active
date:
reverses:
created: 2026-07-21
updated: 2026-07-21
tags: [decision, db, orm, sqlalchemy]
aliases: ["No `relationship()` anywhere in the ORM — joins are written explicitly"]
---

# No `relationship()` anywhere in the ORM — joins are written explicitly

## Context

SQLAlchemy's declarative ORM offers `relationship()` for navigable
object-graph traversal (`song.difficulties`, `account.play_scores`, etc.).
This project's schema has plenty of natural relationships — `songs` →
`song_difficulties`, `arcaea_accounts` → `play_scores`, `player_links` →
`arcaea_accounts` — that would be candidates.

## Alternatives

| Option | Why not |
|---|---|
| `relationship()` with default lazy-loading | Async SQLAlchemy's lazy-load story is a known footgun (implicit I/O inside attribute access, easy to trigger outside an active session/event loop context); also hides the exact query being run behind attribute access. |
| `relationship()` with everything eager-loaded (`selectin`/`joined`) | Fetches data services rarely need on every read; the catalog's inheritance model (`COALESCE(difficulty.field, song.field)`) and score queries (`play_scores` filtered/joined per use case, e.g. b30's `DISTINCT ON` narrowing) are use-case-specific enough that a generic eager load either over-fetches or gets bypassed anyway. |

## Decision

Every model subclasses one shared `Base` (`src/coda/db/base.py`) and no model
anywhere declares `relationship()` — confirmed by source read
(`grep -rn "relationship(" src/coda/db/` returns nothing). Every join a
service needs is written explicitly at the call site with `select(...).
join(...)`, as seen throughout `src/coda/players/service.py` (e.g.
`current_account`'s explicit `join(PlayerLink, PlayerLink.arcaea_account_id
== ArcaeaAccount.id)`).

## Consequences

- Every cross-table read states exactly what it fetches and how — no hidden
  N+1 query behind an attribute access, and no query plan surprises from an
  eager-load strategy chosen once at model-definition time but wrong for a
  specific call site.
- Some duplication is inevitable: multiple services write their own version
  of "join `PlayerLink` to `ArcaeaAccount`" rather than sharing one
  `relationship()`-backed accessor. Accepted cost, not an oversight.
- Any future model addition should not introduce `relationship()` without
  reopening this decision — it would be an inconsistency, not a neutral
  choice, given every existing model deliberately avoids it.

## Enforced at

No enforcement mechanism beyond convention — verified by absence
(`grep -rn "relationship(" src/coda/db/`), not by a lint rule. Alembic itself
does not care either way; this is a service-layer discipline choice, visible
throughout `src/coda/players/service.py`, `src/coda/scores/` (referenced,
not read in this ingest), and every model file under `src/coda/db/models/`.
