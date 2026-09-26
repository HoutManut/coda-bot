---
type: domain
status: active
source: 2024 prototype (`classes/chardle.py`, `plugins/chardle.py`, 2024-09/10, archived outside this repo) + design session 2026-07-27
verified: 2026-07-28
created: 2026-07-29
updated: 2026-07-29
tags: [domain, chardle, game]
aliases: ["Chardle Discord Surface", "Chardle — Discord Surface"]
---

# Chardle — Discord Surface

Split out of [[chardle|Chardle]] 2026-07-29 (that page had grown past the vault's 300-line
soft threshold — see `meta/lint-report-2026-07-29.md`). Covers where a Chardle board and its
daily scoreboard live in Discord: the guild Chardle channel, the daily scoreboard message,
and the transport chain a board falls back through. Clue-column mechanics live in
[[chardle-clue-columns|Chardle — Clue Columns]]; pool/stats/rules live in
[[chardle-mechanics|Chardle — Mechanics]].

## The Chardle channel

A guild admin (**Manage Channels**) can give Chardle a home with `/chardle channel`. One
channel per guild — `chardle_channels.guild_id` is the primary key, deliberately unlike the
live-update *allowlist*, because the scoreboard needs exactly one place to live and "threads
go under it" means nothing if there are several. Running the command with no option shows the
current channel and offers a Clear button.

When one is set it becomes the **parent of every Chardle thread** and the home of the
**daily scoreboard**. Threads go there from *any* channel the command was typed in.

**It never moves an inline board.** A free-play board started with `thread: No thread` posts
in the channel it was started in, wherever that is. Routing those to the Chardle channel too
would collide with [[h-chardle-boards-are-channel-owned]] — one live board per channel means
one live inline board *per guild* if every one of them lands in the same channel.

When none is set, **threads are refused rather than scattered**: `/chardle play` with a
`thread:` option answers with "set a Chardle channel first", and `/chardle daily`, which has
no inline form, falls through to a **DM**. Inline free-play boards are unaffected and work in
any channel.

A player who **cannot see** the Chardle channel is the same problem wearing a different hat —
thread access is inherited from the parent, and being added to a private thread does not
override it, so the board would exist somewhere they can never open. Checked with
`can_view` (VIEW_CHANNEL) before opening anything, and only a *definite* False rejects: a
cold cache is "don't know" and the post itself is the real check. `/chardle play thread:`
refuses, because an inline board in the channel they are standing in is right there;
`/chardle daily` takes the DM leg instead, because it has no inline form to fall back to.

That check can only ever fire **one player at a time, at play time**, so `/chardle channel`
asks a second question up front: can **@everyone** see the channel being set? The per-member
check is useless here — the caller is an admin, who can see everything. `everyone_can_view`
reads the @everyone role's baseline and that channel's @everyone overwrite, and a `False`
appends a warning to the confirmation. It **warns and does not refuse**: "@everyone denied,
Member allowed" is an ordinary server, and the check cannot tell whether that role covers
every player. Re-run on every `/chardle channel` with no argument too, since a channel can be
locked down long after Chardle was pointed at it.

## The daily scoreboard

One message per puzzle number in the Chardle channel, **edited in place** and carrying a
`Play today's Chardle` button. It lists everyone who opened today's daily *in this guild*:
who is still playing (guess count only), and each finished player's emoji grid — the same
grid `render.cells` draws on their own board, so the two can never drift.

It is spoiler-safe by the same argument as the share string: the grid carries no information
about the answer, and a daily's column set is identical for everyone. A **live** board shows
no grid, because an unfinished grid also says how many attempts are left.

Refreshed when a daily opens, when one finishes, and by the half-hourly sweep — which is what
posts a fresh board after rollover in a guild where nobody has played yet. Not pinned: a new
message per day would fill Discord's 50-pin limit inside two months.

A daily played in **DMs** has `guild_id IS NULL` and does not appear on any guild's
scoreboard. Lifetime stats stay location-independent; only this display is scoped.

## Where a board lives

A **daily board is never posted in the open channel.** In a guild it lives in a **private
thread** the bot creates and adds the player to; in a DM the DM channel itself serves. The
thread is **reused per (guild, player)** rather than created per puzzle — one
`Chardle — <player>` thread that every new daily is posted into. The thread id is stored in
`chardle_player_threads`; reuse re-validates that the channel is still a thread, still hangs
off the current parent, and unarchives it if Discord archived it overnight.

A free-play board takes `/chardle play thread: none | public | private`. `none` posts it in
the channel (the Chardle channel if one is set, else where the command was typed); the other
two open a thread under that same parent. A thread has its own channel id, so several
free-play boards coexist where `UNIQUE (channel_id) WHERE state = 'playing'` would otherwise
allow one. When the board does not land where the command was typed, the ephemeral reply
links to it — `/chardle guess` looks up by the invoking channel and would find nothing.

Transport chain: **private thread → DM → ephemeral.** Ephemeral is a last resort and a
poor one: an interaction token dies after 15 minutes, so an ephemeral board cannot be
edited for the hours a daily lives and has to be re-rendered in full on every guess. A
threaded or DM board is a real message, edited in place for as long as the game runs, and
it keeps the reply input path working.

Free-play boards are the opposite — posted where they are played, because there the
channel *is* the owner ([[h-chardle-boards-are-channel-owned]]).

The parent channel is told nothing: a private thread fires no `THREAD_CREATED` system message
and is visible only to its members (verified against Discord's docs 2026-07-27 —
[[h-chardle-boards-are-channel-owned]] §A daily is private). It is still not a privacy
*guarantee*, because anyone holding `MANAGE_THREADS` can join one. So a daily also checks that
the guesser **is** the session's owner. Location narrows the audience; the check is what
enforces it.

## Related

[[chardle|Chardle]] · [[chardle-clue-columns|Chardle — Clue Columns]] ·
[[chardle-mechanics|Chardle — Mechanics]] ·
[[h-chardle-boards-are-channel-owned]] · [[h-chardle-puzzle-number-not-date]]
