---
type: question
status: open
blocks: [run, settings]
source: design conversation 2026-07-28
created: 2026-07-28
updated: 2026-07-28
tags: [question, run, settings, discord]
aliases: ["What is still unsettled about /run before it is built?"]
---

# What is still unsettled about `/run` before it is built?

> [!note] Built 2026-07-28. Only item 1 (autocomplete replacement semantics) is still open.

## Why it is open

The 2026-07-28 conversation settled the shape — [[h-owner-surface-is-run-terminal]] for the
surface, [[h-config-audience-declared-on-key]] for the visibility rule,
[[d-autocomplete-is-a-hint]] for the mechanics that constrain both. Nothing is built. What is
left is the residue that cannot be settled in prose: one behaviour that needs a capture, one
bug that predates the design and must not be inherited silently, and a set of choices that
want to be made against real code rather than in the abstract.

## The leftovers

### 1. Discord's autocomplete replacement semantics — needs one capture

The grammar in [[h-owner-surface-is-run-terminal]] assumes a chosen suggestion replaces the
**entire option value**, so every row's `value` must be the rebuilt line, and the 100-character
choice cap therefore applies to the whole line rather than the token. Stated from documented
semantics, not observed.

**What would answer it:** register a throwaway command with one string option and a two-token
autocomplete, pick a row for the second token, read what lands in the box. Also worth capturing
in the same pass: whether a >100-character `value` is rejected at registration, truncated, or
silently dropped from the list — that determines whether the failure mode is loud or is the
silent one the gotcha page describes.

If replacement turns out to be token-scoped instead, the grammar gets *more* headroom, not
less, and only the callback changes. Nothing in the decision pages reverses.

### 2. `set_value` stores whatever it is handed — no coercion anywhere

This is a live bug, not a design question, and `/run` would inherit it.

`ConfigKey.type` accepts `"str" | "bool" | "int"` or a tuple of literals
(`src/coda/settings/types.py:20`). The command layer validates **only** the tuple case
(`src/coda/extensions/config.py:133`); everything else falls through. `set_value`
(`src/coda/settings/service.py:71`) then writes `{"v": value}` into JSON verbatim, and
`resolve` reads `row.value["v"]` straight back out.

So every `type="int"` key set through `/config` is stored as a **string**:
`chardle_bpm_window`, `chardle_note_window`, `chardle_abandon_hours` — declared int, defaulted
int, persisted `"20"` the moment anyone sets one. Consumers get an int from the default path
and a string from the configured path, which is the kind of divergence that shows up as an
arithmetic `TypeError` weeks later on a key nobody touched recently.

**What would answer it:** decide where coercion lives, then fix `/config` and build `/run` on
top of the fixed version rather than around it.

*Current best guess (a guess):* a single registry-driven `parse_value(defn, raw) -> Any` in
`settings/`, called by both surfaces before `set_value`, raising a typed error the command
layer renders. Putting it inside `set_value` is tempting and slightly wrong — `set_value`
takes `Any` and is also the path a future non-string caller would use, so validation there
would have to be conditional on the input already being a string.

Whether to migrate existing rows: the affected keys all have int defaults, so a read-side
coercion would mask the bug rather than fix it. Cleanest is a one-off `UPDATE` over
`config_values` for `type="int"` keys, consistent with the dev-stage destructive-is-fine stance.

### 3. The verb table's first contents

`config get|set|reset` is obvious and covers the `/config global` migration. `help` is
required, not optional — see [[h-owner-surface-is-run-terminal]]. Beyond those, nothing is
chosen. Candidates raised but not decided — each needs to clear the "internals-only" half of
the scope rule *and* the "if users need it, build a real command" half:

- **`reconcile`** — the strongest case, because `/reconcile`
  (`src/coda/extensions/reconcile.py`) already exists as a top-level command with the exact
  problem `/run` was designed for: a row in everyone's picker whose description says "(bot
  owner only)", gated only in the handler at `:22`. Migrating it is a straight deletion plus
  four lines of verb. The only argument against is that it takes no options, so it leaks a
  name and not a schema.
- `session list` / `session drop <id>` — must not print a `sid`, per
  [[w-sid-confined-to-sessions]]; the formatter is the whole design question.
- poll-loop nudges — overlapping surface with `reconcile` once that moves.
- catalog cache / search-index rebuild — overlaps the admin app, which is the natural home.

**What would answer it:** build `config` + `help` alone, ship it, and let the third verb be one
that was actually wanted twice. `reconcile` has been wanted once and already has a home, so it
migrates when `/run` proves itself, not before.

### 4. `/run` in DMs, and `contexts`

`default_member_permissions` only governs guild installs. Whether `/run` should be reachable in
DMs at all — and whether to constrain `contexts` / `integration_types` (both available,
`commands.py:82-88`) — was not discussed. DM access is convenient and removes the guild-admin
visibility caveat entirely; it also means the command exists in a context where
`default_member_permissions` does nothing and only the handler gate stands.

### 5. Audience for the existing keys

[[h-config-audience-declared-on-key]] defaults new keys to `"user"`, but the eleven keys in
`REGISTRY` today were written before the field existed and each needs a call. `locale` and
`recent_b30_stat` are plainly user. `chardle_debug_board` is plainly owner. `polling`,
`chardle_epoch`, `chardle_timezone` are the interesting ones — operational, but a user might
reasonably want to *read* them, which the decision explicitly permits for a GLOBAL-only
user-audience key.

## Answer

**Items 2-5 answered by the 2026-07-28 build. Item 1 still open — it needs a live capture,
and the build does not depend on which way it lands.**

**2. Coercion** — `parse_value(defn, raw)` in `settings/parse.py`, exactly the guess above:
registry-driven, called by both write paths before `set_value`, raising `ValueError` with a
message the command layer renders. It also validates `type="timezone"` through `ZoneInfo`,
because `parse_zone` falls back silently at read time — without that, setting a typo'd zone
reports success while the bot keeps using Bangkok. No migration was needed: the dev database
held no int-key rows at all, so nothing had been miscast yet.

**3. First verbs** — `config` (`get`/`set`/`reset`/`list`), `reconcile`, `help`. The "let the
third verb be one that was wanted twice" reasoning was overruled deliberately: the owner asked
for `/reconcile` to migrate in the same change, and it is a straight deletion plus one small
module.

**4. DMs** — not reachable, and by a stronger mechanism than `contexts`: `/run` is *created*
only in `OWNER_GUILD_IDS`, so it exists nowhere else. The guild-admin visibility caveat
survives, bounded to that one guild, and `default_member_permissions=NONE` is the layer that
handles it there.

**5. Audience of existing keys** — six owner (`polling`, `chardle_epoch`,
`chardle_debug_board`, and the three chardle windows), three user (`locale`,
`recent_b30_stat`, `timezone`). The owner's call on the interesting ones was **none of them
surfaces**, `polling` included. `chardle_timezone` did not get an audience — it got
**renamed**: it is now `timezone`, a general key feeding both Chardle rollover and day/night
jacket art, guild-settable with a bot-wide default. `is_night` (`catalog/jackets.py`) takes a
`ZoneInfo` instead of hardcoding GMT+7 and ignoring the `user_id` it was handed, and
`DEFAULT_ZONE`/`parse_zone` moved to the pure `coda/utils/zones.py` so the registry and
`chardle/schedule.py` share one literal rather than two kept in step by comment.
