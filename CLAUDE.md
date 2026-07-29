# CLAUDE.md

Guide for Claude Code (claude.ai/code) when work this repo.

## What this is

`coda-bot` answer Arcaea (rhythm game) queries on Discord — player recent scores, song/chart data.

Built so far: song catalog + admin editor, settings system, lowiro API layer, session pool, registration (`/register`), live-update config, score tracking (poll loop both read paths, storage, chart resolution + reconcile, `/recent`, `/tracking`, live-update poster + post filters), chardle (Wordle over the catalog; emoji renderer is temporary), `/run` owner terminal (bot-wide config + reconcile, created only in `OWNER_GUILD_IDS`). **Not built**: tournaments.

See `CODING_STYLE.md` for hard rules on function/file size, comments, error handling, abstraction, naming, typing, testing. See `wiki/` (below) for everything below this file level of detail.

## Tooling & commands

Project use **`uv`** with **Python 3.14**.

```bash
uv run python -m coda          # run the bot (src/ layout, package entry)
uv run python -m coda.admin    # run the local catalog admin editor (separate process)
uv add <pkg>                   # add a dependency (updates pyproject.toml + uv.lock)
uv sync                        # install from lockfile

uv run alembic revision --autogenerate -m "<msg>"   # create a migration
uv run alembic upgrade head                          # apply migrations
uv run alembic check                                 # assert models match the schema

uv run python -m coda.catalog.seed                   # BOOTSTRAP ONLY: seed the song catalog from assets/ (gitignored). Refuses if the catalog is non-empty -- the admin editor owns it once seeded. `--force` overrides (intentional re-bootstrap only).
uv run python scripts/seed_bot_account.py --email X  # add a bot account to the pool (prompts for password)
uv run python scripts/seed_bot_account.py --list     # list bot accounts
uv run python scripts/verify_multipart.py            # assert lowiro still accepts our add_friend body

./scripts/dump-songs.sh [-v VERSION] [-a]            # backup DB to backups/ (default: song/catalog tables; -a: full DB)
```

**Add/remove table → update `SONG_TABLES` list in `scripts/dump-songs.sh`** so song-only dumps stay complete. Player/bot tables deliberately *not* in that list — dumps catalog, not user data.

No test/lint setup yet. Add tests → prefer `uv run pytest`, single test via `uv run pytest path::test_name`. DTO sentinel handling (`wiki/modules/arcaea.md`) highest-value thing to pin down first — regresses silent.

## Structure & stack

**`src/` layout, feature packages.** `pyproject.toml` makes `src/coda` package.

```
src/coda/
  arcaea/     lowiro webapi client (was arcaea_online). PURE WIRE -- never imports db/
    dto/      raw dict -> typed objects. No I/O
  sessions/   BotSession + SessionPool. The ONLY module that knows what a sid is
  players/    registration, reserved codes, live-update destinations
  catalog/    song/chart seeding, aliases, resolution
  settings/   DB-backed scoped config (/config). `audience` on a key decides who sees it exists
  ops/        owner operations behind /run. Never imports hikari
  extensions/ hikari/lightbulb slash commands, auto-loaded from this package
  admin/      separate FastAPI catalog editor
  db/         SQLAlchemy models, async engine/session, declarative Base
  utils/      encoding, friend codes, Discord permissions
  crypto.py   Fernet encrypt/decrypt for stored credentials
  config.py   settings loaded from env / .env
migrations/   Alembic env + versions
scripts/
```

Postgres + SQLAlchemy 2.0 async (`asyncpg`) + Alembic, no `relationship()` anywhere — joins written explicit. hikari + lightbulb v3 for Discord, DI-injected services. **`BOT_TOKEN`, `DATABASE_URL`, `FERNET_KEY` read at import** — missing one breaks bot, admin app, *and* Alembic in one stroke.

Two layering invariants hold across whole codebase, not specific to any one domain: `arcaea/` **never imports `coda.db`** (returns data, never persists — importing `coda.db` builds async engine at import time, so this'd make wire layer unimportable without live database), and `sessions/` only module that knows what `sid` is (`bot_account_id` appears only in `sessions/pool.py`). Everything else — wire behavior, encodings, security posture, ownership rules — domain detail owned by `wiki/`, not restated here.

## `wiki/`

Obsidian vault, project knowledge base: domain pages, module/flow/decision/gotcha pages, open questions. Start at `wiki/hot.md`, then `wiki/index.md`. See `wiki/meta/conventions.md` for schema and precedence.

| Page | Covers |
|---|---|
| `wiki/domains/catalog.md` | Songs, difficulties, packs, artists/charters, level/CC encoding, aliases, inheritance |
| `wiki/domains/scoring.md` | Score formula, pure/far/lost, grades, clear types, gauge — hard-gauge loss submits early |
| `wiki/domains/potential.md` | Play rating, b30/r10, PTT encoding — b30 works any tier, r10 impossible on friend path |
| `wiki/domains/score-mapping.md` | Wire `(song_id, difficulty)` → `song_difficulties` row; `byd_2` needs `game_song_id` |
| `wiki/domains/auth-and-sessions.md` | Auth, sessions, friend endpoints — every claim graded, check grade |
| `wiki/modules/*.md` | `arcaea/`, `sessions/`, `players/`, `scores/`, `db/` — layout, envelopes, DTOs, pool, cadence |
| `wiki/domains/tournaments.md` | Tournament module design — not built |
| `wiki/questions/` | Open questions + designed-but-unbuilt work — not settled reference |

**Precedence: live wire > `src/` > this file > `wiki/`.** Wiki page carries `verified:` date, can go stale; if wire contradicts page, re-capture + update page — never "fix" code against stale claim, never let wiki page be reason to change code.