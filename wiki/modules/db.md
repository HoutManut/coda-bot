---
type: module
status: active
path: src/coda/db/
purpose: SQLAlchemy 2.0 async ORM models + declarative Base; Alembic-owned schema for the song catalog and player/score persistence
depends_on: []
used_by: [catalog, players, sessions, settings, scores (unbuilt module name — see flows/live-updates), extensions]
created: 2026-07-21
updated: 2026-07-21
tags: [module, db, persistence, postgres]
---

# db

## Purpose

`src/coda/db/` is the shared SQLAlchemy 2.0 (async) declarative layer: one `Base`
(`src/coda/db/base.py`), one `Base.metadata`, and every ORM model in
`src/coda/db/models/`. **Alembic owns the schema** — migrations are hand-reviewed
autogenerate output in `migrations/versions/`, never `create_all()`, and never a
hand-edited table. `uv run alembic check` asserts the models match the live schema.

No model anywhere uses `relationship()` — confirmed by source read
(`grep -rn "relationship(" src/coda/db/` returns nothing). Every join across
tables is written explicitly in service code. This is a deliberate constraint
(see [[h-no-orm-relationships]]), not an oversight.

## Public surface

| Symbol | File | What it does |
|---|---|---|
| `Base` | `db/base.py` | Shared `DeclarativeBase`; every model subclasses it |
| `Pack`, `Song`, `SongDifficulty` | `db/models/{pack,song,difficulty}.py` | Catalog core |
| `Artist`, `ArtistMember`, `SongArtist`, `DifficultyArtist` | `db/models/artist.py` | Artist entities, unit membership, per-song/per-chart links |
| `Charter`, `SongCharter`, `DifficultyCharter` | `db/models/charter.py` | Charter entities and links |
| `SongAlias`, `DifficultyAlias`, `ArtistAlias`, `CharterAlias` | `db/models/alias.py` | Search alias tables (source of truth for search; no DB triggers — populated by the catalog seed service) |
| `TagCategory`, `Tag`, `SongTag`, `DifficultyTag` | `db/models/tag.py` | Curated M:N tag vocabulary, orthogonal to packs |
| `DifficultySearchConfig` | `db/models/search_config.py` | Per-difficulty-class search tuning, read at startup |
| `BotAccount` | `db/models/bot_account.py` | A lowiro account the bot logs into to read friends' scores |
| `ArcaeaAccount`, `PlayerLink`, `PlayerCredential` | `db/models/arcaea_account.py` | In-game player, Discord↔player link, optional own-login |
| `PendingRequest` | `db/models/pending_request.py` | Durable human-decision queue (approvals) |
| `LiveUpdateChannel`, `LiveUpdatePref` | `db/models/live_update.py` | Guild channel allowlist + per-user destination preference |
| `PlayScore` | `db/models/play_score.py` | One observed play, accumulated by the poller |
| `coda.db.enums` | `db/enums.py` | `DifficultyClass`, `ArtistKind`, `LinkMethod`, `RequestStatus`, `Side`, `ClearType`/`GaugeModifier` (imported from `arcaea/dto/enums`, one-directional) — plus the matching Postgres `SAEnum` types |

## Layer rules

`db/` is imported by every feature package but must never be imported by
`arcaea/` (the wire client) — see [[arcaea]]. Building the async engine happens
at import time (`create_async_engine`), which is why `BOT_TOKEN`, `DATABASE_URL`,
and `FERNET_KEY` are read at import and a missing one breaks the bot, the admin
app, *and* Alembic in one stroke (see `docs/self-hosting.md`, filed as
[[self-hosting]]).

`db/enums.py` importing `coda.arcaea.dto.enums` (for `ClearType`/`GaugeModifier`)
does **not** violate the "`arcaea/` never imports `db/`" rule — the dependency
runs the other direction, and `dto/enums.py` is a pure module with no I/O, so
this does not build the engine as a side effect of importing the wire layer.

## Tables

### Catalog (Tier 1, but shipped and owned by this module)

| Table | PK | Notable FKs | On delete/update |
|---|---|---|---|
| `packs` | `pack_id` (VARCHAR) | — | — |
| `songs` | `song_id` (VARCHAR) | `pack_id → packs` | `onupdate=CASCADE` (a `pack_id` rename repoints its songs) |
| `song_difficulties` | `id` (SERIAL) | `song_id → songs`, UNIQUE(`song_id`,`difficulty`) | `onupdate=CASCADE` |
| `artists` | `artist_id` (VARCHAR) | — | — |
| `artist_members` | (`group_id`,`member_id`) | both `→ artists` | `onupdate=CASCADE` |
| `song_artists` | (`song_id`,`artist_id`) | `→ songs`, `→ artists` | `onupdate=CASCADE` |
| `difficulty_artists` | (`difficulty_id`,`artist_id`) | `→ song_difficulties`, `→ artists` | `artist_id onupdate=CASCADE`; no explicit delete rule on `difficulty_id` |
| `charters` | `charter_id` (VARCHAR) | — | — |
| `song_charters` | (`song_id`,`charter_id`) | `→ songs`, `→ charters` | `onupdate=CASCADE` |
| `difficulty_charters` | (`difficulty_id`,`charter_id`) | `→ song_difficulties`, `→ charters` | `charter_id onupdate=CASCADE` |
| `song_aliases` | `id` (SERIAL) | `song_id → songs`, UNIQUE(`song_id`,`alias`) | `onupdate=CASCADE` |
| `difficulty_aliases` | `id` (SERIAL) | `difficulty_id → song_difficulties`, UNIQUE(`difficulty_id`,`alias`) | none explicit |
| `artist_aliases` | `id` (SERIAL) | `artist_id → artists`, UNIQUE(`artist_id`,`alias`) | `onupdate=CASCADE` |
| `charter_aliases` | `id` (SERIAL) | `charter_id → charters`, UNIQUE(`charter_id`,`alias`) | `onupdate=CASCADE` |
| `tag_categories` | `id` (SERIAL) | UNIQUE `slug` | — |
| `tags` | `id` (SERIAL) | `category_id → tag_categories`, UNIQUE `slug` | `ondelete=CASCADE` |
| `song_tags` | (`song_id`,`tag_id`) | `→ songs`, `→ tags` | `ondelete=CASCADE, onupdate=CASCADE` on `song_id`; `ondelete=CASCADE` on `tag_id` |
| `difficulty_tags` | (`difficulty_id`,`tag_id`) | `→ song_difficulties`, `→ tags` | `ondelete=CASCADE` on both |
| `difficulty_search_config` | `difficulty` (enum PK) | — | one row per `DifficultyClass` |

`search_index` (§5 of the source doc) is a **materialized view**, not an ORM
model — it is raw SQL Alembic cannot autogenerate, refreshed after any alias
write. Sentinel values throughout the catalog: `level`/`rating` use `0` = TBA,
`-1` = N/A (`err` only); see [[catalog|Catalog]] and [[catalog|level encoding]] / [[catalog|CC encoding]]
(domain pages, Tier 1 — not authored by this ingest).

### Player / session / score (Tier 3 — this ingest's focus)

| Table | PK | Notable FKs | On delete/update |
|---|---|---|---|
| `bot_accounts` | `id` (SERIAL) | UNIQUE `email`, UNIQUE `friend_code` (nullable) | — |
| `arcaea_accounts` | `id` (SERIAL) | `bot_account_id → bot_accounts` (nullable); UNIQUE `arc_user_id`, UNIQUE `friend_code` | no explicit rule on `bot_account_id` |
| `player_links` | `id` (SERIAL) | `arcaea_account_id → arcaea_accounts`; UNIQUE `discord_id`; partial UNIQUE index on `arcaea_account_id WHERE is_owner` | `ondelete=CASCADE` |
| `player_credentials` | `id` (SERIAL) | `arcaea_account_id → arcaea_accounts`, UNIQUE | `ondelete=CASCADE` |
| `pending_requests` | `id` (SERIAL) | none (payload is JSONB, no FK) | indexed on `(status, expires_at)` and `(kind, responder_id, status)` |
| `live_update_channels` | `id` (SERIAL) | none | UNIQUE(`guild_id`,`channel_id`) |
| `live_update_prefs` | `discord_id` (BIGINT PK) | none | — |
| `play_scores` | `id` (SERIAL) | `arcaea_account_id → arcaea_accounts`; `song_difficulty_id → song_difficulties` (nullable) | **`arcaea_account_id`: `ondelete=RESTRICT`** (deliberate — see below); **`song_difficulty_id`: `ondelete=SET NULL`** |

**`play_scores` identity is the wire tuple, not the resolved chart FK**:
`UNIQUE(arcaea_account_id, wire_song_id, wire_difficulty, score, time_played)`.
`score: 0` is a real score and is part of the key — never filtered as "empty".
A secondary partial unique index guards `wire_play_id` (own-tier only,
`WHERE wire_play_id IS NOT NULL`) as an enrichment/trace column, **not** the
primary dedup key.

> [!contradiction]
> [[arcaea-bot-db-schema]] §9 sketches dedup as **tier-dependent**:
> "tier 2 has a stable play `id`; tier 1 must key on `(arc_user_id, song_id,
> difficulty, score, time_played)`." What shipped
> (`src/coda/db/models/play_score.py`) uses **one identity tuple for both
> tiers** — `wire_play_id` is a secondary guard, not the dedup key. This is a
> refinement discovered during implementation, not a design document anyone
> updated; the source page for `arcaea-bot-db-schema.md` is marked stale on
> this point.

**Why `arcaea_account_id → play_scores` is `RESTRICT`, not `CASCADE`**: see
[[h-straying-preserves-history]]. Score history is irreplaceable (no
backfill on the friend/free-own tiers — see [[Score history backfill]]), so an
account delete must be a conscious act that deals with its scores first, never
a silent cascade.

## FERNET_KEY gotcha (persistence-adjacent, not a DB constraint)

`bot_accounts.password_enc` and `player_credentials.{email_enc,password_enc}`
are Fernet-encrypted application-side under **one** `FERNET_KEY` env var with
**no rotation path** — the DB schema stores opaque ciphertext and cannot
enforce or detect a key change. Changing `FERNET_KEY` orphans every encrypted
row silently: no constraint violation, no error, just credentials that no
longer decrypt. See `docs/self-hosting.md` (filed as [[self-hosting]]) and
`CLAUDE.md` §Security.

## What Alembic owns

Every table above is Alembic-managed. Migration history (`migrations/versions/`)
shows the schema arriving incrementally and being *revised in place* as design
firmed up — e.g. `66ad9752c1d2_song_id_fk_on_update_cascade`,
`b3f1c2d4e5a6_entity_pack_fk_on_update_cascade`,
`460bea66bb35_one_account_per_discord_unique_discord_`,
`448eeff195d4_player_link_provenance_linked_via_and_`,
`72cf0122181a_play_scores`. Never hand-edit a table; never rely on
`create_all`; `uv run alembic revision --autogenerate -m "<msg>"` then
`uv run alembic upgrade head`. `uv run alembic check` asserts models match
the applied schema.

## State it owns

All Postgres tables listed above. No pickles, no flat files — this module is
the entire persistence layer for coda-bot's catalog and player/score state
(replacing the old project's JSON/pickle flat-file model, per `CLAUDE.md`).

## Related

[[self-hosting]], [[h-straying-preserves-history]],
[[h-one-account-per-user]], [[h-login-upgrades-link-in-place]],
[[h-owner-consent-on-second-claim]], [[h-bot-accounts-excluded-bidirectionally]],
[[h-no-orm-relationships]], [[tournaments|Tournaments]] (reads `play_scores`, writes
nothing), [[live-updates|Live Updates]] (unbuilt — reads `play_scores` + `live_update_*`),
[[b30]], [[Score history backfill]]
