# Self-hosting coda-bot

Everything you need to run your own instance. The [README](../README.md) covers
what the bot does; this covers how to stand it up and operate it.

## Requirements

- Python 3.14, managed with [`uv`](https://docs.astral.sh/uv/)
- Postgres, reachable from wherever the bot runs
- A Discord bot token
- At least one Arcaea account to use as a bot account (see below)

## Install

```bash
uv sync                              # install deps from the lockfile
cp .env.example .env                 # then edit .env (see below)
```

## Configuration (`.env`)

`.env` (gitignored) holds all secrets/config:

```bash
BOT_TOKEN=<discord-bot-token>                                         # required
DATABASE_URL=postgresql+asyncpg://<user>:<pass>@127.0.0.1:5432/coda   # required
FERNET_KEY=<44-char urlsafe base64 key>                               # required
DEV_GUILD_IDS=<comma/space-separated guild ids, or empty for global>  # optional
OWNER_IDS=<comma/space-separated discord user ids>                    # optional; FIRST is the main owner
OWNER_FRIEND_CODE=<the owner's own 9-digit friend code>               # optional; reserves the code for OWNER_IDS
```

`BOT_TOKEN`, `DATABASE_URL` and `FERNET_KEY` are read **at import**, so a missing one
fails the bot, the admin app and alembic alike.

Generate the Fernet key once:

```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

It encrypts stored Arcaea credentials (bot accounts and linked player accounts) and has
**no rotation path** — changing it orphans every encrypted row, meaning every bot account
must be re-seeded and every user must re-link.

`OWNER_IDS` grants `/config global` and lets an owner register the otherwise-reserved friend
code. Leaving it empty silently denies both.

## Database

Requires a Postgres database reachable at `DATABASE_URL` (create the database first,
e.g. `createdb coda`).

Alembic owns the schema (never `create_all`). The connection URL is read from
`coda.config` in `migrations/env.py`, not `alembic.ini`.

```bash
uv run alembic upgrade head                          # apply all migrations
uv run alembic downgrade base                        # drop all (full teardown)
uv run alembic revision --autogenerate -m "<msg>"    # generate a migration from model changes
uv run alembic current                               # show applied revision
uv run alembic history                               # list migrations
```

## Seed the song catalog

Imports `assets/arcsongs.json` into the ORM. Idempotent — safe to re-run.

> **`assets/` is not in the repo** — jackets are lowiro-copyrighted art and
> `arcsongs.json` is legacy seed data (the live catalog lives in the DB), so both
> are gitignored. A fresh clone seeds from your own songs JSON (pass its path) or
> restores a catalog dump from `backups/` via `./scripts/dump-songs.sh` output.

```bash
uv run python -m coda.catalog.seed                   # default source: assets/arcsongs.json
uv run python -m coda.catalog.seed path/to/songs.json
```

## Seed a bot account

The bot reads other players' scores by friending them from its own Arcaea accounts.
At least one is needed before `/register` works.

**Account creation is manual by design** — there is no automated signup path and none
should be built; it would mean defeating email verification and CAPTCHA, risking a ban
on the hand-made accounts the bot depends on. This only stores an existing account's
credentials (encrypted), after checking they actually log in.

```bash
uv run python scripts/seed_bot_account.py --email <email-or-username>   # prompts for password
uv run python scripts/seed_bot_account.py --list                        # show the pool
uv run python scripts/seed_bot_account.py --email X --deactivate        # stop using one
```

## First-time bring-up

```bash
uv run alembic upgrade head
uv run python -m coda.catalog.seed
uv run python scripts/seed_bot_account.py --email <your-bot-account>
uv run python -m coda                                # run the bot
```

## Catalog admin editor

A separate local FastAPI app for editing the song catalog (songs, charts, aliases,
tags). Runs against the same database:

```bash
uv run python -m coda.admin
```

## Backups

```bash
./scripts/dump-songs.sh              # dump the song/catalog tables to backups/
./scripts/dump-songs.sh -a           # full DB dump
```

## Development

```bash
uv add <pkg>                         # add a dependency (updates pyproject.toml + uv.lock)
uv remove <pkg>                      # remove a dependency
uv sync                              # install from lockfile

uv run pytest                        # all tests
uv run pytest path::test_name        # a single test
```
