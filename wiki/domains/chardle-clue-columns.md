---
type: domain
status: active
source: Tenniel prototype (`classes/chardle.py`, `plugins/chardle.py`, 2024-09/10, archived outside this repo) + design session 2026-07-27
verified: 2026-07-28
created: 2026-07-29
updated: 2026-08-31
tags: [domain, chardle, game]
aliases: ["Chardle Clue Columns", "Chardle — Clue Columns"]
---

# Chardle — Clue Columns

Split out of [[chardle|Chardle]] 2026-07-29 (that page had grown past the vault's 300-line
soft threshold — see `meta/lint-report-2026-07-29.md`). Covers the clue-column mechanics:
what columns exist, how each is scored, ordering, and the jacket/duplicate-title identity
rules. Pool, stats, rules, and prototype provenance live in
[[chardle-mechanics|Chardle — Mechanics]]; the Discord channel/scoreboard surface lives in
[[chardle-discord-surface|Chardle — Discord Surface]].

## Clue columns

A puzzle freezes an ordered column set at creation. `title` is always present. The rest
are drawn per puzzle, so the board's *shape* is itself a variable — 56 possible shapes,
measured against the live catalog 2026-08-31 at the 7-column cap (extras rolls the same
set as an ordinary tier: the `class` column below was never built). That claim
was **false for the first day of the build**; see
[[d-chardle-dead-clue-columns]] §The over-correction that shipped first.

The column *set* varies per puzzle; the column **order does not**. Columns always render in
one canonical sequence, and a puzzle chooses only which of them are present:

`jacket · title · artist · level|rating · pack|version · charter · side · class · bpm · note`

At most **7 columns counting `title`** (`jacket` is an identifier, not a clue). Both the
order and the cap are carried from the prototype, which appended in a fixed sequence and
rolled only membership. Its cap could leak to 8: the `level`/`rating` branch was the one
append path that never checked it.

Deterministic order is what keeps a board readable across days — the emoji share grid means
the same thing on every puzzle, and a player learns the layout once instead of re-reading a
legend each morning.

| Column | Green | Yellow | Red | Arrow |
|---|---|---|---|---|
| `title` | same song | — | different song | no |
| `artist` | link sets equal | sets intersect | disjoint | no |
| `charter` | link sets equal | sets intersect | disjoint | no |
| `pack` | same pack | same series, different pack | unrelated | no |
| `side` | same side | Achromic / Lephon / Dark Lephon, wrong one of the three | Light or Conflict mismatch | no |
| `version` | equal | same major | different major | **yes** |
| `level` | equal | within ±4 stored (±2 game levels) | beyond | **yes** |
| `rating` (CC) | equal | same whole CC number | different whole CC number | **yes** |
| `bpm` | equal | within threshold | beyond | **yes** |
| `note` | equal | within threshold | beyond | **yes** |
| `class` | same class | — | different class | no |

`class` exists only on **extras** puzzles, where the difficulty class is hidden rather
than revealed. It is meaningless anywhere else, since every other pool states its class up
front.

Arrows show on **both** yellow and red — direction is never withheld. That generosity is
what keeps a 6-attempt board solvable.

### The three Lephon-adjacent sides score as one family

`side` is the one column whose yellow is not a distance. Arcaea presents Achromic, Lephon
and Dark Lephon as a single side to the player — the song list offers Light, Conflict and
Colorless and nothing else — so a guess that lands inside that family but names the wrong
one of the three is a near miss, not a wrong answer (owner, 2026-08-31). Light and Conflict
are untouched: they stand alone, and a mismatch against either is red. The cell still prints
the chart's **true** side, so the family is visible on the board rather than inferred.

`rating` does not use a distance window like `level`/`bpm`/`note` — it mirrors `version`
instead: CC is stored `x10`, so `guess // 10 == answer // 10` is "same whole CC number"
(`10.1` and `10.9` both count as close to each other; `9.9` doesn't, despite being the
smaller raw distance). See `_rating` in `feedback.py`, next to `_version`.

`bpm` and `note` are new. The prototype reserved them in config (`bpm_range`,
`note_range`, with bucket tables) and never implemented either. The revival uses
**arrows, not buckets** — finer signal, and no bucket boundaries to tune. Their yellow
thresholds are the one genuinely unsettled number here; start at ±20 BPM and ±150 notes
and treat them as scoped settings. Both thresholds are surfaced in `/chardle help`
(resolved live from `chardle_bpm_window`/`chardle_note_window`, not hardcoded), so a
player can read the actual rule instead of discovering it by trial.

Two column pairs must not both appear on one board — see
[[d-chardle-dead-clue-columns]]. `level`/`rating` are mutually redundant (the prototype
already coin-flipped between them); `pack`/`version` are near-duplicates it always showed
together.

### The jacket is an identifier, not a clue

The prototype's first column rendered *the guess's own jacket*, and `get_shadow` returned
`None` for it unconditionally — it never produced feedback.

That is not the same as producing nothing. The jacket is there to **identify the row**
alongside the name, which is a real job and the reason it was built (owner, 2026-07-27).
Reading "no feedback" as "no information" conflates feedback with identity.

Its job also got *more* important than it was in 2024. Ambiguity cycling
([[h-chardle-closest-match-always-costs]] §Cycling) means a board can now hold two rows
both titled `Quon`, and art separates them instantly where text does not.

What is actually wrong with the prototype's treatment is **cost, not purpose**: identity
does not need a full 220 px flex column when every other column is carrying feedback. So
the jacket stays, as an identifier, at a fraction of the width.

**Placement is undecided** — the owner is drafting it in Figma. Candidates raised:
inset into the title cell, a narrow fixed left gutter, or a dimmed full-row background.
Tracked in [[h-chardle-board-rendering]].

### Duplicate titles need a tiebreak label

Arcaea ships several distinct songs sharing a title. When a guess resolves to one of
them, a row labelled only `Quon` cannot tell the player *which* Quon was measured — so
the board would be lying about what it compared. Guess resolution itself is
[[h-chardle-closest-match-always-costs]].

Retyping the same ambiguous name **cycles to the next reading of it** — `quon` twice
reaches both Quons, a third time is a free duplicate rejection. So a cycled board really
does hold two rows both titled `Quon`.

Two mechanisms cover it, in order:

1. **The jacket**, which distinguishes them at a glance and costs no text.
2. **A pack or artist label**, rendered **only when the resolved song's `name_en` is
   non-unique**. Ordinary boards stay clean; pixels are spent only where ambiguity is
   real.

The label is a fallback, not decoration, and there are two cases where it is the *only*
mechanism: a song whose jacket art is missing (the prototype fell back to a shared
`base.webp`, which makes every fallback row look identical), and a text/emoji board, which
has no art at all. If [[h-chardle-board-rendering]] lands on a text renderer, the label
stops being conditional and becomes mandatory.

## Related

[[chardle|Chardle]] · [[chardle-mechanics|Chardle — Mechanics]] ·
[[chardle-discord-surface|Chardle — Discord Surface]] ·
[[d-chardle-dead-clue-columns]] · [[h-chardle-closest-match-always-costs]] ·
[[h-chardle-board-rendering]]
