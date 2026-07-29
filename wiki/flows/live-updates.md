---
type: flow
status: planned
entrypoint: "poller._store's new_plays (hook point, not yet called)"
touches: [scores (poller/embed), players (live.py), db (play_scores, live_update_channels, live_update_prefs, player_links)]
created: 2026-07-21
updated: 2026-07-21
tags: [flow, live-updates, unbuilt, score-tracking]
aliases: ["Live Updates (poster)", "Live Updates"]
---

# Live Updates (poster)

**Status: NOT BUILT.** This is the last unbuilt piece of score tracking — the
poller (both read paths), score storage, chart resolution + reconcile, and
`/recent` all landed 2026-07-21 (handoff 07, deleted per the "delete once it
lands" rule). Nothing turns a new play into a Discord message yet.

## Trigger

Intended trigger: `poller._store`'s `new_plays` — the poller already computes
this list per polled key and currently drops it on the floor
(`src/coda/scores/poller.py`). A cycle polls **one key at a time** on its own
short-lived DB session (`poller._poll_key`), so the poster would be handed one
key's plays, not a whole sweep's.

Two pieces already exist with **zero callers**, both built for this flow:

- `ScoreStore.ingest` — returns exactly the genuinely-new first-insert plays
  that should be posted; enrichment (a friend sighting filling in an existing
  own-tier row) stays silent (`src/coda/scores/service.py:58-62`).
- `LiveUpdateService.resolve_destination(db, discord_id) -> (enabled, channel_id)`
  — labelled "the poller's entry point" (`src/coda/players/live.py:114`).

## Path (as designed, not yet built)

1. `poller._store` calls `ScoreStore.ingest` per polled key → `new_plays: list[ScoreResult]`.
2. **Poster routing** (per new play):
   1. `arc_user_id → ArcaeaAccount.id`. The poster works from `arc_user_id`,
      **never** the bot account — `bot_account_id` must not leak past
      `sessions/pool.py` (`pool.py:8-11`).
   2. `ArcaeaAccount.id → all PlayerLink rows for it` — many Discord users can
      link one account, so a play may notify more than one person. No links →
      skip silently.
   3. For each linked `discord_id`: `resolve_destination(db, discord_id)` →
      `(enabled, channel_id)`. Skip if `enabled` is False.
      `channel_id is None` → DM (create/lookup via `rest.create_dm_channel`);
      else post to the channel. `resolve_destination` already falls back to DM
      when a stored channel drops off the allowlist (`live.py:119-136`) — the
      poster trusts its result and does not re-check.
      `DEFAULT_ENABLED = True` (`live.py:26`): a registered user with no pref
      row still resolves to `(True, None)` — DM on by default.
3. **Build the embed** — reuse `score_embed(row, chart, song, *, locale, night)`
   from `src/coda/scores/embed.py`. **Do not write a second score format.**
   It already handles title/colour/jacket, score with PM + distance-from-max,
   CC → play rating, own-path pure/far/lost, a `<t:…:R>` stamp, and an
   unresolved-chart note. It takes a `PlayScore` row, not a `ScoreResult`, so
   the poster re-reads the inserted rows (or ingest grows a row-returning
   variant).
4. **Stagger and order same-destination bursts**, then send via `hikari.RESTAware`
   (`app.rest`, matching `players/notify.py`).

## Filters — NOT DESIGNED YET

Posting is filtered — not every new play deserves a message — but **the
filter set itself is undesigned**. It is expected to be plural, layered, and
probably user-configurable; design it as its own piece of work when this doc
is picked up. Exactly one filter is settled: *did this play raise the
account's tracked b30?* ([[handoff-09-b30]] §8, filed as [[b30]]).
That filter must use **our** computed b30 sum, never the server's
`reported_rating` (quantized to 0.01 PTT, and permanently NULL for a hidden
player). For a hidden player the flag may fire but the *number* must never be
printed, in any recoverable form. See [[h-live-update-post-filters]].

## Failure modes

| Failure | Where it surfaces | User-visible result |
|---|---|---|
| User blocked the bot / closed DMs | `rest.create_dm_channel` or send fails | That one post is dropped (try/except per post, log, move on) — must not crash the loop or block other destinations |
| Deleted/removed channel | `resolve_destination` already re-validates against the allowlist at post time | Falls back to DM automatically, no cleanup job needed |
| Account with no `PlayerLink` rows | Routing step 2 finds nothing | Silent skip — nobody to notify |
| Friend-path play (thin data) | Embed build | Renders from as little as `(wire_song_id, difficulty, score, time_played)`; own-path detail block omitted entirely, never partially shown |
| Unresolved chart (`song_difficulty_id IS NULL`) | Embed build | Falls back to raw `wire_song_id` + difficulty int; still posts, never drops |
| `/recent` and a live update for the same play race | Both read paths can produce the same score | See ordering below — undecided whether the live update should be suppressed or merely delayed |

## Ordering constraints

- **Same-destination bursts must be staggered**, not dumped simultaneously —
  space them out so a channel reads as a feed, not a flood. Different
  channels/DMs post in parallel; only same-destination bursts are spaced.
- **Order by `ScoreResult.time_played`** (server-assigned ms epoch), ascending
  — the feed must reflect when plays really happened, not ingest/iteration
  order.
- **`/recent` jumps the queue.** As built, `/recent` (`extensions/recent.py`)
  answers its own interaction directly — it awaits
  `coordinator.request_refresh(key)`, then reads and replies, knowing nothing
  about any queue. The precedence point therefore **does not exist yet**; the
  poster is the only side that can hold or reorder, so it must create it.
  Simplest shape: the poster's per-destination stagger already delays its own
  sends, so a live update for a play `/recent` just showed lands after the
  reply on its own, with no extra mechanism.
  **Undecided**: whether that trailing update should then be **suppressed**
  rather than merely delayed — the user already saw the score, and posting it
  again to the same channel reads as a duplicate. See
  [[h-recent-duplicate-suppression]].
- **No double-posting across cycles** — `ingest` returns only first-insert
  plays, so a play appears in `new_plays` exactly once, ever. The poster needs
  no dedup of its own; within one cycle, post each play once per resolved
  destination.

## Related

`[[db]]` (`play_scores`, `player_links`, `live_update_channels`,
`live_update_prefs`), `[[b30]]` (feeds the one settled filter),
`[[h-live-update-post-filters]]`, `[[h-recent-duplicate-suppression]]`,
`[[handoff-08-live-updates-poster]]` (source)
