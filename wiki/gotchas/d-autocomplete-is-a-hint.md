---
type: gotcha
status: active
severity: high
area: discord
verified:
created: 2026-07-28
updated: 2026-07-28
tags: [gotcha, discord, autocomplete, validation, run]
aliases: ["Autocomplete is a hint, not a constraint — and a chosen row replaces the whole option value"]
---

# Autocomplete is a hint, not a constraint — and a chosen row replaces the whole option value

## Symptom

Two separate failures, one mechanism.

**Submitted values you never offered.** A handler reads its option as though it came from the
choice list it advertised, and gets something else — a raw snowflake for a channel that was
never in the allowlist, a config key that is not in `REGISTRY`, a song id that does not exist.
The user typed it and pressed Enter without touching a suggestion. Nothing in the interaction
payload distinguishes a picked row from typed text.

**Completions that silently stop working past a certain line length.** Under a free-text
grammar like `/run` ([[h-owner-surface-is-run-terminal]]), short lines complete fine and long
ones just stop offering anything. No error, no truncation, no log line — the suggestion list
is simply empty from some length onward.

## Cause

Discord's autocomplete is a *rendering* attached to a string option, never a validator on it.
Three properties drive both symptoms:

- **A chosen row overwrites the entire option value**, not the token the cursor is in. Under a
  multi-token grammar, each suggestion's `value` therefore has to carry the whole line
  reconstructed up to and including the completed token — the prefix the user already typed,
  plus the completion.
- **Choice `name` and `value` are capped at 100 characters.** Combined with the point above,
  the cap applies to the *whole reconstructed line*, not to the token. So a grammar whose
  lines run long becomes uncompletable while remaining perfectly typeable, because the string
  option itself permits far more than 100 characters.
- **At most 25 rows, and the callback has roughly 3 seconds.** Named in-repo at
  `src/coda/extensions/liveupdates.py:41` (`_MAX_CHOICES`).

The submit path never consults the callback. A user can ignore suggestions entirely, or open
the picker, type, and submit before any response arrives.

## The wrong fix

**Trusting the option value because a choice list exists.** The tempting read is "the option
declares `choices=`, so lightbulb/Discord enforces membership" — true for a *static*
`choices=` array, and false for `autocomplete=`. The two look nearly identical at the
declaration site (`config.py:160` vs `config.py:163`, one option apart in the same class) and
behave completely differently on submit. Any handler that skips validation because "the
autocomplete only offers valid rows" is trusting a suggestion.

The second wrong fix, specific to `/run`: **completing only the focused token**, returning
just the word rather than the rebuilt line. It reads correctly during development because a
one-token line is indistinguishable either way, and it destroys the line the moment a second
token exists — picking a row for token 3 replaces tokens 1 and 2 with nothing.

The third: **raising the per-line character budget by making verb and key names longer and
more descriptive.** That trades a readable command for a dead completion at the exact point
the grammar gets useful.

## The right handling

Re-derive, never trust. `src/coda/extensions/liveupdates.py:285` states it inline:

> Re-check rather than trust the value: autocomplete is a…

`song.py:509` (`_autocomplete_choices`) and `chardle.py:657` follow the same discipline —
the completion is a convenience path, the handler resolves the value again from scratch.

For `/run`, that means the handler tokenizes and validates every token against `REGISTRY` and
the verb table as though no autocomplete existed, and the completion callback:

- gates on `config.owner_ids` and returns `[]` otherwise — an ungated callback is the leak
  `/run` was created to close ([[h-owner-surface-is-run-terminal]]);
- parses the partial line **purely and without I/O** to stay inside the deadline, which
  in-memory `REGISTRY` lookups satisfy and unbounded catalog queries do not;
- returns each row's `value` as the full line up to the completed token;
- caps at 25 rows.

## Regression signal

- A handler crashes on a `KeyError` from `REGISTRY[key]` or an `int()` of a non-numeric
  string — that value came from a user who typed it, and it means validation was skipped.
- Completions work for the first token or two, then stop appearing as the line grows: the
  100-character reconstructed-line cap.
- Picking a suggestion mid-line clears earlier tokens: the callback is returning the token
  instead of the line.

## Not yet verified

The whole-value replacement behaviour and the 100-character cap applying to the reconstructed
line are stated from Discord's documented autocomplete semantics, **not from a capture against
the live client**. They are load-bearing for the `/run` grammar — a single throwaway command
with a two-token grammar settles both in one interaction. Tracked in
[[h-run-terminal-build-time]]; date this page's `verified:` when it is done.
