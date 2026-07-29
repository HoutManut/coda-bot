---
type: question
status: open
blocks: []
source: 06-credentials-changed-server-side.md
created: 2026-07-21
updated: 2026-07-21
tags: [question, credentials, unresearched]
aliases: ["Can a stored Arcaea credential go stale server-side, and if so, is the current handling adequate?"]
---

# Can a stored Arcaea credential go stale server-side, and if so, is the current handling adequate?

## Why it is open

Captured as a bare observation from the owner (2026-07-17): a password stored
by the bot can stop being the account's real password without the bot doing
anything or being told. Everything past that single sentence is unresolved:

- **Whose credentials** — `BotAccount` (~5, hand-made, unreplaceable; a dead
  one takes its ~10 friend slots) or `PlayerCredential` (the optional tier-3
  opt-in; a dead one silently downgrades that player to the friend path) —
  are two different blast radii and the note does not say which was meant.
- **Changed by whom, and why** — a user rotating their own password is a
  different problem than lowiro forcing a reset.
- **How it surfaces on the wire** — presumably a 403 on `auth.login`, but
  unconfirmed against [[arcaea-auth-behavior]] (Tier 2, not
  re-verified in this ingest).
- **Whether existing handling is even wrong** — `PlayerCredential.is_valid`
  is documented as *"False = login returned 403. Terminal; never retried"*
  and `BotSession` has its own deactivation path. The note explicitly warns:
  *"Possibly the current behavior is already correct and this only needs a
  way to tell someone."* Nobody has established that a stale credential is
  actually mishandled rather than merely silent.
- **How a user would find out** — a notification path **does** exist and ships:
  `players/session.py::handle_invalid` DMs the owner **once** via
  `players/notify.py::notify_credential_invalid`, and the DM lives in `players/`
  precisely because `sessions/` must not import it. See [[session-lease]] and
  [[players]]. What is *not* settled is whether that one-shot DM is the right
  response to a *changed* credential as opposed to a *dead* one — the terminal
  `is_valid = False` policy below is the open part, not the notification itself.

## What would answer it

Deliberately research-first, not build-first:

1. Reproduce or confirm the failure mode on the wire — rotate a throwaway
   account's password externally, attempt `auth.login`, capture the exact
   response (status code, envelope, `error_code`) and grade it in
   [[arcaea-auth-behavior]].
2. Decide, with the owner, which credential type the original observation
   was about (or whether it applies to both).
3. Decide whether "terminal, never retried" is correct policy or whether a
   changed-not-dead credential deserves a re-auth prompt instead.

## Current best guess

**Guess, not established**: most likely surfaces as a 403 on `auth.login`,
handled identically to a bad-password 403 today (`is_valid = False`,
terminal). Whether that is the *right* answer for a changed (vs. always-bad)
credential is exactly what is unresolved.

## Answer

Not yet answered.
