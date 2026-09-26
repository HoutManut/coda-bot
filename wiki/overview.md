---
type: meta
title: "Overview"
status: stub
created: 2026-07-21
updated: 2026-07-21
tags: [meta, overview]
aliases: ["coda-bot — Overview"]
---

# coda-bot — Overview˝

## What it is

A Discord bot that answers Arcaea (rhythm game) queries — a player's recent scores and
song/chart data. A from-scratch rewrite of an older bot; the old tree is a behavioral
reference, not a source to port.

## How it reads scores

There is no public Arcaea API. The bot scrapes lowiro's private web API: it logs in with a
pooled **bot account**, adds the target player as a **friend** by 9-digit friend code, and
reads scores from `GET /webapi/friend/me`. Each bot account caps at ~10 friends, so slots
are a leased resource. A player may instead supply credentials (own path), which proves
ownership and unlocks data the friend path cannot see.

## Layering

```
extensions/   Discord-facing slash commands (hikari + lightbulb v3)
   ↓
players/ settings/ catalog/ approvals/    stateless services, AsyncSession per call
   ↓
sessions/     the only module that knows what a sid is
   ↓
arcaea/  +  db/     wire layer and persistence — arcaea/ NEVER imports db/
```

The `arcaea/` → `db/` ban is load-bearing, not stylistic: importing `coda.db` builds the
async engine at import time, so a violation makes the wire layer unimportable without a
live database. See [[w-arcaea-never-imports-db|arcaea never imports db]] (pending).

## Stack

Python 3.14 + `uv`. Postgres via SQLAlchemy 2.0 async (`asyncpg`), Alembic owns the schema,
no `relationship()` anywhere. hikari + lightbulb v3 for Discord. A separate FastAPI app
(`src/coda/admin`) edits the song catalog locally.

## Built vs not

Built: song catalog + admin editor, settings, lowiro API layer, session pool, `/register`,
live-update config, score tracking (poll loop both paths, storage, chart resolution +
reconcile), `/recent`.

Not built: the live-update poster, tournaments, `/song`, b30.

## Where to go next

- Game knowledge → `domains/`
- Code structure → `modules/`
- "Why is it like this?" → `decisions/`
- "What breaks silently?" → `gotchas/`
- "What is unfinished?" → `questions/`
