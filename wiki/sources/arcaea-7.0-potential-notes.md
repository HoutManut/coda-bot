---
type: source
status: active
path: (no archived file — first-party social post, not a design doc)
url: https://x.com/arcaea_en/status/2091314523604955307
lines:
dated: 2026-08-28
verified: 2026-08-28
supersedes: []
superseded_by: []
created: 2026-08-28
updated: 2026-08-28
tags: [source, arcaea, potential, ptt, 7.0]
aliases: ["Arcaea 7.0 potential patch notes (tweet)"]
---

# Arcaea 7.0 — Potential rework (official tweet)

## Covers

First-party announcement of update 7.0's potential/PTT rework, posted by the official
`@arcaea_en` account — the studio's primary channel for change announcements (owner-confirmed,
not a fan translation). Grade for every claim below is **DEV-STATED**: first-party and
authoritative on *what changed*, but not a wire capture — no exact magnitudes, formula constants,
or field-level detail. Supersedes [[arcaea-potential]] on every point it touches; still needs a
live-wire pass before any number from here goes into code.

## Key claims

- **DEV-STATED**: "Top Rated Recent Plays" (r10) is removed from the potential formula.
- **DEV-STATED**: "Potential can no longer be lost due to song play" — stated as a deliberate
  design goal ("allowing for songs to be challenged without a decrease"), not merely an
  implementation detail. Logical consequence of r10's removal: a best-N pool (see next claim) is
  monotonic by construction — the same property that already made b30 (never r10) safe to expose
  unconditionally. See [[potential|Potential]] §Traps' old "b30 works on any tier" framing, which
  this generalizes to the whole formula.
- **DEV-STATED**: potential is now based on the **best 50** scores ("songs"), not 30.
- **DEV-STATED**: the **top 10** of those plays have their potential contribution **doubled**.
- **DEV-STATED**: **obtaining a Clear** slightly **increases** the potential value of a score
  (previously play rating was a pure function of score + CC, independent of clear status).

## Not stated — still open

- The resulting divisor. Best guess by analogy with the old `(b30+r10)/40 = 30+10` shape:
  `(sum(best_50) + sum(top_10)) / 60`. **Not in the tweet — inferred, unverified.**
- Magnitude of the clear bonus ("slightly").
- Which `clear_type` values count as "obtaining a Clear" — presumably anything but `track_lost`
  (`clear_type == 0`), but not confirmed; a hard-gauge loss is `clear_type==0` so by that reading
  gets no bonus, consistent with it never having been eligible for anything before.
- Whether "best 50 songs" is per-chart-best exactly like today's `B30Service` (max score per
  `(song_id, difficulty_class)`), or some other unit.
- No accompanying image/table was retrievable (X blocked an automated fetch of this URL,
  HTTP 402) — if the original tweet carried a graphic with exact numbers, it isn't captured here.

## Contradicts / reversed by

Reverses [[arcaea-potential]] on every point above: that source's r10 mechanic, its `/40`
divisor, its recent-30 admission table, and its "play rating is a pure function of score+CC"
claim are all **pre-7.0** and now historical. [[arcaea-potential]] is not rewritten or deleted —
see [[potential|Potential]] §Historical: pre-7.0 model for the archived research it fed (the
2026-07-23 recent-30 admission testing), which was real, correct work against a mechanic that no
longer exists live.

## Feeds

[[potential|Potential]], [[h-7.0-potential-rework]], [[d-r10-impossible-friend-path]],
[[h-recent-config-ptt-b30-r10]]
