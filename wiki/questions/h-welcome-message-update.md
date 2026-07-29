---
type: question
status: answered
blocks: ["registration welcome DM content"]
source: conversation 2026-07-23
created: 2026-07-23
updated: 2026-07-23
tags: [question, registration]
aliases: ["What should the post-registration welcome message say now?"]
---

# What should the post-registration welcome message say now?

## Why it is open

Smallest of the four surface-feature asks filed 2026-07-23 — the send path
itself is not in question (the welcome DM already sends correctly; an
earlier "phantom success" read of it turned out to be a misread, not a bug).
Open part is purely content: what the message should say now that more
of the bot is built (score tracking, live updates) than when the current copy
was written.

## What would answer it

- Decide whether the welcome message should explain the live-update
  destination pick ([[live-updates]] — guild allowlist + user pick,
  default-on to DM) inline, or stay minimal and point at a help command.
- Draft copy following the existing truthful-UX-copy rule: assert only what
  holds for every registration outcome the message covers, no overclaiming.

## Current best guess

Likely just a copy change once scope is picked — low research needed relative
to the other three.

## Answer

Answered 2026-07-23, shipped in `_send_welcome` (`src/coda/extensions/register.py`):
stayed minimal, but explicit — the embed calls out both defaults inline rather
than pointing at a help command, since tracking and live updates now default
oppositely (tracking on, live updates off) and that asymmetry is exactly what
a new user needs told to them, not looked up. It goes further than "explain
the destination pick": when the invoking channel is already allowlisted
(`LiveUpdateService.is_allowed`), an inline button turns live updates on for
that channel in one click; otherwise the text points at `/liveupdates on` /
`channel`. Full detail: [[registration|Registration]] §Post-registration
welcome, [[live-updates|Live Updates (poster)]].

Also corrects this page's own stale framing — the title's "welcome DM" label
predates the DM path being dropped (see [[registration|Registration]]'s
`_send_welcome` docstring); the message is ephemeral and in-channel, not a DM.
