---
type: source
status: active
path: docs/self-hosting.md
lines: 129
dated: undated (living operations doc)
verified: 2026-07-21
supersedes: []
superseded_by: []
created: 2026-07-21
updated: 2026-07-21
tags: [source, ops, self-hosting]
aliases: ["Self-hosting coda-bot"]
---

# Self-hosting coda-bot

## Covers

The operator-facing setup doc: install, `.env` configuration, database
bring-up via Alembic, song catalog seeding, bot account seeding, first-time
bring-up sequence, the catalog admin editor, backups, and dev commands.
Complements the README (what the bot does); this is how to run it.

## Key claims

- `BOT_TOKEN`, `DATABASE_URL`, `FERNET_KEY` are all required, read **at
  import**, so a missing one fails the bot, the admin app, and Alembic alike
  — **matches** `CLAUDE.md` §Env vars and the [[db]] module page's note on
  the same gotcha.
- `FERNET_KEY` has **no rotation path**: changing it orphans every encrypted
  row, meaning every bot account must be re-seeded and every user must
  re-link. Placed as a gotcha-grade warning on [[db]] per this ingest's
  instructions (never a claim to reproduce a real key value).
- `OWNER_IDS` is ordered; leaving it empty silently denies both `/config
  global` and the reserved owner-code registration path — a silent-default
  gotcha worth knowing before deploying without it.
- Bot account creation is **manual by design** — no automated signup exists
  or should exist, since automating it means defeating email verification and
  CAPTCHA and risking the hand-made, unreplaceable accounts the bot depends
  on. `scripts/seed_bot_account.py` only stores an *existing* account's
  credentials after confirming they log in. See
  [[h-manual-bot-account-creation]] (decision).
- `assets/` (jackets, `arcsongs.json`) is gitignored — copyrighted art plus
  legacy seed data, since the live catalog lives in the DB once seeded. A
  fresh clone seeds from its own songs JSON or restores a `backups/` dump.
- Alembic owns the schema — the self-hosting doc's own bring-up sequence
  (`alembic upgrade head` before any seed step) operationally enforces the
  same rule stated architecturally in `CLAUDE.md` and [[db]].

## Contradicts / reversed by

None. Fully consistent with `CLAUDE.md` §Env vars / §Structure & stack and
with the shipped `scripts/seed_bot_account.py` / `alembic.ini` +
`migrations/env.py` setup (not modified, read only for this ingest).

## Feeds

[[db]], [[h-manual-bot-account-creation]]
