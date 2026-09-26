---
type: flow
status: active        # active | partial | planned
entrypoint:           # command or task that starts it
touches: []           # modules
created:
updated:
tags: [flow]
---
# <Flow name,>

## Trigger

What starts it.

## Path

1. `module.function` — what happens, `file.py:line`
2. ...

## Failure modes

| Failure | Where it surfaces | User-visible result |
|---|---|---|

## Ordering constraints

Steps whose order is load-bearing, and what breaks if swapped.

## Related

`[[Module]]`, `[[Gotcha]]`
