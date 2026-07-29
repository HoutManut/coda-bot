---
type: decision
status: active
date: 2026-07-28
reverses:
created: 2026-07-28
updated: 2026-07-28
tags: [decision, discord, surface, owner, config, run]
aliases: ["Owner-only operations live behind one `/run` terminal, not behind owner-gated slash options"]
---

# Owner-only operations live behind one `/run` terminal, not behind owner-gated slash options

## Context

Discord's command surface is a menu, and the menu is public. Every option name, every choice
list, every subcommand description is readable by anyone who can type `/`. Nothing about
"this handler checks `config.owner_ids`" removes an entry from that menu, or removes the
option names underneath it.

So each owner-only capability added as a slash subcommand costs twice: a row of clutter in
everyone's picker, and a published list of internal parameter names. `/config global` is the
current instance — `_KEYS_GLOBAL` (`src/coda/extensions/config.py:24`) advertises
`chardle_debug_board`, `chardle_epoch`, `polling` to a picker where the only person who can
act on any of them is the owner. Owner operations are also the fastest-growing category —
session pool inspection, poll-loop nudges, reconcile triggers, cache dumps — and each one
added the same way widens the leak and the clutter together.

A separate discoverable command per owner operation is the wrong shape: discoverability is
worthless for an audience of one who wrote them.

## Alternatives

| Option | Why not |
|---|---|
| Keep owner subcommands, gate the handler | Status quo. Handler gates control *action*, never *visibility*; the leak and the clutter are both presentation-layer and survive untouched. |
| Keep owner subcommands, hide with `default_member_permissions` | Hides from non-admins only. Server Administrator ≠ bot owner, so every admin of every guild still reads the option names, and the clutter persists for exactly the people most likely to poke at it. Still needed as one layer — see below — just not sufficient alone. |
| A separate owner-only bot | Two tokens, two deploys, two session pools, and cross-process access to the same DB and the same live poll loop. Cost enormously out of proportion to a bot with fewer than 50 users. |
| Admin web UI (`src/coda/admin/`) grows an ops page | Real option, and the catalog editor is already there. But it is a separate process the owner is not usually running, and the operations wanted here are moment-to-moment ("is the poller alive", "flip debug board") while sitting in Discord. Non-exclusive: nothing here forbids the admin app growing an ops page later. |
| `/run` with structured options (`/run verb:<x> args:<y>`) | Half-measure. The option names are back in the menu, and the verb list is back in a choice array. |

## Decision

One top-level command, `/run`, taking exactly one free-text string option and nothing else.
Suggestions come from a dynamic autocomplete that gates on the invoker. To everyone else it is
a single opaque row with one nameless-looking box; to the owner it behaves like a terminal
line.

### The gate is three layers, and all three are required

| Layer | Where | What it buys | What it does not buy |
|---|---|---|---|
| **Autocomplete callback** | the `_ac_*` function returns `[]` when `ctx.user.id not in config.owner_ids` | Closes the leak. Without it a non-owner types `/run ` and reads the same internal names the whole change was meant to hide. | Nothing about authority — autocomplete never executes. |
| **Invoke handler** | `if ctx.user.id not in config.owner_ids: refuse` | The actual authority check. The only one that matters for correctness. | Nothing about visibility. |
| **Registration** | `default_member_permissions=hikari.Permissions.NONE` on the command | Removes the row from the picker for non-admins. | Guild admins still see it, and Discord's own docs treat this as a default a guild may override. Never the authority check. |

Layer 1 is the one that gets forgotten, because it is not a security control in the usual
sense and nothing fails without it. It is the entire point of the change.

Confirmed available in the pinned lightbulb: `commands.py:88` exposes
`default_member_permissions`, alongside `contexts` and `integration_types`.
**`commands.py:190` rejects it on subcommands** — top-level only. That is a hard constraint,
not a preference: `/run` must stay a flat command and can never become a `lightbulb.Group`.

### The grammar is verb-first and space-separated

```
/run config set chardle_epoch 2026-07-27
/run config get polling
/run config reset chardle_debug_board
/run session list
```

**There is no scope token, because `/run config` is bot-wide config and nothing else.** Every
`set` and `reset` writes `Scope.GLOBAL` at `GLOBAL_SCOPE_ID`; `get` reads the raw value stored
there, alongside the registry default. Per-scope writes stay on `/config user|channel|server`,
and "what actually applies in this context" stays on `/config view` — that is `resolve()`, a
different question, and one verb name must not mean both. This is what `/config global` did,
carried over unchanged; the terminal replaces its *surface*, not its semantics.

Parsed with `shlex.split` into tokens, dispatched through a flat table, one small handler per
verb. Three reasons this shape and not another:

- Short tokens keep autocomplete usable. Completions are bounded at 100 characters
  ([[d-autocomplete-is-a-hint]]) and a flag-heavy or `key=value`-with-long-names grammar
  spends that budget on syntax.
- The table is extensible to non-config verbs without touching the command definition —
  which is the whole reason `/run` exists rather than `/config-owner`.
- One handler per verb keeps each one small, per `CODING_STYLE.md`.

There is **no shell state**. Discord slash commands are one-shot: no history, no working
directory, no pipes, no variables, no multi-line. "Terminal" is a description of how the input
box feels, not a promise of a REPL. Anything in the design that needs state between
invocations is not `/run`-shaped and belongs elsewhere. Every response is ephemeral.

`shlex.split` raises `ValueError` on an unbalanced quote, and the autocomplete callback sees
half-typed lines constantly — `config set x "half` is a normal keystroke, not an error case.
Both the callback and the handler catch it: the callback returns `[]`, the handler says what
broke. An uncaught parse error in the callback is indistinguishable from "no suggestions".

### `help` is a required verb, not a nicety

Named slash options carry descriptions; Discord renders them in the picker, and that is the
only documentation a slash command has. A single free-text option throws all of it away — for
the owner too. So `/run help` (lists verbs) and `/run <verb> help` (lists that verb's grammar)
ship with the first verb, and the autocomplete callback offers the verb list when the line is
empty. Skipping this trades a leak for an interface nobody can remember in three weeks.

### What may live behind `/run`, and what may not

Both halves bind:

- **Internals only.** Anything whose interface names a registry key, a `Scope` enum value, a
  DB column, a raw snowflake, a `bot_account_id`, or a `song_difficulty_id` belongs here and
  nowhere else.
- **Conversely: if users need it, it gets a real command.** `/run` is not a place to park a
  feature to skip designing its UX. The moment a non-owner would reasonably want an operation,
  it needs a discoverable slash command with named options — the thing `/run` exists to stop
  polluting. This half is what keeps the terminal from becoming a dumping ground.

### Output is per-verb, never a generic dump

Each verb formats its own reply. No `repr()` of a model, no `dict` splat, no "print whatever
the service returned". A generic formatter is how a `sid` reaches a Discord message the first
time someone adds a session-inspection verb — [[w-sid-confined-to-sessions]] is a layering
rule that a debug dump silently defeats. Same for encrypted credentials, Fernet material, and
lowiro tokens: they have no rendering, so no verb may have a path that stringifies an object
holding them.

Replies assert only what actually holds — a verb reports what it did, not what it attempted.

### Destructive verbs confirm; reads do not

Reset, wipe, purge, force-anything return an ephemeral confirm button before acting. The
pattern already exists at `src/coda/extensions/config.py:63` (`_make_reset_menu`, with its
`mctx.user.id != caller_id` guard). Reads and ordinary sets stay one-shot — a confirm on every
line makes the terminal unusable and trains the reflex that defeats the confirm on the one
line that mattered.

This is a deliberate narrowing of the dev-stage destructive-is-fine stance: it governs
*this repo's development* (drop the table, re-seed), not *a Discord button that fires against
the live DB from a phone*.

### Every invocation is audited — to file, never to the Discord log channel

Actor id and the raw submitted line, through `coda/logging/`, before dispatch — including
lines that fail to parse and lines refused by the owner gate. A refused line is the more
interesting log entry of the two.

**The audit record must carry `extra={"discord": False}`.** `DiscordChannelHandler`
(`logging/discord_handler.py`) posts records as embeds into `LOG_DISCORD_CHANNEL_ID`, and
`RouteFilter` (`logging/routing.py`) promotes any record at or above the discord threshold.
An audit line is the raw `/run` input — internal key names *and the values being set* — so
routing it there republishes into a Discord channel exactly what the command was built to keep
out of one, and does it in a channel whose read access is a server setting rather than the
owner list. The steering already exists per-record; the point is that it must be set
deliberately, because the default for a refusal logged at WARNING is to go.

## Consequences

- `/config` keeps `user`, `channel`, `server` and `view` as the discoverable surface for
  `audience="user"` keys. `/config global` is deleted and `Scope.GLOBAL` writes move to `/run`,
  which is the *only* thing that moves — `/run` is not a superset of `/config`, it is the
  replacement for one subcommand plus room to grow non-config verbs.
- A user-audience GLOBAL key (`polling`) stays readable through `/config view`; only the write
  path leaves. The two filters are orthogonal and both apply: `audience` decides who sees the
  name, `settable_scopes` decides where it can be written.
- **An `audience="owner"` key that is not GLOBAL-only would have no surface at all** — `/config`
  filters it out by audience, `/run` only writes GLOBAL. Every owner key in `REGISTRY` today is
  GLOBAL-only so nothing is stranded, but adding a per-guild owner key means designing a scope
  token first, not squeezing it into the existing grammar.
- Autocomplete must stay pure and fast — see [[d-autocomplete-is-a-hint]] for the deadline and
  the caps. A verb whose completion needs the catalog must bound its query the way
  `song.py:509` already does.
- Free text is always submittable, so **every token is re-validated in the handler**.
  Autocomplete narrows nothing. Existing precedent for the same discipline:
  `src/coda/extensions/liveupdates.py:285`.
- The `/run` handler must not become the parser, the validator, the dispatcher and the
  formatter in one function. Split: tokenize → resolve verb → verb handler → verb formatter.
- A `/run` verb is not exempt from [[h-config-audience-declared-on-key]]; it is the consumer
  that reads the registry unfiltered, and it is the only one.
- `/reconcile` (`src/coda/extensions/reconcile.py`) is the other command already living the
  problem: a top-level row in everyone's picker, described "(bot owner only)", gated only in
  the handler at `:22`. It is the natural second migration, and its existence is the argument
  that this category grows.
- **`OWNER_IDS` unset makes the entire owner surface unreachable.** `config.owner_ids` is a
  `frozenset` built from the env var (`src/coda/config.py:60`); empty means every gate refuses
  and `/run` is dead weight in the picker. Fail-closed is right, but it fails *silently* — a
  startup warning when the set is empty is worth the three lines.
- Confirm menus must stay well inside Discord's 15-minute interaction-token life. The existing
  `_make_reset_menu` call site uses `timeout=60`; keep that order of magnitude rather than
  inventing a longer one for "dangerous" verbs.

## Enforced at

**Built 2026-07-28.**

- `src/coda/extensions/run.py` — the command. Four gates, not three: the guilds it is
  *created* in (`OWNER_GUILD_IDS`) turned out to be a cheaper first layer than
  `default_member_permissions`, which stays as the second. Registered with
  `loader.command(Run, guilds=...)` as a function call, because `Loader.command`'s
  second-order decorator drops `global_`; and always with a tuple, because `client.py:610-620`
  reads `guilds=None` as "fall back to `default_enabled_guilds`" — an unset env would have
  published the terminal to every dev guild instead of nowhere.
- `src/coda/ops/` — `types.py`, `registry.py` (table + `tokenize`/`dispatch`/`suggestions`),
  `config.py`, `reconcile.py`. No `hikari` import in the package: an op returns text and an
  optional `ConfirmAction`, and the extension decides how that renders.
- `ConfirmAction.run` opens its **own** session. The button fires up to 60 s after the op
  returned; a captured session is closed by then. `_make_reset_menu` (`config.py:63`) already
  did this correctly and is the precedent.
- The invoker in an autocomplete callback is `ctx.interaction.user.id` —
  `AutocompleteContext` has no `user` property.
- `src/coda/extensions/config.py` — `ConfigGlobal` and `_KEYS_GLOBAL` deleted.
- `src/coda/extensions/reconcile.py` — deleted; `reconcile` is a verb.

Consequence accepted at build time: `/run` is **not reachable in DMs**, because
guild-scoped registration excludes them.

Still open: [[h-run-terminal-build-time]] item 1 (autocomplete replacement semantics, needs a
live capture). Items 2-5 are answered on that page.
