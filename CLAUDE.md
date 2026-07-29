# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`coda-bot` is a **from-scratch rewrite** of an earlier, unreleased Discord bot ("CodaBot") that is not part of this repository. The bot answers Arcaea (rhythm game) queries on Discord — looking up a player's recent scores and song/chart data. Where this file mentions "the old project", it means that predecessor: a **behavioral reference**, not a source to port. Re-derive structure rather than lifting files, and check any claim about it against `wiki/` and the live wire before trusting it (several old behaviors are wrong against the live API today — and one that looks wrong is load-bearing, see §Security).

Built so far: the song catalog + admin editor, the settings system, the lowiro API layer, session pool, registration (`/register`), live-update config, and score tracking — the poll loop (both read paths), score storage, chart resolution + reconcile, `/recent`, and the tracking opt-out (`/tracking`). **Not built**: the live-update poster (`wiki/flows/live-updates.md`), tournaments.

See `CODING_STYLE.md` for hard rules on function/file size, comments, error handling, abstraction, naming, typing, and testing.

## Tooling & commands

This project uses **`uv`** with **Python 3.14** (the old project used `requirements.txt` + a `venv`; do not reintroduce that).

```bash
uv run python -m coda          # run the bot (src/ layout, package entry)
uv run python -m coda.admin    # run the local catalog admin editor (separate process)
uv add <pkg>                   # add a dependency (updates pyproject.toml + uv.lock)
uv sync                        # install from lockfile

uv run alembic revision --autogenerate -m "<msg>"   # create a migration
uv run alembic upgrade head                          # apply migrations
uv run alembic check                                 # assert models match the schema

uv run python -m coda.catalog.seed                   # BOOTSTRAP ONLY: seed the song catalog from assets/ (gitignored). Refuses if the catalog is non-empty -- the admin editor owns it once seeded; re-seeding force-resets curated names to ids and resurrects merged/renamed entities. `--force` overrides (intentional re-bootstrap only). Fresh clones pass their own JSON path or restore a backups/ dump
uv run python scripts/seed_bot_account.py --email X  # add a bot account to the pool (prompts for password)
uv run python scripts/seed_bot_account.py --list     # list bot accounts
uv run python scripts/verify_multipart.py            # assert lowiro still accepts our add_friend body

./scripts/dump-songs.sh [-v VERSION] [-a]            # backup DB to backups/ (default: song/catalog tables; -a: full DB)
```

**When you add or remove a table, update the `SONG_TABLES` list in `scripts/dump-songs.sh`** so song-only dumps stay complete. Player/bot tables are deliberately *not* in that list — it dumps the catalog, not user data.

No test or lint setup exists yet. If you add tests, prefer `uv run pytest` and a single test via `uv run pytest path::test_name`. The DTO sentinel handling (§Security) is the highest-value thing to pin down first — it regresses silently.

## Structure & stack

**`src/` layout, feature packages.** `pyproject.toml` makes `src/coda` the package; do not develop a top-level `coda/` like the old tree.

```
src/coda/
  arcaea/     lowiro webapi client (was arcaea_online). PURE WIRE -- never imports db/
    dto/      raw dict -> typed objects. No I/O
  sessions/   BotSession + SessionPool. The ONLY module that knows what a sid is
  players/    registration, reserved codes, live-update destinations
  catalog/    song/chart seeding, aliases, resolution
  settings/   DB-backed scoped config (/config)
  extensions/ hikari/lightbulb slash commands, auto-loaded from this package
  admin/      separate FastAPI catalog editor
  db/         SQLAlchemy models, async engine/session, declarative Base
  utils/      encoding, friend codes, Discord permissions
  crypto.py   Fernet encrypt/decrypt for stored credentials
  config.py   settings loaded from env / .env
migrations/   Alembic env + versions
scripts/
```

- **Postgres + SQLAlchemy 2.0 (async) + Alembic.** This replaces all flat-file JSON/pickle persistence from the old project. `asyncpg` driver, `create_async_engine` / `async_sessionmaker`. Models use typed `Mapped[...]` / `mapped_column(...)` on a shared declarative `Base`, with **no `relationship()`** anywhere — joins are written explicitly. **Alembic owns the schema** — never hand-edit tables or rely on `create_all`. Connection URL comes from config/env, never hardcoded.
- **Env vars** (`.env`, gitignored): `BOT_TOKEN`, `DATABASE_URL`, `FERNET_KEY` **all required at import** — a missing one breaks the bot, the admin app *and* alembic. `DEV_GUILD_IDS` and `OWNER_IDS` are optional; `OWNER_IDS` is ordered and its **first entry is the main owner** (`config.main_owner_id`).

## How the bot works

**hikari** (Discord gateway) + **lightbulb v3** (slash commands + DI).

- **Entry**: `src/coda/__main__.py` → `bot.build()`, which wires the lightbulb `Client`, registers stateless singleton **services** into the DI registry, and auto-loads every module in `src/coda/extensions/` at startup. A new command = a new file there with a module-level `loader = lightbulb.Loader()`; no central edit. Commands declare service dependencies as `invoke()` params and lightbulb injects them.
- **Layering**: `extensions/` (Discord-facing) → feature services (`players/`, `settings/`, `catalog/`) → `sessions/` → `arcaea/` + `db/`. Services are stateless classes that take an `AsyncSession` **per call**; commands open `async with async_session() as db:` themselves. DTOs apply to *external* shapes (lowiro responses); internal persistence is ORM rows.
- **The layer rule that matters**: `arcaea/` **never imports `db/`** and never persists — `auth.login()` *returns* `(sid, expires_at)` and the caller writes them. This is not decorative: importing `coda.db` builds the async engine at import time, so breaking the rule makes the wire layer unimportable without a live database. `sessions/` is the only module that knows what a sid is, and `bot_account_id` appears in `sessions/pool.py` and nowhere else.
- **Arcaea Online client** (`src/coda/arcaea/`): a self-contained scraper of lowiro's private web API (`https://webapi.lowiro.com`). Logs in with a bot account, adds the target player as a **friend** by friend code, and reads scores from **`GET /webapi/friend/me`** (*not* `/webapi/user/me`, which carries no friends key). Sessions pool across bot accounts (each capped at ~10 friends). Account/session state lives in Postgres — **do not pickle**. `error_code`s map to typed exceptions; **branch on the response body, never the HTTP status**.
- **Two off switches for polling, at different levels.** Bot-wide: the `polling` config key (`/config global polling on|off`), re-read by the poller every tick so it needs no restart — it replaced the old `POLLING_ENABLED` env var, which is gone. Per account: `arcaea_accounts.tracking_enabled` (`/tracking`, owner-only, one flag per *account* because several Discord users can link one). Both stop **recording**, not fetching: the enforcement point is `ScoreStore.ingest`, the one choke point both read paths cross. An account with tracking off is still fetchable, so `/recent` works — the poller puts every observed play in `scores/observations.py::ObservationCache` and `/recent` renders from there when the DB has nothing newer. Never store-then-delete a play to render it.
- **Persistence is Postgres** via the ORM. The old flat-file model — JSON for songs/profiles/accounts, pickles for live sessions — is the *source data to migrate from*, not a pattern to keep. The static song/chart catalog still seeds from a bundled JSON; profiles, account/session state and scores live in the DB.

## Arcaea domain knowledge (don't re-guess these)

These encodings are domain-specific and easy to get wrong — port the *logic*, verified against the old `coda/utils/utils.py`:

- **Level** is stored as an int: `value*2` for plain levels, `value*2+1` for `+` levels, `-1` for `?`. (`encode_level`/`decode_level`)
- **Chart constant (CC / rating)** is stored ×10; `<= 0` means unknown. (`encode_rating`/`decode_rating`)
- **Play rating** formula (`calculate_play_rating`): score ≥ 10,000,000 → CC+2; 9,800,000–9,999,999 → CC + 1 + (score−9.8M)/200000; below 9.8M → CC + (score−9.5M)/300000; floored at 0.
- **Score** is an 8-digit value (max 10,000,000 + song note count).
- **Friend codes are exactly 9 digits**, validated locally in `src/coda/utils/friend_code.py` **before any request** — lowiro does not validate shape and answers `401` ("no such player") to outright garbage, so local validation is the only thing that lets the bot say "that's not a friend code". ⚠️ It strips **separators only** (`123 456-789` → `123456789`), deliberately *not* the old project's "strip every non-digit": that rule reduces `00000002ie1oi2ee` to nine digits and sends it, manufacturing a plausible code out of garbage and producing the exact wrong message. Do not "restore" it.
- Songs are loaded sorted by `song_id` and looked up with binary search.

### Domain references (`wiki/`)

`wiki/` is an Obsidian vault holding the project's knowledge base: domain pages, module/flow/decision/gotcha pages, and open questions. It is more detailed than the summary above; read the relevant page before touching an area. Start at `wiki/hot.md`, then `wiki/index.md`. See `wiki/CLAUDE.md` for the vault's schema and precedence rules.

| Page | Covers |
|---|---|
| `wiki/domains/catalog.md` | Catalog: songs, difficulties, packs, artists/charters, level/CC encoding, aliases, inheritance |
| `wiki/domains/scoring.md` | Score formula, pure/far/lost, grades, clear types, gauge. **A hard-gauge loss submits early — the only sub-song-length score** |
| `wiki/domains/potential.md` | Play rating, b30/r10, PTT encoding. **b30 works on any tier; r10 is impossible on the friend path** (excluding hard-gauge losses needs `clear_type`+`modifier`, both own-path only) |
| `wiki/domains/score-mapping.md` | Wire `(song_id, difficulty)` → `song_difficulties` row; `byd_2` needs `game_song_id` |
| `wiki/domains/auth-and-sessions.md` | Wire behavior: auth, sessions, friend endpoints. Every claim is graded — check the grade before trusting it |
| `wiki/modules/arcaea.md`, `wiki/modules/sessions.md`, `wiki/flows/registration.md` | `src/coda/arcaea/` + `src/coda/sessions/` + registration: layout, envelopes, DTOs, pool, reserved codes, cadence |
| `wiki/domains/tournaments.md` | Tournament module: rounds, windows, validity, state machine, tiers. Not built |

**The code and the live wire always win.** Wiki pages carry `verified:` dates and have a shelf life — never let a wiki page be the reason to change code.

**The private webapi changes without notice** — no versioning, no deprecation. If the wire contradicts a page, re-capture and update the page rather than "fixing" code against a stale claim.

`wiki/questions/` holds **open questions and designed-but-unbuilt work** — not settled reference. Read the relevant question page before touching `/register` or `src/coda/players/`: some record decisions that reverse what older pages say (the bot-code not-found oracle is retired; the alt model is dropped), so a page contradicting a newer decision in `wiki/decisions/` is stale, not authoritative.

**Use in-game vocabulary internally — pure / far / lost.** The API's `perfect`/`near`/`miss` names stop at the DTO boundary in `src/coda/arcaea/`.

## Security & hard-won gotchas

- **This project likely breaks Arcaea's ToS, two ways**, acknowledged and accepted risk, not oversight: (1) scraping `webapi.lowiro.com` — private, undocumented, no public API grant, header spoofing exists to keep it working, not to hide malice. (2) One-account-per-person: `player_links` enforces one Arcaea account per Discord user, but the bot-account pool is itself several in-game accounts run by one operator to serve strangers' friend-list reads — multiple accounts under one person by the letter of most such rules, even though no *user* of the bot ends up multi-linked. Risk is bot-account bans, not legal exposure; kept small on purpose (§coda-bot scale constraint). Noted in README under "Likely breaks Arcaea's ToS" — keep that section in sync if this changes.
- **Credentials are Fernet-encrypted** (`src/coda/crypto.py`) under one `FERNET_KEY` from env, with **no rotation path** — changing it orphans every encrypted row. Never log a password, and never log an exception's context from a credential path.
- **Header spoofing is insurance, not a requirement.** A bare `curl` gets 200 today. Keep it: Cloudflare fronts this API and can tighten bot rules with no notice, the cost is cheap, and the bot accounts are hand-made and unreplaceable. Each account — bot *and* own-path player — impersonates **one fixed, self-consistent Chrome build** (UA + `sec-ch-ua` triplet + platform), generated once at seed/registration time and stored in `bot_accounts.browser_identity` / `player_credentials.browser_identity`. `src/coda/arcaea/identity.py` owns it: `generate()` derives the whole set from one `(platform, chrome_version)` pair so the fields **cannot disagree**, and `bind()`/`current()` pass it per-task via contextvar. `sessions/session.py` binds the bot account's identity around every call; `players/service.py` binds the player's around the own-path login. This replaced a `fake_useragent` call that returned a **new random UA every request** against frozen client-hints — a self-contradicting browser (Windows UA, macOS platform hint) that flags *harder* than a plain default UA. `fake_useragent` was removed, not reused-at-create: it yields a UA but no matching client hints, so it reintroduces the very mismatch. **Coherence beats freshness** — don't reintroduce per-request UA rotation, and keep `generate()` internally consistent (everything derives from `major`); bump the `CHROME_VERSIONS` ceiling occasionally so the pool tracks real releases. Header-level spoofing maxes out here — TLS (JA3) and HTTP/2 fingerprints are aiohttp's, not Chrome's, and closing that gap needs a transport swap (`curl_cffi`) not worth it at this scale.
- ⚠️ **Never send `aiohttp.FormData` to lowiro.** Verified live: it streams `Transfer-Encoding: chunked` with no `Content-Length`, lowiro's origin hangs, and Cloudflare returns a **504**. Hand-build the body (`client.encode_multipart`). This makes the old client's `WebKitFormBoundary` **load-bearing, not cargo-cult** — the one old behavior worth keeping. Corollary: an HTML/non-JSON reply to a POST is *our framing* until proven otherwise, not a lowiro outage.
- ⚠️ **`dto/` is the volatility absorber.** Parse defensively (`.get()` + explicit defaults) and fail with "lowiro changed the API", never a bare `KeyError`. Sentinels that silently corrupt if missed: `rating: -1` means *hidden* (naive decode gives `-0.01`), `score: 0` is a **real score**, `recent_score` may be absent/null/`[]` for a never-played friend, and `showcase_characters` holds ints **or** dicts in one response.
- **The friend-code path has no proof of ownership, so a second claim asks the owner.** Codes are semi-public, so a code claim on an account someone else already owns can be an alt or a stranger and nothing can tell them apart. `register_by_code` returns `NeedsApproval`; the durable approval flow (`src/coda/approvals/` + `src/coda/players/link_approval.py`) DMs the current owner Approve/Deny, and only they decide. Silence never means yes: a 24h expiry (or an owner with closed DMs) refuses. Credentials still override — logging in is the only real proof, and promotes the proven user to owner (`is_owner` on `player_links`).
- **One account per Discord user, no switching — and straying preserves history.** `player_links` is `UniqueConstraint("discord_id")`: a user holds exactly one link. Registering a *different* account while linked is refused (`AlreadyLinkedElsewhere`) **before any friend slot is consumed** — the check sits ahead of `_acquire` in `register_by_code`, and after login-but-before-row-create in `register_by_credentials`. There is **no atomic switch** (an earlier design had "newest wins" — reversed); changing accounts is `/unregister` then a fresh `/register`. Logging in as an account you already code-linked is *not* a switch — it upgrades that one link in place (`_link` → `_prove_in_place`, the tier-1→tier-3 fix). The reverse cardinality (many Discord users → one account) stays legal via the consent flow above. **Straying** (`RegistrationService._stray`, fired by `unregister` when a link was the account's last) releases the pool slot (`SessionPool.release`: unfriend by **`arc_user_id`** then NULL `bot_account_id` — order matters, §multipart-style drift), sets `ArcaeaAccount.is_active=False`, deletes the `PlayerCredential` (the only *private* item), and **keeps the `ArcaeaAccount` row + its `play_scores`**. This preservation is deliberate and fixed policy, not keep-or-drop: the friend/free-own tiers have **no score backfill**, so a dropped history is irrecoverable, while a kept one reattaches on relink (same `arc_user_id`). The `play_scores → arcaea_accounts` FK is `RESTRICT` (not `CASCADE`) precisely so a stray — or any future account delete — cannot silently cascade that history away.
