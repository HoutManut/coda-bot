---
type: question
status: answered
blocks: []
source: 06-credentials-changed-server-side.md
created: 2026-07-21
updated: 2026-07-23
verified: 2026-07-18
tags: [question, credentials]
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

**Already resolved before this question was filed** — captured 2026-07-18 (three days
before this page's `created` date), documented in `src/coda/arcaea/errors.py`'s module
docstring and [[w-third-auth-envelope]], but never cross-linked back here. No new wire
capture needed; closing by pointing at existing evidence.

- **Whose credentials**: both. `sessions/adapters.py` shares one core between
  `BotAccountAdapter` (flips `BotAccount.is_active`) and `PlayerCredentialAdapter` (flips
  `PlayerCredential.is_valid`) — same `InvalidCredentials`/`mark_dead` mechanism, same
  wire behavior, regardless of which credential type rotated.
- **Changed by whom, why**: mechanically irrelevant — the wire treats an
  owner-rotated password and a lowiro-forced reset identically. Only the *symptom* is
  observed, not the cause.
- **How it surfaces on the wire**: NOT a direct 403 as guessed. It's two steps —
  the next authenticated call gets **HTTP 401 `{"code":"UnauthorizedError"}`**
  (a third envelope, distinct from `error_code: 203`), which `raise_for_envelope`
  maps to `SessionExpired` (transient, re-login attempted once). *That* re-login is
  what discovers the password no longer works — `/auth/login` then returns the
  ordinary 403 `ForbiddenError`, raising `InvalidCredentials` (terminal, `mark_dead`).
  A rotated password becomes a terminal failure only after one failed reauth attempt,
  never immediately.
- **Is existing handling adequate**: yes. The design already does the thing the "what
  would answer it" section wondered about — attempts a re-auth before declaring
  terminal, rather than terminal-on-first-401. `is_valid=False`/`is_active=False` is the
  correct policy for the *outcome* of that failed reauth, not a shortcut around it.
- **Notification**: ships — `players/session.py::handle_invalid` →
  `players/notify.py::notify_credential_invalid` DMs the owner once, after the credential
  is already durably marked dead. Nothing further needed here.

No design change indicated. The only actual gap was cross-referencing — this page existed
because its author didn't know about the 2026-07-18 capture; [[w-third-auth-envelope]] and
`errors.py` are the authoritative record going forward.
