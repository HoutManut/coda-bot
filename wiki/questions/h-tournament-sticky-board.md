---
type: question
status: open
blocks: [tournaments — /tournament board, board.py]
source: spot check 2026-09-03 (handoff 13 review)
created: 2026-09-03
updated: 2026-09-03
verified: 2026-09-03
tags: [question, tournaments]
aliases: ["Should the match board be sticky?"]
---

# Should the match board be sticky?

## Why it is open

**Owner ruling 2026-09-03: yes** — a sticky mode, where the old board message is deleted
and a brand new one posted. The shape is decided; nothing is built. This page collects
what that rework should absorb, because every item below lives in the two files it will
already be editing.

Sticky reverses [[tournaments-module]]'s current stance — "a lost message is recovered by
`/tournament board`, never by an automatic repost: a repost loop would fight the
conversation the thread exists to host". That reasoning was about *reposting on failure*,
not about a deliberate move to the bottom, so the two can coexist; the page should say
which one applies when.

## What the 2026-09-03 beat work changed underneath it

[[h-tournament-window-and-clock]] shipped `announce.py`, which splits the thread in two:
**the board is state and is edited; a *moment* is a new message.** A round now posts two
beats — the chart being revealed, and the round being decided — and each is a plain
`create_message` that pings the roster. That closes the "nothing notifies" hole *without*
sticky, so sticky is no longer load-bearing for it.

**Owner direction 2026-09-03 reverses the ruling below**: the old board is **kept, not
deleted**, and its controls stripped — so the thread reads back as a match log. Item 3's
permission gate and items 4–5 stand unchanged.

Two things the rework should now do rather than the ones it was going to:

- **Post the board *as* the beat, not beside it.** Once the board moves down on its own,
  a separate beat message and a re-posted board are two narrations of one moment. The
  seam is already in place: `service.Tick` carries `touched` (edit) and `beats` (post)
  separately because they fail separately, and `BoardService` has `refresh` and `say` to
  match. Merging them is a change to what `say` sends, not a rewrite.
- **Move only on a beat.** A within-beat change — a countdown ticking, a score landing, a
  pick/ban selection — must stay an edit. A board that reposts every 5 s tick is the
  "repost loop fighting the conversation" the module page warned about; a board that
  reposts when something *happens* is a human running a match.

Stripping the old board's controls needs the view **as it was at that beat**, which no
caller holds today — `render.board` would have to take the rows off, or the handler gate
on `interaction.message.id == match.board_message_id`. The second is one comparison and
also covers a board that predates a restart.

## What it should absorb

### 1. `/tournament board` can destroy the pointer it was meant to fix

```python
match.board_message_id = None
posted = await boards.post(ctx.client.app, db, match)
await db.commit()
```

`BoardService.post` returns `None` on `HikariError` without writing the field, so a failed
repost commits the null — and `refresh` returns immediately on `None`, so the *working*
board it was invoked to replace goes dead permanently. The pre-clear buys nothing: `post`
already assigns on success.

### 2. The old board is an orphan with live controls

Component ids are stateless by design (`tourney:<action>:<id>`), which is what lets a match
outlive a restart. It also means a superseded board's Ready button and pick/ban select keep
working while only the newest message is ever redrawn. Deleting the old message — the
sticky behaviour — is what closes this.

### 3. No permission gate

`Board` is the only `/tournament` verb with no `_may_run` check, so anyone in the thread
can repost at will.

### 4. `refresh` snapshots outside its lock

```python
rendered = render.board(await viewbuild.build(db, match))   # outside
async with self.lock(match.id):
    await app.rest.edit_message(...)
```

The lock releases waiters FIFO, but the view is built *before* acquiring, so the sweep and
a pick/ban click can build at t₁ < t₂ and land t₂ then t₁ — the board sits a tick stale
until something else changes it. The module docstring's "ordering is free" only holds once
the read moves inside.

### 5. Locks are never released for a match that closes normally

`BoardService.release` is called from exactly one place, `Cancel`. Every match that reaches
`closed` leaves its `asyncio.Lock` in `_locks` for the life of the process. Separately,
`release` during an in-flight acquire pops the entry and lets the next caller mint a
*second* lock for the same match.

### 6. Two things `render.py` does not say

`_entry_line` names who **banned** an entry but not who **picked** it, though
`acted_by_side` is already on the view and whose pick a round is, is standard tournament
information. And a drawn match closes silently: `_winner` returns `None` when the tally has
tied leaders, so a Bo3 that ends 1–1 on a tied decider prints the score line and stops,
with no 🏆 and nothing saying it is over.

## What would answer it

The sticky implementation itself. Items 1–3 are the command, 4–5 are `board.py`, 6 is
`render.py`; none needs a decision beyond the one already made.

## Current best guess

Delete-then-post, with the delete best-effort and the post authoritative — the failure mode
to avoid is item 1's, where a half-done repost leaves the match with no board at all. So:
post first, then delete the old id, then commit. Marked as a guess.

## Answer

Unanswered.

## Related

[[tournaments-module|tournaments (module)]] · [[tournaments|Tournaments]] ·
[[h-tournament-one-match-per-thread]] · [[h-tournament-window-and-clock]] ·
[[h-spoiler-is-a-render-mode]]
