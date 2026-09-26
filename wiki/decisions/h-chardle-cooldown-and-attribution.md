---
type: decision
status: active
date: 2026-07-30
reverses:
created: 2026-07-30
updated: 2026-07-30
tags: [decision, chardle, guess, cooldown]
aliases: ["Chardle guess cooldown, non-ephemeral chart-name replies, finished-daily sticky refresh"]
---
# Guess cooldown (3s, universal), non-ephemeral chart-name replies, finished-daily sticky refresh

## Context

[[h-chardle-shared-board-modes]] filed four unbuilt ideas from a 2026-07-30 design
conversation. Three of them (#2 attribution, #3 cooldown replacing round-robin, #4 dropped)
plus the widened refinement of #1 (sticky refresh on a resumed *finished* daily) were settled
and built the same session. Idea #1's original ask — letting a player relocate an unbeaten
daily's transport mid-game — is **not** covered here and stays open on that page.

## Decision

- **Sticky refresh on finished-daily resume.** `start_daily`'s existing-session branch
  (`extensions/chardle.py`) now calls `sticky.refresh` when resuming *into a guild*
  (`guild_id is not None`) a session that's already `WON`/`LOST` — the same call the
  fresh-open path already made. A `PLAYING` resume is untouched (nothing on the scoreboard
  could have changed). This folds a daily finished elsewhere (DM, no guild channel configured
  at the time) into that guild's scoreboard once the player later touches it there.
- **Guess replies: non-ephemeral, name the chart.** `Guess.invoke`'s `ctx.defer(ephemeral=True)`
  → `ctx.defer()`, unconditionally — every board kind, not just shared ones. Nothing
  server-side was ever deleting a guess or a player's message, so ephemeral only ever hid
  the reply, it didn't protect anything; on a shared board, the visible reply *is* the
  attribution (no avatar needed, see the source page's #2). `_apply_guess`'s `Accepted` arm
  now resolves `outcome.difficulty_id` via `facts.load_facts` and reports the chart name
  (`render.chart_label`, the same song-name+difficulty formatter the board's own reveal text
  uses — un-privated for this reuse) instead of generic "Guess recorded."/"Solved
  it."/"That was the last attempt."
- **Guess cooldown: 3 seconds, universal, no toggle.** New `Outcome` variant
  `Cooldown(remaining: float)` (`chardle/guess.py`), `COOLDOWN_SECONDS = 3.0`. After any
  **accepted** guess, the next accepted guess from a *different* `discord_id` on the same
  session must wait out the window — same player back-to-back is never blocked.
  `GuessService.cooldown_remaining` looks up the session's most recent guess by
  `ordinal DESC LIMIT 1` (not `created_at` — reuses the existing per-session ordinal
  invariant rather than trusting clock ordering) and compares its `discord_id`/`created_at`
  against the caller. Enforced in `_apply_guess`, before `guesses.submit`, so a
  cooldown-blocked attempt costs nothing (no `ChardleGuess` row, no ordinal burned) — same
  shape as `Invalid`/`Duplicate`/`Searched`. Applies to **every** session kind
  unconditionally: no `is_daily` gate, no opt-in `Play` option. This costs nothing on a
  genuinely solo board (the "last guess" is always the same person, the rule never fires)
  and correctly covers a multi-guesser private free-play thread without a special case.
  `_on_reply` reacts ⏳ on a cooldown-blocked reply-guess, alongside existing 🔍/❌.

## Alternatives

| Option | Why not |
|---|---|
| Opt-in cooldown via a new `Play` command option, default off | The source page floated this, but the exemption (same player never blocked) already makes the cooldown free on a solo board — a toggle adds a command surface and a session-state field for a case that self-resolves. Dropped in favor of always-on. |
| Cooldown enforced inside `GuessService.submit` | The source page specified enforcing it in `_apply_guess`, before `submit` — keeps `GuessService` a pure resolver and the no-cost-outcome shape (Invalid/Duplicate/Searched/Cooldown) consistent at the call site that already owns that pattern. |
| Ephemeral kept for daily boards only | Considered and rejected in favor of unconditional non-ephemeral, for simplicity — a daily reply going non-ephemeral has no attribution upside but also no cost (single-owner, nothing sensitive in a "guessed X" line). |
| Sticky refresh unconditionally on every resume (including still-`PLAYING`) | Costs a REST edit + query for a state the scoreboard can't have changed for. Gated on `existing.state is not PLAYING`. |

## Consequences

- No migration: `ChardleGuess.discord_id`/`created_at` already existed; no new `ChardleSession`
  column, no new command option.
- The cooldown constant lives in `chardle/guess.py` as a flat `COOLDOWN_SECONDS`, not per-tier
  — it paces the session, not the puzzle. If it ever needs tuning per board kind, that's a
  new decision, not a config surface today.
- `render._chart_label` is now `render.chart_label` (public) — its only other caller
  (`_reveal`, same module) is unaffected.
- Idea #1's core ask — a player-initiated mid-game relocation command, message-move
  semantics, one-shot vs ping-pong — is untouched and stays the open item on
  [[h-chardle-shared-board-modes]].

## Enforced at

`extensions/chardle.py` (`start_daily` resume branch, `Guess.invoke`, `_apply_guess`,
`_on_reply`), `chardle/guess.py` (`Cooldown`, `COOLDOWN_SECONDS`,
`GuessService.cooldown_remaining`), `chardle/render.py` (`chart_label`).
