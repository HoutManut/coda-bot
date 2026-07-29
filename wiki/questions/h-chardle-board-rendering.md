---
type: question
status: open
blocks: [chardle]
source: design session 2026-07-27
created: 2026-07-27
updated: 2026-07-27
tags: [question, chardle, rendering, unbuilt]
aliases: ["How is a Chardle board rendered?"]
---
# How is a Chardle board rendered?

## Why it is open

Deliberately deferred on 2026-07-27 so the game's rules could be settled without the
renderer's constraints leaking into them. Everything else in [[chardle|Chardle]] is
decided; this is not.

The Tenniel prototype composited the board with Pillow: `header.png`, a per-guess row
image, jacket art, side backgrounds, a flex-grow column layout (`FLEX_GROW` weights,
`MIN_WIDTH = 220`) and a per-character font fallback (Mada → Noto Sans) for CJK titles.
It looked like Arcaea. It also carried ~3 MB of assets, a Pillow dependency, per-guess CPU
on every board redraw, and a hand-rolled line-breaker.

The obvious cheap alternative — a Discord-native table plus 🟩🟨🟥⬆️⬇️ — needs no assets,
reads on mobile, and is trivially shareable. It also discards the game's entire visual
identity, which was most of the prototype's appeal.

Three decided rules constrain whatever is chosen, and none of them is satisfied for free:

1. **Rows must identify the song they measured.** Guesses always resolve silently, and
   retyping an ambiguous name *cycles*
   ([[h-chardle-closest-match-always-costs]] §Cycling), so a board can hold two rows both
   titled `Quon`. The **jacket** is the primary identifier; a **pack or artist label**
   appears only when `name_en` is non-unique. A text/emoji board has no jacket, so
   choosing one **promotes that label from conditional to mandatory** — the renderer
   choice changes the game's display rules, not just its looks.
2. **Sentinel columns render `?` with no colour and no arrow** — never a decoded number.
   See [[d-level-cc-sentinel-values]].
3. **The share string is a separate renderer** and must stay in sync with the board's
   colours. `Chardle #412 4/6`, arrows included (they leak nothing — the reader cannot see
   the guess an arrow points from). A free-play board shares a self-describing variant
   instead — `Chardle · FTR 9 · 4/6` — because without a puzzle number the reader has no
   column legend to decode the grid against.

The column set is frozen per puzzle and varies between puzzles, so the layout is dynamic
in either approach — though the *order* is a canonical constant, so only the presence of a
column varies, never its position ([[chardle-clue-columns|Chardle — Clue Columns]]).

A fourth constraint arrived with the transport decision: a **daily board is edited in place**
inside a private thread or DM for the hours it lives ([[h-chardle-boards-are-channel-owned]]),
so whichever renderer is chosen runs once per guess on a message that already exists. An image
board pays that cost in re-composited attachments, which is worse than re-rendering text.

## What would answer it

An owner decision between:

- **Port the Pillow renderer** — keep the look, pay the asset pipeline. Needs ETR and
  `Side.LEPHON` art the prototype never had, since its `bg_file` branched only on sides
  0–2 and `byd`/`byd_2`.
- **Text/emoji grid** — no assets, instant share parity, loses the identity.
- **Hybrid** — image board, text share string. Two renderers to keep in sync, which
  rule 3 already half-requires anyway.

### Sub-question: where the jacket sits

Settled: the jacket **stays**, as a row identifier rather than a clue, and must not cost a
full 220 px flex column the way the prototype's did — see
[[chardle-clue-columns|Chardle — Clue Columns]] §The jacket is an identifier, not a clue.

Unsettled: its placement. **The owner is drafting this in Figma (2026-07-27)** rather than
deciding it in prose. Candidates raised, none chosen:

| Placement | Trade |
|---|---|
| Inset in the title cell | No extra width (title already has flex-grow 2), identity sits next to what it identifies |
| Narrow fixed left gutter | ~48 px instead of 220, and the title cell stays purely textual so line-breaking stays simple |
| Dimmed full-row background | Zero width, closest to Arcaea's own UI, but fights the side-coloured background and hurts legibility on busy art |

A jacket fallback is also needed: the prototype used a shared `base.webp` for missing art,
which makes every fallback row look identical and silently defeats the identifier.

## Current state (2026-07-27)

The **text/emoji grid** shipped as a deliberately temporary frontend, on the
owner's instruction. It is `chardle/render.py`: 🟩🟨🟥⬛ plus 🔼🔽, a `-#` legend
line naming the board's columns in canonical order, and the pack label promoted to
**mandatory on a non-unique title** exactly as rule 1 requires. The share string is
the same grid, fenced into the finished board's own embed so it copies in one tap.

It was **not legible enough on its own** — seven unlabelled emoji in a row do
not say which column is which. A **debug view** (`chardle_debug_board`, default
`on`) now renders one labelled line per column per guess and states the answer
outright. That is a testing scaffold, not a design answer: it makes the question
below more urgent, not less.

Still open: whether the Pillow board is ported. Nothing in the schema or the
services blocks it — the renderer is the only module that would change.

The **daily scoreboard** (iteration 2, 2026-07-27) was built behind the same seam
and pre-committed to the image path: `scoreboard.build` produces a pure
`DailyScoreboard` dataclass and `render.scoreboard` returns
**`tuple[Embed, File | None]`** — the repo's existing attachment convention
(`scores/embed.py`, `song.py`'s `_Rendered`). The text implementation returns
`(embed, None)`; a composited board fills the second slot and nothing outside
`render.py` changes. It reuses `render.cells` for each finished player's grid, so
a shared grid and that player's own share string cannot drift apart.

## Earlier best guess

None ventured. The owner deferred this explicitly rather than defaulting to either.

Worth noting for whoever picks it up: rule 3 means a text renderer has to exist *anyway*
for the share string, so "text grid" is the incremental-cost-zero option and "hybrid" is
closer to it than to a full image port.

## Answer

Unanswered.
