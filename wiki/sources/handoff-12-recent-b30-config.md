---
type: source
status: active
path: "(none — authored directly in this session, not ingested from an archived doc)"
lines: 165
dated: "2026-07-23"
verified: 2026-07-23
supersedes: []
superseded_by: []
created: 2026-07-23
updated: 2026-07-23
tags: [source, handoffs, b30, recent, landed]
aliases: ["12 — recent b30 config"]
---

# 12 — /recent b30 stat config

## Covers

Design + file-by-file implementation spec for surfacing [[handoff-09-b30|b30]]'s
compute backend (`B30Service`, built 2026-07-23, `src/coda/scores/b30.py`) in
the `/recent` embed, gated by a new per-user `/config` option. Depends on
nothing unbuilt (poller landed, b30 backend landed). **Landed 2026-07-23** —
built as specced, in `scores/b30_stat.py` plus the config key, the
`exclude_score_id` param, and the rating-observation plumbing. One open point
survives: the "target" reading flagged below was implemented as the
30th-place chart rating, unconfirmed against original intent.

## Decisions made this session

1. New enum config key `recent_b30_stat`, four values: `never`,
   `on_b30_change`, `on_b40_change`, `always`.
2. The displayed number is **b30 sum / 30** (an average, PTT-scale ~0–13),
   not the raw sum (~300–600 for a strong player). Matches the worked
   example given for this feature (`13.12345 -> 13.12456`) and the
   project's existing "always divide by a fixed pool size" convention
   ([[potential]] §5, same logic applied to a 30-slot pool instead of 40).
3. Before/after diff is computed **exactly**, not approximated, by
   extending `B30Service.compute()` with an `exclude_score_id` param.
   Storing a cached rating instead was raised and considered, then dropped:
   it reopens the exact staleness bug [[h-b30-cache-stores-sum]] already
   rejected (a chart's CC can refine with no new play, silently staling a
   stored number) and needs a migration plus an ingest-path hook, for no
   accuracy gain over one extra indexed query issued only on demand.
4. Hidden-rating or opted-out accounts: **never** show the stat, regardless
   of `recent_b30_stat`'s value — show a fixed "unavailable" line instead.
   Checked **live, every call**, never cached — the point is catching a
   mid-session toggle (user turns the display on, then hides their rating
   in-game; next `/recent` must reflect that immediately). When the current
   rating can't be freshly confirmed either way, fail **closed** (treat
   "don't know" the same as "hidden") — privacy safety over completeness.
   The same suppression applies to `tracking_enabled=False` accounts, by
   explicit instruction — not just PTT-hidden ones.

## Config key

`src/coda/settings/registry.py` — add one `REGISTRY` entry. Mirror
`locale`'s shape (`registry.py:14-21`), not `polling`'s: this is a personal
display preference, not bot-wide.

```python
"recent_b30_stat": ConfigKey(
    name="recent_b30_stat",
    default="never",
    type=("never", "on_b30_change", "on_b40_change", "always"),
    guild_chain=(Scope.USER, Scope.GLOBAL),
    dm_chain=(Scope.USER, Scope.GLOBAL),
    description="Show b30 rating impact on /recent results",
),
```

No other file needs to change for `/config` to expose this — the key/value
choice lists, autocomplete, and enum validation in `extensions/config.py`
are all generic over `REGISTRY` (confirmed by reading that file this
session: `_KEYS_USER` etc. filter on `Scope.X in defn.settable_scopes`, and
`_handle`'s validation checks `isinstance(defn.type, tuple)` generically).

## B30Service: exact before/after

`src/coda/scores/b30.py` — add `exclude_score_id: int | None = None` to both
`compute()` (currently line 62) and `_best_scores()` (currently line 101),
plus one conditional `.where()`:

```python
async def compute(
    self, db: AsyncSession, account_id: int, limit: int = 30,
    exclude_score_id: int | None = None,
) -> B30Result:
    ...
    best_by_chart, unresolved_excluded_count = await self._best_scores(
        db, account_id, exclude_score_id
    )
    ...

async def _best_scores(
    self, db: AsyncSession, account_id: int, exclude_score_id: int | None = None
) -> tuple[dict[int, int], int]:
    query = select(
        PlayScore.song_difficulty_id, PlayScore.wire_song_id,
        PlayScore.wire_difficulty, PlayScore.score,
    ).where(PlayScore.arcaea_account_id == account_id)
    if exclude_score_id is not None:
        query = query.where(PlayScore.id != exclude_score_id)
    rows = await db.execute(query)
    ...  # unchanged from here
```

`PlayScore.id` is the surrogate PK (`db/models/play_score.py:83`). The
caller passes the current play's own `row.id` to get "b30 as if this
specific play never happened." This is exact even when the play *improved*
an already-top30 chart (a cheaper rank-31-backfill approximation was
considered and rejected — it gets that specific case wrong, since it
assumes the chart had no prior top-30 entry at all).

## Rendering logic (new module, e.g. `src/coda/scores/b30_stat.py`)

Called from `src/coda/extensions/recent.py`'s `invoke`, around the existing
`score_embed(...)` call (currently lines 98-104). Append the result as an
extra description line rather than threading a new param through
`embed.py`: `score_embed` is otherwise a pure function of three rows shared
with the live-updates poster, and this stat needs a DB round-trip
`score_embed` doesn't otherwise do.

```python
embed, file = score_embed(row, chart, song, locale=..., night=...)
line = await b30_stat_line(db, b30_service, account, row, chart, config_value)
if line:
    embed.description = f"{embed.description}\n{line}"
await ctx.respond(embed=embed)
```

`config_value` comes from `ConfigService.resolve` (`settings/service.py:17`,
signature `resolve(db, key, *, guild_id, channel_id, user_id, is_dm)`) —
call it exactly the way `extensions/config.py`'s `ConfigView.invoke` does
(`config.py:254-263`) to derive `is_dm`/`guild_id`/`channel_id` from `ctx`.

**Gate order** — cheapest checks first, so a `never`-configured or
ineligible play never touches `B30Service`:

1. `config_value == "never"` → `None` (nothing rendered, no query).
2. `chart is None or chart.rating <= 0` → `None`. Mirrors
   `chart_rating_line`'s existing "(Unknown CC)" skip
   (`catalog/labels.py:70-81`) — if this play's own chart has no computable
   rating, there is nothing to say about its b30 impact.
3. `row.id is None` (account is on the observed-but-unstored path,
   `recent.py:_observed_play`, `row.id` is never set there) **or**
   `not account.tracking_enabled` **or** the freshly-fetched rating for this
   account comes back unknown/hidden (see plumbing section) → show the
   fixed unavailable line, never the computed stat.

If none of the above trip, call `B30Service.compute`:

- `limit = 40 if config_value == "on_b40_change" else 30` — `b30_sum` is
  always the true top-30 regardless of `limit` (per `B30Result`'s own
  docstring), so 30 is enough for `on_b30_change`/`always`; 40 is only
  needed to detect b40-pool membership for the `on_b40_change` branch.
- `after = await b30_service.compute(db, account.id, limit=limit)`
- `this_entry = next((e for e in after.entries if e.song_difficulty.id == chart.id), None)`
- `in_top30 = this_entry is not None and this_entry.counts_toward_b30`

**If `in_top30`** (this play is currently the chart's best score, and that
score ranks in the top 30 by rating):

```python
before = await b30_service.compute(db, account.id, limit=30, exclude_score_id=row.id)
before_avg, after_avg = before.b30_sum / 30, after.b30_sum / 30
if before_avg == after_avg:
    line = f"b30: {format_rating(after_avg)}"
else:
    delta = after_avg - before_avg
    line = f"b30: {format_rating(before_avg)} → **{format_rating(after_avg)}** (+{format_rating(delta)})"
```

`format_rating` (`utils/scoring.py:78`) already defaults to 5 decimal
places and trims trailing zeros — exactly the precision in the worked
example (`13.12345 -> **13.12456**`), no new formatter needed. Arrow style
`→` matches `chart_rating_line`'s existing convention
(`catalog/labels.py`).

**Else (not in top30)** — behavior depends on config:

- `on_b30_change` → `None` (nothing changed, by definition of this option).
- `on_b40_change` and `this_entry is None` (didn't even crack the top 40)
  → `None`.
- Otherwise (`on_b40_change` with `this_entry` present at rank 31–40, or
  `always` unconditionally) → show the 30th-place rating as the target to
  beat:

```python
if len(after.entries) < 30:
    line = "-# Not enough rated plays yet to show a b30 target."
else:
    target = after.entries[29].play_rating
    line = f"b30 target (30th place): **{format_rating(target)}**"
```

This reading unifies the two ways this case was described in-session —
"shows the rating for b30th as target" (the config option's description)
and "if play is above [i.e. didn't change it] just show the user b30
there" (the embed-field description) — both taken to mean the same number:
the current 30th-place chart rating, not the aggregate sum. **Flag this for
confirmation** if the actual intent was two distinct numbers, since the
two messages that specified it used different words for what may or may
not be the same value.

**Unavailable line** (hidden rating, opted-out, or unstored observation):

```python
_UNAVAILABLE = "-# b30 stat unavailable — hidden rating or tracking off."
```

One line, true under either cause, no guessing which one applies — matches
this project's existing UX convention of not overclaiming a specific
reason when several could apply.

## Hidden-rating plumbing (new work — nothing surfaces this today)

Traced this session (`poller.py`, `observations.py`): the account's live
PTT rating (`Me.rating` / `Friend.rating`, `None` for the wire's `-1`
hidden-sentinel, per [[d-ptt-hidden-sentinel]]) **is already fetched on
every refresh cycle** — `parse_me`/`parse_friends` decode it — but it is
discarded before it reaches anything `/recent` can read
(`poller.py:207` and `poller.py:228-233`). No new API call is needed; the
new plumbing is:

1. **`src/coda/scores/observations.py`** — add a second cache, keyed the
   same way as `_entries` but not gated on `time_played` (rating isn't a
   play, it has no ordering to guard against):

   ```python
   def record_rating(self, arc_user_id: int, rating: float | None) -> None:
       self._ratings[arc_user_id] = (rating, monotonic())

   def latest_rating(self, arc_user_id: int) -> tuple[float | None, bool]:
       """(rating, was_observed). was_observed=False means unknown/expired --
       treat the same as hidden (fail closed), never the same as visible."""
       entry = self._ratings.get(arc_user_id)
       if entry is None:
           return None, False
       rating, recorded_at = entry
       if monotonic() - recorded_at > TTL:
           del self._ratings[arc_user_id]
           return None, False
       return rating, True
   ```

   A plain `float | None` return can't distinguish "confirmed hidden" from
   "never fetched" — the `was_observed` flag is what the fail-closed gate
   in the rendering logic above actually needs.

2. **`src/coda/scores/poller.py`** — `_friend_scores` (line 199-207) and
   `_own_scores` (line 210-233) currently discard `Friend.rating` /
   `Me.rating` right after parsing. Change both to also return a
   `dict[int, float | None]` of `arc_user_id -> rating`:
   - own path: one entry, always, regardless of whether `recent_score` is
     `None`.
   - friend path: **every** friend, not just ones with a `recent_score` —
     the current filter at line 207
     (`[f.recent_score for f in friends if f.recent_score is not None]`)
     drops friends without a recent play entirely, which would silently
     drop their rating too if captured after that filter instead of
     before it.

   Thread the dict through `_poll_key` (line 178-196) into
   `observations.record_rating(...)` calls, right next to the existing
   `_store(...)` call — this doesn't need to go through `_store` itself,
   rating has nothing to do with chart resolution or ingest.

3. **`src/coda/extensions/recent.py`** — read
   `observations.latest_rating(arc_user_id)` in the same place it already
   reads `observations.latest(arc_user_id)` (line 92), pass the result
   into the new `b30_stat_line` call.

## Verification

- `uv run alembic check` — should report no drift (no schema change here).
- Manual: set `/config user recent_b30_stat always`, play a chart that's
  clearly outside your top 30, run `/recent`, confirm the target line shows
  and matches a hand-computed `B30Service.compute` call for the same
  account (no `/b30` command exists yet to cross-check against directly).
- Play a chart that beats an existing top-30 entry, confirm the arrow+delta
  line, and sanity-check the delta by hand:
  `(new_chart_rating - old_chart_rating) / 30`.
- Toggle the game's in-game "hide rating" setting on a test account,
  confirm `/recent` falls back to the unavailable line on the very next
  call — no stale "visible" state lingering. This specific behavior can't
  be checked by reading code alone, it needs a live wire round-trip.
- Set `tracking_enabled=False` on a test account, confirm the same
  unavailable line, not a stale/partial b30 number left over from before
  opt-out.

## Feeds

[[scores]], [[handoff-09-b30|09 — b30]] (this is its `/recent`-facing display
half), [[h-b30-cache-stores-sum]] (reaffirms the no-cache decision against
this session's own proposal to reconsider it), [[d-ptt-hidden-sentinel]],
[[h-recent-config-ptt-b30-r10]] (the open question this closes — update or
close it once this lands).
