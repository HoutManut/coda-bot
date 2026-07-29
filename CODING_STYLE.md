# Coding Style

Hard rules for writing code in this repo. No exceptions without a reason documented inline.

## Size & structure

| Rule | Notes |
|---|---|
| One responsibility per function | If you need "and" to describe what it does, split it |
| One responsibility per file | Group by feature (matches existing `src/coda/` package layout), not by layer-within-layer |
| No fixed line-count limit | Judge by responsibility, not line count — a 10-line function doing two things is worse than a 40-line function doing one |

## Comments & docstrings

| Rule | Notes |
|---|---|
| No inline comments explaining WHAT | Names should already say it |
| Inline comment only for non-obvious WHY | Hidden constraint, workaround, surprising invariant — same bar as global CLAUDE.md |
| Public functions/classes get a one-line docstring | Summary only |
| Add param/return docs only when the signature isn't self-explanatory | Non-obvious types, sentinel values, order-dependent args — see `dto/` sentinel handling for the kind of thing that qualifies |
| Never multi-paragraph docstrings | If it needs that much explaining, the design is the problem |

## Error handling & validation

| Rule | Notes |
|---|---|
| Validate at boundaries | User input, external API responses (lowiro), config/env loading |
| Trust internal calls | No re-validating what an internal caller already guarantees |
| Validate risky internals with real failure history | e.g. `dto/` parsing (`.get()` + explicit defaults, never bare `KeyError`) — see CLAUDE.md §Security for the specific sentinels |
| Fail loudly on unexpected external shapes | "lowiro changed the API", not a swallowed exception |
| No defensive code for scenarios that can't happen | Don't guard against states the type system or caller already rules out |

## Abstraction & DRY

| Rule | Notes |
|---|---|
| Extract on the 2nd duplication | Don't wait for a 3rd occurrence |
| No speculative abstraction | Don't build for a hypothetical future caller |
| Prefer the option where the problem dissolves | Over adding a layer to manage it — check if a boundary can just move instead of adding an abstraction on top |
| Delete, don't deprecate | No unused `_var` renames, no `# removed` comments, no back-compat shims for code only this repo calls |

## Naming

| Rule | Notes |
|---|---|
| PEP8 baseline | `snake_case` functions/vars, `PascalCase` classes, `UPPER_CASE` constants |
| Descriptive over short | No single-letter vars except loop counters/comprehensions; no unclear abbreviations |
| Use domain vocabulary, not wire vocabulary | e.g. pure/far/lost internally, not the API's perfect/near/miss — the DTO boundary is where translation happens, not before |

## Type hints

| Rule | Notes |
|---|---|
| Required on public/boundary code | Extension commands, service methods, DTOs, ORM `Mapped[...]` columns |
| Optional on internal helpers/scripts | Loosen where it's genuinely internal-only and typing adds no signal |
| No bare `dict`/`Any` where a real type exists | If a shape is known, name it |

## Testing

| Rule | Notes |
|---|---|
| No blanket coverage requirement | No test suite exists yet; don't block on backfilling old code |
| Required for high-risk logic | DTO sentinel parsing, level/rating encode-decode, score/rating math, friend-code validation — anything that regresses silently |
| Not required for simple CRUD / passthrough code | `uv run pytest`, single test via `uv run pytest path::test_name` |
