---
type: decision
status: active
date: 2026-07-17
reverses:
created: 2026-07-21
updated: 2026-07-21
tags: [decision, security, credentials]
aliases: ["One `FERNET_KEY`, no rotation path, covering both bot and player credentials"]
---

# One `FERNET_KEY`, no rotation path, covering both bot and player credentials

## Context

Both `BotAccount.password_enc` and `PlayerCredential`'s email/password need encryption at
rest before any DB row is written. `arcaea-api-research-tasks.md` task 12 required a
decision before writing any encrypt/decrypt code, because changing key strategy later means
re-encrypting every existing row.

## Alternatives

| Option | Why not |
|---|---|
| `MultiFernet` with rotation support | Complexity with no payoff at this project's scale (<50 users, ~5 bot accounts) — nothing in the design ever calls for rotating without a re-seed anyway |
| Separate keys for bot-account vs. player credentials | Two secrets to manage in `.env`/prod instead of one, for a distinction (bot vs. player) that the encryption layer has no reason to treat differently — both are "a password that must not leak" |
| A seed-migration bake-in of credentials (Alembic) | Would hardcode plaintext credentials into version control before encryption ever runs — directly conflicts with the encryption decision itself |

## Decision

One `FERNET_KEY` environment variable, required at import, covering both
`BotAccount.password_enc` and every `PlayerCredential` row. **No rotation path exists.** If
the key is ever rotated, every encrypted row is orphaned by design — the fix is to re-seed
every bot account and have every user re-run `/register method:account`, not to migrate
ciphertext.

## Consequences

- `FERNET_KEY` missing at import breaks **three** things simultaneously: the bot, the admin
  app, and `alembic` itself — this is intentional, not a bug, per `CLAUDE.md`. It makes the
  key's absence loud and immediate rather than a runtime surprise deep in a request.
- Rotation is destructive by design: a real key rotation is an operational event (re-seed +
  mass re-registration), not a background migration. This is acceptable because it is rare
  and the user base is small enough that a mass re-registration is a real, if annoying,
  option — it would not be at a larger scale.
- No plaintext credential, key, session id, or friend code may ever be written into a log,
  the wiki, or any other durable artifact — the single-key, no-rotation design makes the key
  itself the one thing standing between "encrypted at rest" and total compromise, so nothing
  should ever normalize handling it or its outputs loosely.

## Enforced at

`src/coda/crypto.py` — two functions (`encrypt`/`decrypt`) over a module-level `Fernet`
instance built from `FERNET_KEY` at import time. `players/service.py::_store_credential`
and `scripts/seed_bot_account.py` are the two call sites that ever write an encrypted
credential.
