---
type: decision
status: active
date: 2026-07-18
reverses:
created: 2026-07-21
updated: 2026-07-21
tags: [decision, bot-accounts, registration, seeding]
aliases: ["Bot accounts are excluded from the player pool in both directions"]
---

# Bot accounts are excluded from the player pool in both directions

## Context

`BotAccount` (pool infrastructure the bot logs into to read friends' scores)
and `ArcaeaAccount` (a tracked player) are separate tables, but nothing on
the wire stops the same in-game account from being both. Two distinct ways
that could happen need two distinct guards:

1. A player tries to `/register` using a bot account's friend code or email.
2. An operator tries to seed a bot account (`scripts/seed_bot_account.py`)
   using credentials that already belong to a tracked player.

Left unguarded, either direction lets the poller track and potentially
[[h-straying-preserves-history|stray]] one of the bot's own accounts, or lets
a bot account burn a friend slot friending another bot account.

## Alternatives

| Option | Why not |
|---|---|
| Guard only the `/register` direction | Leaves a path where an operator accidentally seeds an already-tracked player as bot infrastructure — the poller would then treat pool infrastructure as a player to track. |
| Guard only the seed direction | Leaves `/register` able to onboard a bot account as if it were a player, which the API would happily allow, wasting a friend slot and creating a bot-watching-bot row. |
| Check by `friend_code` only, both directions | Bot rows seeded before `friend_code` existed have it `NULL`, so a code-keyed check alone misses them; the credentials path needs an email-keyed check anyway since it has no code to compare. |

## Decision

Both directions are refused, independently, by different keys:

**Direction 1 — `/register` refuses a bot account, on both register paths:**

- Code path: `reserved.is_bot_account(db, code)` checks the typed code
  against `BotAccount.friend_code` and raises
  `ReservedCodeError("bot_account", "You can't use that friend code.")`
  (`src/coda/players/reserved.py:94-113`, called from
  `src/coda/players/service.py:192-193`).
- Credentials path: `reserved.is_bot_email(db, email)` checks the typed
  email against `BotAccount.email` and raises
  `ReservedCodeError("bot_account", "You can't use that account.")`
  (`src/coda/players/reserved.py:116-132`, called from
  `src/coda/players/service.py:254-255`). **This check runs before the login
  call** — `src/coda/players/service.py:246-256` shows it firing ahead of
  `auth.login(email, password)` at `:266`, so a bot account is refused
  without ever spending a login request, and without needing `friend_code` to
  be populated (email is the bot account's other unique key, always present).
- Both refusals are **plain and honest** — "you can't use that
  code/account" — not the retired fake-not-found + mimicked-latency
  shrouding (dropped per handoff 05, see [[handoffs-readme]]).

**Direction 2 — seeding refuses an already-tracked player:**

- `scripts/seed_bot_account.py:159-173`: after logging in as the candidate
  bot account and reading `me.arc_user_id` from `/me`, it queries
  `ArcaeaAccount.arc_user_id == me.arc_user_id`. A match means this account
  is already a tracked player — the script prints a refusal ("already
  registered as a tracked player account... unregister that player first")
  and exits `1` **before** any `BotAccount` row is written
  (`scripts/seed_bot_account.py:175` is the first write, strictly after the
  guard at `:163-173`).
- The code comment states the reasoning explicitly: seeding it anyway "would
  let the poller track and stray our own bot — the reverse of the
  `/register` bot-code refusal" (`scripts/seed_bot_account.py:159-162`).

## Consequences

- The two checks use different keys (`friend_code`/`email` for direction 1,
  `arc_user_id` for direction 2) because each direction has different data
  available at check time — direction 2 only knows `arc_user_id` for certain
  after the login `/me` call, mirroring direction 1's credentials-path check
  needing `email` (known before any login) rather than `friend_code`
  (unknown until `/me`).
- A `BotAccount` row with `friend_code IS NULL` (seeded before that column
  existed) is invisible to the code-keyed half of direction 1 — the fix is
  re-running the seed script to populate it, not a code change (documented at
  `src/coda/players/reserved.py:104-106`).
- Nothing enforces this at the schema level (no cross-table constraint
  between `bot_accounts` and `arcaea_accounts`) — both guards are
  application-layer checks that must be reached to fire, not a DB invariant.

## Enforced at

`src/coda/players/reserved.py:94-113` (`is_bot_account`), `:116-132`
(`is_bot_email`); `src/coda/players/service.py:192-193`,
`:254-255` (call sites); `scripts/seed_bot_account.py:159-173` (the
already-tracked-player guard).
