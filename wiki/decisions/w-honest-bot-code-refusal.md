---
type: decision
status: active
date: 2026-07-17
reverses: "handoff 05's predecessor: mimicking an unknown-code 401 + latency for a bot-account code"
created: 2026-07-21
updated: 2026-07-21
tags: [decision, registration, reserved-codes]
aliases: ["Refuse a bot-account friend code honestly, not with a mimicked not-found"]
---

# Refuse a bot-account friend code honestly, not with a mimicked not-found

## Context

A bot account's own friend code must never be registerable as if it were a player — the API
would happily let a bot friend another bot, burning a real pool slot and creating a
bot-watching-bot row that pollutes the poller. The earlier design (superseded by handoff 05,
referenced from `arcaea-api-layer.md` §6 and `players/reserved.py`) treated this as an
enumeration threat: reusing `PlayerUnreachable` (the same message a genuinely nonexistent
code gets) and sleeping `reserved.mimic_not_found_latency()` so neither the wording nor a
stopwatch could distinguish "this is one of our bot accounts" from "this code does not
exist" — an attempt to keep the bot-account pool's codes unlearnable even by someone probing
`/register` repeatedly.

## Alternatives

| Option | Why not |
|---|---|
| Keep the mimicked-latency, mimicked-message fake-not-found (the prior design) | Rejected on purpose (handoff 05). The repo is open source, so the mechanism (which codes are reserved and why) is public regardless of what the bot says at runtime — shrouding it behind a lie fools nobody with source access, while a real user who genuinely typo'd their own code is told something false ("no such player") that gives them no path forward |
| A generic "invalid code" message that doesn't distinguish bot-account from anything else | Loses the chance to tell a legitimate user something actionable — a bot-account collision is a different situation from a typo, and only one of the two has a useful specific message |

## Decision

A friend code belonging to one of the bot's own accounts is refused **plainly**: "You can't
use that friend code." — via `ReservedCodeError("bot_account", "You can't use that friend
code.")`, raised from `reserved.is_bot_account`'s call site in
`RegistrationService.register_by_code` (and the email-keyed equivalent,
`reserved.is_bot_email`, on the credentials path — refused *before* spending a login round
trip). No mimicked latency, no reused not-found wording.

**The reasoning that makes this safe**, not just simpler: the bot-account pool's codes are
already effectively unguessable at this project's scale — no friend object anywhere on the
wire ever carries a `friend_code` (see [[w-formdata-504]]'s sibling finding in
`arcaea-auth-behavior.md` §7.4), no endpoint maps a `user_id` back to a `friend_code`, and
the space is 10⁹ against a user base under 50. An enumeration attack against the pool has no
oracle to enumerate *with*, honest refusal or not — so the only thing the old
mimicked-latency design was actually buying was a worse experience for genuine users, in
exchange for a security property the wire's own shape already provides for free.

## Consequences

- `mimic_not_found_latency()` was deleted outright, not merely deprecated — its
  reintroduction (e.g. from a stale copy of an older design doc) should be treated as a
  regression, not a restoration.
- A user who collides with a bot-account code gets a message that tells them something true
  and actionable, rather than a lie that happens to be indistinguishable from a real
  not-found.
- This decision only holds because the "no enumeration surface exists" premise holds — if
  the wire ever grows an endpoint that maps `user_id`/`friend_code` to each other (currently
  confirmed absent, `arcaea-auth-behavior.md` §7.4), the honest-refusal reasoning would need
  re-examining, since the threat model it dismisses would then actually exist.

## Enforced at

`src/coda/players/reserved.py::is_bot_account` / `is_bot_email` (the checks) and their call
sites in `src/coda/players/service.py::register_by_code` / `register_by_credentials` (the
refusal). See [[Registration]] for where in the ordering this check runs.
