---
type: question
status: open
blocks: []
source: arcaea-tournament-layer.md
created: 2026-07-21
updated: 2026-09-02
tags: [question, tournaments, wire, low-priority]
aliases: ["How much does the bot's clock skew from lowiro's server clock?"]
---

# How much does the bot's clock skew from lowiro's server clock?

## Why it is open

Score validity for tournaments (`valid(score, round)`, [[tournaments|Tournaments]] §2)
compares `score.time_played` (server-assigned at submission) against a
round's `[start, end]` window drawn from the bot's own clock. The player's
device clock is provably irrelevant — `time_played` is server-assigned and
verified 2026-07-17 against [[arcaea-auth-behavior]] §7.3 — but the
remaining skew between **the bot's clock and lowiro's server clock** is
untested. Both are presumably NTP-synced, so the skew is expected to be
small, but "presumably" is not a measurement.

The source doc marks this explicitly as **"worth knowing, not blocking"** —
window durations start at 200s (`clamp(2t, 200s, 500s)`), which is far above
any plausible NTP skew, so nothing in the current design is fragile to it.

## What would answer it

Compare a captured `time_played` value on a play made at a known local
instant against the bot host's own clock at round-window-computation time.
Not urgent — no round-tightness decision depends on this today.

## Current best guess

Small (sub-second to low-single-digit-seconds), by the NTP-synced assumption
— **unverified, explicitly presumed rather than measured.**

## Answer

Not yet answered. Not blocking anything as of this ingest.
