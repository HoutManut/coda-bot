---
type: decision
status: active
date: 2026-07-28
reverses:
created: 2026-07-28
updated: 2026-07-28
tags: [decision, settings, config, discord, surface]
aliases: ["A config key declares its own audience; every user-facing picker filters on it"]
---

# A config key declares its own audience; every user-facing picker filters on it

## Context

`/config` grew four scope subcommands plus a `view`, each carrying a `key` option built from
`REGISTRY` at import time (`src/coda/extensions/config.py:21-25`). Four of those five lists
filter by `settable_scopes`, which reads like a permission filter but is not one — it answers
*where can this be written*, never *who should see that it exists*.

The fifth does not filter at all:

```python
_KEYS_VIEW = [lightbulb.Choice(name="all", value="all")] + [lightbulb.Choice(name=k, value=k) for k in REGISTRY]
```

and `ConfigView` has no permission check on the handler either. So every user opening
`/config view` reads a picker containing `chardle_debug_board`, `chardle_epoch`,
`chardle_abandon_hours`, `polling` — bot-wide operational knobs, named in internal snake_case,
several of which describe the internals of an unshipped feature. The picker is a schema dump.

The trigger was a plan to delete `/config global` because it clutters the suggestion list and
leaks internal parameter names. It does clutter, and it does leak — but deleting it closes
neither problem, because `view` leaks the same names to a strictly larger audience and is not
owner-gated at all. A per-command fix would have to be repeated at every future call site and
would be forgotten at the first new one.

## Alternatives

| Option | Why not |
|---|---|
| Delete `ConfigGlobal`, leave the rest | Does not reach the stated goal. `_KEYS_VIEW` still enumerates every key for every user, and `ConfigView` still has no gate. |
| Derive audience from the scope chains — "GLOBAL-only means owner-only" | Implicit, and wrong at the edges. `polling` is GLOBAL-only and is exactly the sort of key a user may legitimately read; a future user-audience key could be GLOBAL-only too. Encoding one property in another means the day they diverge, nothing says so. |
| A second `OWNER_REGISTRY` dict | Hardest to leak, but `resolve`, `set_value`, `get_at_scope` and `all_at_scope` all grow a "which registry" branch, and a key can never change audience without moving between dicts. Cost falls on every consumer to protect one presentation concern. |
| Gate at the command layer, per command | This is the status quo that produced the bug: four call sites filtered, one did not, and nothing detects the fifth. |

## Decision

`ConfigKey` carries its own audience.

```python
@dataclass(frozen=True)
class ConfigKey:
    name: str
    default: Any
    type: Literal["str", "bool", "int"] | tuple[str, ...]
    guild_chain: tuple[Scope, ...]
    dm_chain: tuple[Scope, ...]
    description: str = field(default="")
    audience: Literal["user", "owner"] = "user"
```

Two rules follow, and both are checkable by reading the file:

1. **Every user-facing choice list, autocomplete callback, and rendered listing filters on
   `audience == "user"`.** No exceptions, including `view`, including `all_at_scope`
   renderings. If a comprehension over `REGISTRY` reaches a user's screen and does not carry
   that predicate, it is a bug.
2. **`audience="owner"` keys are reachable only from the owner surface**
   ([[h-owner-surface-is-run-terminal]]). The owner surface sees the whole registry
   unfiltered — that is its purpose.

Audience is about *visibility*, `settable_scopes` is about *writability*. They are independent
and a key may need both stated. A user-audience key can still be GLOBAL-only (a user reads the
bot-wide value of `polling` and cannot change it); an owner-audience key can still be
per-guild.

The default is `"user"`, deliberately. A new key is visible unless someone thought about it —
the failure mode of forgetting is a slightly noisy picker, not a silent gate. The opposite
default hides keys nobody meant to hide and is discovered as "why can't I set my locale".

This generalizes past settings: **internal-ness is a property of the definition, not a check
at each call site.** Same shape as the gate-on-the-service-not-the-command rule, one layer further down —
that rule moved gates off the command onto the service, this moves them off the service onto
the data.

## Consequences

- Adding a config key now requires one more judgement: who is this for. Cheap, and the
  `description` field already forces the author to think about the reader.
- `_KEYS_VIEW` stops being the "everything" list, so a user who *knows* an internal key name
  can still type it as free text into an autocomplete option. That is fine and expected —
  audience hides names, it does not authorize writes. The write path is still guarded by
  `settable_scopes` plus the owner check. See [[d-autocomplete-is-a-hint]].
- The registry becomes the single place to audit "what do users see", which is the property
  that makes this worth doing at all.
- Anything that renders `all_at_scope` output to a user must filter too — that dict comes back
  keyed by whatever is in the DB, not by `REGISTRY`, so a stale owner key written before this
  landed will still surface. Filter the render, not the query.

## Enforced at

**Built 2026-07-28.**

- `src/coda/settings/types.py` — `audience: Literal["user", "owner"] = "user"` on `ConfigKey`.
- `src/coda/settings/registry.py` — `user_keys()`, the single filter. Every user-facing list
  in `extensions/config.py` is built from it, including `_KEYS_VIEW`, `ConfigView`'s
  `keys_to_show`, and `_handle`'s `all_at_scope` render (filtered on the render, not the
  query — the query returns whatever is in the DB).
- Six keys are `audience="owner"`: `polling`, `chardle_epoch`, `chardle_debug_board`,
  `chardle_bpm_window`, `chardle_note_window`, `chardle_abandon_hours`. The owner's call,
  2026-07-28: **none** of them surfaces to users, including `polling` — the decision permits a
  user-audience GLOBAL-only key, and none was wanted. If the bot-wide state of polling should
  be visible, it gets its own command, not a picker entry.
- The user-audience keys are `recent_b30_stat` and `timezone`. (`locale` was a third
  until 2026-07-28, when it was deleted: Discord's `interaction.locale` already carries
  it — see [[live-updates]] §12.)
- `/config view` labels a value inherited from `Scope.GLOBAL` as *"from default"* in the
  neutral colour, never "from global" — the scope has no user-facing name and nothing on that
  surface can write it. `_SCOPE_COLOR/_LABEL/_TITLE[GLOBAL]` are deleted.

Also fixed on the way, from [[h-run-terminal-build-time]] item 2: `parse_value(defn, raw)`
(`settings/parse.py`) is called by **both** write paths, so an int key can no longer be stored
as a string. No such rows existed in the dev database, so nothing needed migrating.
