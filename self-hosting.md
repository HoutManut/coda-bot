# Self-hosting coda-bot

Everything you need to run your own instance. The [README](../README.md) covers
what the bot does; this covers how to stand it up and operate it.

> [!warning]
> By hosting this bot, you agree to accepting the risk of breaking Arcaea ToS. See [README.md](../README.md) for more detail.

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
OWNER_GUILD_IDS=<guild ids /run is created in>                        # optional; falls back to DEV_GUILD_IDS
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

`OWNER_IDS` grants the `/run` owner terminal and lets an owner register the otherwise-reserved
friend code. Leaving it empty silently denies both.

`/run` is created only in `OWNER_GUILD_IDS` and hidden from non-admins there; with neither it
nor `DEV_GUILD_IDS` set, it is created nowhere and owner operations are unreachable.

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

> **Most of `assets/` is not in the repo** — `assets/jackets/` and
> `assets/chardle/` are lowiro-copyrighted art and `arcsongs.json` is legacy seed
> data (the live catalog lives in the DB), so all three are gitignored. A fresh
> clone seeds from your own songs JSON (pass its path) or restores a catalog dump
> from `backups/` via `./scripts/dump-songs.sh` output. `assets/fonts/` **is**
> committed — the board renderer will not start without it.

```bash
uv run python -m coda.catalog.seed                   # default source: assets/arcsongs.json
uv run python -m coda.catalog.seed path/to/songs.json
```

## Chardle board art

Chardle draws its boards with Pillow, from PNGs under `assets/chardle/`:

```
header.png stand.png            column header plate and its label ornament
0.png 1.png 2.png 3.png         row plate per side; 3 (Lephon) copies 2 (Achromic)
0_BYD.png … 3_BYD.png           Beyond variants; 2_BYD/3_BYD copy the plain plate
back/0.png … back/3.png         jacket frame
shadow_0.png … shadow_3.png     side pill drawn under the side name
hint/{green,yellow,red}.png     feedback wash
hint/{yellow,red}_{up,down}.png feedback wash with a direction chevron
```

Fonts ship in `assets/fonts/` and are routed by glyph coverage, not by language.
After changing the chain or importing songs with new scripts:

```bash
uv run python scripts/check_font_coverage.py         # must report nothing uncovered
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

## Tournaments

Matches run in **threads off one channel per server**, so an admin has to point the
bot at one before anything can start:

```
/tournament channel channel:#tournaments
```

Or run `/tournament channel` with no options in the channel you want to use, and
press **Use this channel**. The button only appears when no channel is set yet,
and only for someone with Manage Channels.

Without it `/tournament quick` refuses. It never falls back to the channel the
command was typed in — a server that later moves its tournament channel would
otherwise strand every thread already under the old one.

The bot needs these permissions **in that channel**:

| Permission | Without it |
|---|---|
| Create Public Threads | a `visibility: public` match cannot start |
| Create Private Threads | a `visibility: private` match cannot start (this is the default) |
| Send Messages in Threads | the thread opens but the board never posts |
| Manage Threads | a crew's archived thread cannot be reused, so every match opens a new one |

The failures are silent from a player's side — they just see a refusal naming the
permission — so it is worth checking the channel overrides rather than the
server-wide role.

Two server defaults keep `/tournament quick` short, and both are optional:

```
/config guild key:tournament_default_level value:9-10+
/config guild key:tournament_default_best_of value:5
```

`tournament_default_level` is a band (`9`, `10+`, `9-10+`, `9-`, `-10`); unset means
any level. The others are `tournament_default_bans` and
`tournament_default_visibility`. None can be set per-user: a match is shared state,
and two players must not believe different rules apply.

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
