---
type: flow
status: active
entrypoint: "poller._store -> poster.submit -> poster.run"
touches: [scores (poller/embed/poster), players (live.py), db (play_scores, live_update_channels, live_update_prefs, player_links)]
created: 2026-07-29
updated: 2026-07-29
verified: 2026-07-28
grade: A
tags: [flow, live-updates, score-tracking]
aliases: ["Live Updates Poster", "Live Updates — Poster"]
---

# Live Updates — Poster

Split out of [[live-updates|Live Updates (poster)]] 2026-07-29 (that page had grown past the
vault's 300-line soft threshold — see `meta/lint-report-2026-07-29.md`). Covers the poster
module itself: hand-off from the poller, task lifecycle, routing, ordering/stagger, and
attribution. Trigger/gate filter logic and its storage live in
[[live-updates-filters|Live Updates — Filters]]; `/recent` duplicate suppression lives in
[[live-updates-suppression|Live Updates — Suppression]].

---

## Poster

New module `src/coda/scores/poster.py`. Its input is plays and it starts next to
the poller, so it belongs in `scores/`; it *reads* destinations from
`players/live.py` rather than living there.

### Hand-off from the poller

`poller._store` (`poller.py:252-272`) currently drops `new_plays` on the floor.
After `db.commit()`, it hands the poster **row ids** — not `ScoreResult`s, not
ORM objects: the poller's session is short-lived by design (`poller.py:194`) and
any row it returns is detached moments later. The poster opens its own session.

This requires `ScoreStore.ingest` to return ids. `_upsert` already uses
`RETURNING` on both branches (`service.py:117`, `service.py:132`) — add
`PlayScore.id` to each and thread it up. `ingest`'s only caller is `_store`, so
the change is contained.

Submission is **non-blocking**: a bounded `asyncio.Queue` (maxsize ~256) with
`put_nowait`; on `QueueFull`, log and drop. A wedged poster must never stall the
poll loop, and the queue can only fill if the poster is already broken.

### Task lifecycle

Started in `bot.py`'s `StartingEvent` handler alongside `poller.run` and
`reconcile.run_reconcile_loop` (`bot.py:48-56`) and appended to
`background_tasks`, so the existing `StoppingEvent` cancel/gather handles
shutdown unchanged.

### Routing, per play

1. Load the row + chart + song in the poster's own session.
2. `row.arcaea_account_id` → all `PlayerLink` rows. No links → skip silently.
   **The poster never touches `bot_account_id`** — that identifier does not leave
   `sessions/pool.py` ([[w-sid-confined-to-sessions]], `keys.py:9-12`).
3. Per linked `discord_id`: `resolve_destination(db, discord_id)` →
   `(enabled, channel_id)`. Not enabled → skip. `channel_id is None` → DM.
   The poster **trusts** that result and does not re-check the allowlist.
4. Channel destination → `floor_for(db, channel_id)`
   ([[live-updates-filters|Live Updates — Filters]] §The guild floor).
5. Evaluate filters for that user
   ([[live-updates-filters|Live Updates — Filters]] §Evaluation order), reusing
   the per-play fact cache.
6. Collect the destinations that passed and **deduplicate** them (below) — one
   message per destination, never one per linked user.
7. Per surviving destination: check the `/recent` suppression marker
   ([[live-updates-suppression|Live Updates — Suppression]]).
8. Build the embed with
   `score_embed(row, chart, song, locale=..., night=..., player=...)`
   (`embed.py:39`, `player` added per §Whose play is it below). **Do not write a
   second score format.**
9. Send: channel → `app.rest.create_message`; DM → `send_dm(app, discord_id, …)`
   (`utils/dm.py:13`), which already swallows `ForbiddenError` on closed DMs and
   returns `None`.

### Ordering and stagger

- **Sort each submitted batch by `time_played` ascending** before enqueueing.
  The feed must reflect when plays happened, not iteration order — one
  friend-path cycle can yield many plays at once.
- **Same-destination sends are spaced; different destinations run in parallel.**
  One `asyncio.Lock` per destination key (`channel_id`, or `("dm", discord_id)`),
  one task per post. `asyncio.Lock` waiters are FIFO, so per-destination order is
  preserved without a queue per destination. Each post takes the lock, sleeps
  only long enough to keep ≥ `SPACING` (~5 s) since that destination's last send,
  sends, records the time.
- **`INITIAL_DELAY` (~3–8 s, jittered) before the first send of any play.** It
  costs nothing on a feed already minutes behind the wire, and it closes the
  `/recent` race in [[live-updates-suppression|Live Updates — Suppression]] with
  no extra mechanism.
- Lock/timestamp dicts grow with distinct destinations. At <50 people that is
  bounded — do not build a reaper for it.
- **No cross-cycle dedup is needed.** `ingest` returns first-inserts only, so a
  play is offered exactly once, ever.

### Whose play is it

`/recent` never needed to say — Discord's own interaction header attributes the
reply to the invoker. A live post is bot-authored with no such header, so in a
channel following several players a bare score embed says nothing about who
played it. The poster must supply the attribution itself.

**Small avatar + name via `embed.set_author(name=…, icon=…)`.** It renders as one
compact line above the title, which is the right weight — the play is the
content, the player is context. Mechanically: optional `player: PlayerIdentity |
None = None` on `score_embed`, set when given. One format, no second builder;
`/recent` passes nothing and is unchanged.

**Which Discord user: the owner link.** A play belongs to an `ArcaeaAccount`,
which may carry several `PlayerLink` rows, so "the recipient" is not a
stable answer — the same play could show two different faces in two channels.
`is_owner` is unique per account and is already how `notify.py:47-52` picks who
speaks for an account.

Identity is read from `app.cache.get_user(discord_id)` — `display_name` plus
`display_avatar_url`. A cache miss falls back to one `rest.fetch_user`. Guild
nicknames and per-guild avatars need a member fetch and are **not** used: one
identity for every destination keeps the feed consistent and costs no extra
requests.

Fallback chain when there is no Discord identity to show — no owner link, or the
fetch fails:

1. owner link's Discord `display_name` + avatar
2. the recipient's own Discord identity (DM destinations always have one)
3. **`ArcaeaAccount.display_name`** (`arcaea_account.py:53`) — name only, no
   avatar. The in-game name still identifies the player, and a post that says who
   played beats one that says nothing
4. omit the author line

**Never fall back to `friend_code`.** It is how anyone adds the player in-game;
publishing it to a channel is a disclosure the user never consented to by
enabling live updates. An identity lookup must never block or drop a post —
every step above degrades to the next one.

**Send once per destination, not once per linked user.** Two users linking one
account and both pointing at the same channel would otherwise put two messages in
that channel for one play. Evaluate filters per linked user as designed, then
post to the **union of the destinations that passed** — deduplicated. That
keeps both users' preferences intact while the channel sees one message. It also
makes the author line unambiguous, since attribution no longer depends on which
linked user triggered the send.

---

## Related

[[live-updates|Live Updates (poster)]] · [[live-updates-filters|Live Updates — Filters]] ·
[[live-updates-suppression|Live Updates — Suppression]] ·
[[scores|scores (module)]], [[score-poll-loop|Score Poll Loop]],
[[chart-resolution|Chart Resolution]], [[b30]], [[registration|Registration]]
