---
type: flow
status: active
entrypoint: coda.scores.poller.run — background task started in bot.py:52
touches: [scores, sessions, players, catalog, settings, arcaea, db]
created: 2026-07-22
updated: 2026-07-22
verified: 2026-07-22
grade: A
tags: [flow, scores, wire]
aliases: ["Score Poll Loop", "score-poll-loop", "Poll Loop"]
---

# Score Poll Loop

## Trigger

Two ways in, one loop:

- **Periodic** — `PollSchedule.seconds_until_due()` elapses. `wait_for_trigger` returns
  `None`, meaning "sweep whatever is due" (normally *one* key).
- **On-demand** — `/recent` calls `PollCoordinator.request_refresh(key)`, which sets
  `_wake`. `wait_for_trigger` returns the pending key **set**, and only those are polled.

`timeout=None` blocks until an on-demand wake — that is how "polling disabled" is
expressed at the coordinator level.

## Path

1. `poller.run` — `_pollable_keys(app)` (`poller.py:156`) enumerates every pollable
   key and whether it belongs *on the schedule*:
   - `(BOT, s.account_id)` for each `SessionPool.active()` session → always `True`
   - `(OWN, account.id)` for each `PlayerSessionProvider.poll_sessions()` →
     `account.tracking_enabled`
2. `schedule.sync(...)` — adds newcomers at `k * interval / N` from now, shuffled, and
   drops departed keys. **A joining key never shifts an existing key's phase.**
3. `coordinator.wait_for_trigger(schedule.seconds_until_due())` — sleep.
4. `keys = schedule.due_keys()` (periodic) or `list(targets)` (on-demand).
5. Periodic only: `_polling_enabled()` (`poller.py:98`) re-reads the `polling` config key
   at `Scope.GLOBAL` **every tick** — `/run config set polling off` takes effect within
   one interval, no restart. Off ⇒ due keys are pushed forward unpolled.
6. `_run_cycle` — `random.shuffle(keys)` (order within a tick must not be stable), then
   per key, with `STAGGER` sleep between them on periodic ticks only.
7. `_poll_key` — opens its **own short-lived** `async_session()` per key, dispatches on
   the namespace:
   - `BOT` → `_friend_scores`: `SessionPool.get(id)` → `endpoints.fetch_friends` →
     `parse_friends` → every non-`None` `recent_score`. One request covers every
     player that bot account holds (~5 requests cover the whole user base).
   - `OWN` → `_own_scores`: `PlayerSessionProvider.session_for(id)` →
     `endpoints.fetch_me` → `parse_me` → 0 or 1 `recent_score`. The **only** source of
     pure/far/lost.
8. `_store` (`poller.py:237`) — for each result: `resolve_chart` → `difficulty_id`
   (see [[chart-resolution|Chart Resolution]]), then `observations.record(result)` for **every** play,
   then `ScoreStore.ingest`, then **`db.commit()`** (ingest does not commit).
9. `finally:` `schedule.reschedule(keys)` for every **attempted** key, then
   `coordinator.mark_cycle_done(covered)` — only keys that genuinely succeeded.

## Failure modes

| Failure | Where it surfaces | User-visible result |
|---|---|---|
| One key's `ArcaeaError` | `_run_cycle:137` — logged, key left **uncovered** | Other keys unaffected; that key's `/recent` waits out the timeout and serves stale |
| Whole cycle raises | `run:91` `except Exception` — logged, retried next tick | Nothing recorded this tick; schedule still advances (the `finally`) |
| Bot account no longer active | `_friend_scores:204` returns `[]` | Key stays covered, no plays |
| Own credential terminally 403s | `_own_scores:230` `InvalidCredentials` → `provider.handle_invalid(account)` then **re-raises** | Owner is DM'd once; `is_valid=False` was already persisted in the adapter's own transaction, so the credential drops out of the next sweep on its own |
| Poller wedged | `request_refresh` `_WEDGED_POLLER_TIMEOUT = 20 s` | `/recent` warns in the log and renders whatever the DB has |
| Refresh budget empty | `_RefreshBudget.spend` sleeps ≤ `1/rate` | `/recent` is slower; **this is the system working**, not a fault — do not log it as one |
| Unknown `arc_user_id` / tracking off | `ScoreStore.ingest` skips | No row. `/recent` still renders from `ObservationCache` |
| Chart unresolved | `resolve_chart` → `None` | Play stored with NULL FK; embed drops song/jacket/rating and shows the unresolved note; reconcile backfills later |

## Ordering constraints

- **`observations.record` before `ingest`, unconditionally.** The cache is filled for
  *every* observed play, tracked or not — that is what lets `/recent` have no tracking
  branch. Storing then deleting a play to render it is explicitly wrong: it leaks on a
  crash and fires the live-poster "new play" signal on the way through.
- **`resolve_chart` before `ingest`.** `ingest` writes `difficulty_id` verbatim; it does
  not resolve.
- **`db.commit()` after `ingest`.** `ingest` deliberately does not commit.
- **`reschedule` and `mark_cycle_done` in a `finally`.** A key left due in the past is a
  key the loop busy-spins on.
- **`mark_cycle_done` takes only *covered* keys.** Stamping a failed key fresh makes the
  next `request_refresh` for it return instantly on data that was never fetched.
- **Targets are polled as named, never filtered against the `pollable` snapshot** — that
  snapshot predates the wake, so filtering would drop an account registered while the
  loop slept. A key with no usable session costs one no-op DB read.
- **`reschedule` skips keys not already on the schedule.** A targeted refresh may name a
  tracking-disabled account; it must not thereby rejoin the sweep.
- **The tracking filter lives in `_pollable_keys`, not in
  `PlayerSessionProvider._pollable`** — `session_for` shares that, and moving the filter
  down would break on-demand refresh for opted-out accounts.

## The two off switches

| Switch | Level | Stops | Read where |
|---|---|---|---|
| `polling` config key | bot-wide | **fetching**, periodic only | `poller._polling_enabled`, every tick |
| `arcaea_accounts.tracking_enabled` | per account | **recording** | `ScoreStore.ingest` |

Neither stops on-demand refresh. An opted-out account is still fetchable, which is the
whole reason `/recent` works for it.

## `/recent` read-back

After `request_refresh` returns, `/recent` reads **two** sources and takes the newer by
`time_played`: the stored `PlayScore` row, and `ObservationCache.latest(arc_user_id)`.
They agree for a tracked account. For an opted-out one, nothing was stored, so the cache
is the only place the play exists — rendered from a `PlayScore` built by `row_values`
and **never added to the session**.

Path choice (`recent.py:119`): own if a valid `PlayerCredential` exists (one request,
and the only path with pure/far/lost), else `SessionPool.poll_key(account)`. `None` from
both means strayed or slot released → plain error.

## Related

[[scores]] · [[chart-resolution|Chart Resolution]] · [[sessions]] · [[session-lease|Session Lease]] ·
[[players]] · [[live-updates|Live Updates (poster)]] · [[d-score-zero-is-real]] ·
[[w-third-auth-envelope]] · [[h-recent-duplicate-suppression]] ·
[[h-live-update-post-filters]]
