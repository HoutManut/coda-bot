---
type: question
status: open
blocks: ["/r30 command"]
source: conversation 2026-07-23
created: 2026-07-23
updated: 2026-07-23
tags: [question, recent, potential, unresearched]
aliases: ["What does a comprehensive r30 queue view (highlighting the best 10) need?"]
---

# What does a comprehensive r30 queue view (highlighting the best 10) need?

## Why it is open

Depends directly on [[h-recent-config-ptt-b30-r10]] — can't highlight "best
10 of the 30" without the r10 computation existing first, and that page's
friend-path restriction ([[d-r10-impossible-friend-path]]) applies here too,
likely harder: a full queue view exposes more of the underlying data shape
than a single delta number would, so the degrade-or-restrict decision matters
more, not less.

Separately unresolved: 30 rows do not fit one Discord embed cleanly.
Needs a layout decision — paginate, compact multi-column rows, or something
else — informed by the existing `/recent` embed conventions (PM/MPM line
format, blue-via-hyperlink, `?.?` CC skip) rather than inventing new formatting.

## What would answer it

- Resolve [[h-recent-config-ptt-b30-r10]] first — this page is its natural
  extension, not independent work.
- Prototype embed layout against Discord's practical field/character limits
  for a 30-row list before committing to a format.

## Current best guess

None yet — sequenced after r10 computation is settled.

## Answer

Not yet answered.
