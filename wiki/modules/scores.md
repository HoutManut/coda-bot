---
type: module
status: active
path: src/coda/scores/
purpose: Turns observed plays into durable rows, owns the poll loop, the on-demand refresh gate, the tracking opt-out, and the score embed.
depends_on: [arcaea, sessions, players, catalog, settings, db]
used_by: [extensions]
created: 2026-07-22
updated: 2026-07-24
verified: 2026-07-24
grade: A
tags: [module, scores, wire]
aliases: ["scores (module)", "scores"]
---

# scores

## Purpose

`scores/` is everything between "lowiro returned a recent play" and "a row exists /
an embed renders". It owns the poll loop (both read paths), the UPSERT that gives a
play one identity across paths, the in-memory caches that make `/recent` work without
a second fetcher, and the tracking opt-out enforcement point.

The package is ~1190 lines across 11 files and is the largest shipped surface the wiki
did not previously describe. **Read the code first** — the module docstrings in
`scores/` are unusually load-bearing and state the *why* for nearly every decision here.

## Public surface

| Symbol | File | What it does |
|---|---|---|
| `ScoreStore.ingest(db, results) -> list[ScoreResult]` | `service.py:55` | UPSERT observed plays; returns the genuinely-new ones (first-time INSERTs only). **The single enforcement point for the tracking opt-out and for unknown-`arc_user_id` skipping.** Does not commit |
| `row_values(result, account_id)` | `service.py:153` | Flattens a `ScoreResult` to `play_scores` columns. Public only so `/recent` can build a *detached* `PlayScore` for a play that was deliberately never stored |
| `PollCoordinator` | `coordinator.py:81` | The gate between the loop and commands. `.wait_for_trigger(timeout)`, `.mark_cycle_done(covered)`, `.request_refresh(key, max_age=5.0)`. No DB, no lowiro |
| `ObservationCache` | `observations.py:27` | Last *observed* play per `arc_user_id`, stored or not. `.record()` / `.latest()`. TTL 300 s, in-memory, empty on restart |
| `TrackingService` | `tracking.py:26` | `.link_of()`, `.account_of()`, `.set_enabled()` — backs `/tracking` |
| `PollSchedule` | `schedule.py:34` | Per-key due times, jittered and phase-spread. In-memory, no I/O |
| `PollKey = tuple[str, int]`, `BOT`, `OWN` | `keys.py` | Namespaced poll unit — `("bot", bot_accounts.id)` or `("own", arcaea_accounts.id)` |
| `poller.run(coordinator, observations, app, *, interval=None)` | `poller.py:55` | The loop. Started as a background task in `bot.py:52` |
| `reconcile(db)` / `run_reconcile_loop()` | `reconcile.py` | Backfills NULL `song_difficulty_id` every 300 s. Started in `bot.py:54` |
| `score_embed(row, chart, song, *, locale, night)` | `embed.py` | Renders one play. Shared by `/recent` and (eventually) the live poster |
| `B30Service.compute(db, account_id, limit=30) -> B30Result` | `b30.py:59` | Best-30, computed fresh on every call — no cache. Ranks every resolved chart's best score, marks the top 30 `counts_toward_b30=True`, returns up to `limit` (capped 50) plus TBA/unresolved exclusion counts. Source-agnostic (friend/own/manual rows rank identically). **No command uses this yet** — backend only, see [[h-b30-cache-stores-sum]] |

## Layer rules

- **The poller is the only code that calls lowiro for scores.** A command wanting fresh
  data calls `PollCoordinator.request_refresh` and then reads Postgres — it never
  fetches. One fetcher means an on-demand refresh cannot race the loop for
  `arcaea/client.py`'s shared rate limiter.
- **`bot_account_id` does not leak up.** A `PollKey` is opaque to `coordinator.py`; the
  `("bot", id)` key is only ever *constructed* by `sessions/pool.py::poll_key`. See
  [[w-sid-confined-to-sessions|sid confined to sessions]].
- **`ingest` is the choke point, so both off switches live there** — not in the poller,
  not in the commands. Bot-wide `polling` config gates *fetching* in `poller.run`;
  per-account `tracking_enabled` gates *recording* in `ScoreStore.ingest`. An account
  with tracking off is still fetchable, which is exactly what makes `/recent` work for it.
- **`ingest` does not commit** — `poller._store` commits (`poller.py:256`). A caller that
  forgets loses the cycle silently.
- **Chart resolution is the caller's job, not `ingest`'s.** The poller resolves and sets
  `ScoreResult.difficulty_id` before calling in; `ingest` writes whatever it is handed,
  `None` included. See [[chart-resolution|Chart Resolution]].

## State it owns

| State | Where | Durability |
|---|---|---|
| `play_scores` rows | Postgres | Durable. FK to `arcaea_accounts` is **RESTRICT** — see [[h-straying-preserves-history\|straying preserves history]] |
| `arcaea_accounts.tracking_enabled` | Postgres | Durable, per **account** not per Discord user |
| `ObservationCache._entries` | memory | 300 s TTL, lost on restart — by design, it is not storage |
| `PollSchedule._due` | memory | Per-key monotonic due times; a restart re-spreads every key |
| `_RefreshBudget._buckets` | memory | Per-key token bucket, `2` refills per `poll_interval`, cap `3` |

## Play identity — the thing that makes both paths agree

A play *is* `(arcaea_account_id, wire_song_id, wire_difficulty, score, time_played)`
(constraint `uq_play_identity`). `time_played` is server-assigned and immutable across
observations, so the same play seen on the friend path and later on the own path
collapses onto one row and is **enriched in place**.

| Path | Statement | May write |
|---|---|---|
| friend (`play_id is None`) | `ON CONFLICT DO NOTHING` | identity only — cannot blank detail an own sighting already stored |
| own (`play_id is not None`) | `ON CONFLICT DO UPDATE` | the 8 `_DETAIL_COLUMNS` + `source` |

> [!important] The paths no longer overlap (2026-07-24)
> `_friend_scores` drops the plays of any player the own path currently covers
> (`PlayerSessionProvider.own_covered` — the same `is_valid` + `is_active` predicate
> as `poll_sessions`, so it self-heals when a credential dies). Exactly one path
> authors any given play, and the UPSERT collision above is now only reachable in
> the window where a player gains or loses credentials.
>
> **Why:** enrichment is *silent* — the own path's `DO UPDATE` returns no id, so
> `submit()` never re-fires. The two keys are independently jittered, so roughly half
> the time the friend sighting inserted first and the live post went out with no note
> counts, health or clear type, **permanently**. `ObservationCache.record` had the same
> hole (its guard is a strict `>`, so an equal-`time_played` friend sighting overwrote
> the detailed own one), which is why the filter sits in the poller and not in `ingest`.
>
> **Cost, accepted by the owner:** a tier-2+ player who finishes a second chart before
> their own key comes due loses the first — `/user/me` only returns the latest. Owner's
> call: those are mostly failed plays, and the friend path could not have recorded a
> hard-gauge death correctly anyway.

`source` is **derived**, never passed: only the own endpoint carries a play id.

⚠️ **"New" means first-time INSERT, not "row returned".** The own path's UPSERT always
returns a row, so it can't use row-presence — `service.py:147` reads Postgres's
`(xmax = 0)` to distinguish inserted from updated. An own sighting enriching an
existing friend row is **not** new and must not fire the live poster. Getting this
wrong double-posts every play made by a credentialed user.

> [!warning] Contradicts [[arcaea-bot-db-schema]] §9
> That source sketches *separate* tier-1/tier-2 identities. Shipped `service.py` uses
> **one** identity tuple for both, with `wire_play_id` as a secondary guard. The
> shipped design is the real one.

## b30 — pure, on-demand, never cached

`b30.py` (built 2026-07-23, see [[h-b30-cache-stores-sum]]) is a read-only reduction over
`play_scores`, not part of the ingest/poll machinery above — it never writes and holds no
state between calls. One query pulls this account's `(song_difficulty_id, wire_song_id,
wire_difficulty, score)` rows; a max-score-per-chart reduction happens in Python, then one
`outerjoin(SongDifficulty, Song)` fetch resolves the survivors. Three exclusion cases, per
[[handoff-09-b30]]: delisted (silent drop — reuses `catalog/search.py::is_delisted`,
promoted from private `_is_delisted` this session so `b30.py` could reuse it rather than
reimplementing the name-convention check), TBA/unrated CC (`chart.rating <= 0`, dropped
but counted), unresolved chart (`song_difficulty_id IS NULL`, dropped but counted).

Play rating is computed the same way `catalog/labels.py::chart_rating_line` computes it
for `/recent` — `calculate_play_rating` + `decode_rating`, both from `utils/`. Never call
this PTT: it excludes r10 entirely, by design ([[d-r10-impossible-friend-path]]).

## Traffic shape is a security property, not a perf tweak

`schedule.py` exists because a fixed-period sweep firing every account back-to-back
from one IP is the most script-shaped pattern possible against a Cloudflare-fronted
API, and the bot accounts are hand-made and unreplaceable ([[w-coherent-browser-identity|coherent browser identity]] is the same concern at the header layer).

Three separate mechanisms, each fixing a distinct failure:

1. **Per-key interval, not a sweep clock.** `POLL_INTERVAL` is the gap between two
   polls *of one account*. A sweep clock makes the real period `interval +
   cycle_duration`, so every new account silently stretches everyone else's gap.
2. **Jitter** (`JITTER = 0.4`) — no two gaps repeat.
3. **Phase spreading** (`CORRECTION = 0.3`) — jitter alone random-walks phases and
   on-demand refreshes yank them, so keys cluster over hours. `_spread` compares
   neighbours by **phase (offset mod interval), not absolute due time** — measured
   absolutely the correction is one-directional and walks every period past
   `POLL_INTERVAL`, which is the bug the module exists to fix. `CORRECTION` must stay
   well below `1.0`: snapping to the midpoint converges on an evenly-spaced lattice, a
   *cleaner* fingerprint than the clustering it fixes.
4. **Stagger** (`poller.STAGGER = 3–12 s`) between keys that came due together, so a
   cold start is not one burst. Never before the first key, never on a targeted refresh.

## Related

[[score-poll-loop|Score Poll Loop]] · [[chart-resolution|Chart Resolution]] · [[sessions]] · [[players]] ·
[[db]] · [[live-updates|Live Updates (poster)]] · [[score-mapping|Score Mapping]] ·
[[scoring|Scoring]] · [[potential|Potential]] · [[handoff-09-b30|09 — b30]] ·
[[h-b30-cache-stores-sum]] · [[d-score-zero-is-real]] · [[d-byd2-game-song-id-resolution]] ·
[[h-recent-duplicate-suppression]] · [[h-straying-preserves-history]]
