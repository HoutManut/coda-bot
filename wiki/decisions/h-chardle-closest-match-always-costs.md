---
type: decision
status: active
date: 2026-07-27
reverses:
created: 2026-07-27
updated: 2026-07-27
tags: [decision, chardle, catalog, search]
aliases: ["Ambiguous guesses resolve to the answer if possible, else to the closest match — and always cost an attempt"]
---

# Ambiguous guesses resolve to the answer if possible, else to the closest match — and always cost an attempt

## Context

Arcaea ships distinct songs sharing a title. A player typing `quon` has named a real
song, but not a unique one. [[chardle|Chardle]] has to decide what the board measured.

`catalog.search.SearchService` already models this: `resolve` returns `SongDupes`, a
button-per-song pick, and `/song` presents it. Chardle cannot simply reuse that flow —
a modal pick mid-guess is friction, and the interaction cost is paid on every ambiguous
title.

The Tenniel prototype had a half-answer. `submit` iterated candidates and `break`'d on
`entry == self.answer` — generous when the guess *was* right. The other branch was the
bug: ambiguous with no candidate matching, it compared against whichever candidate the
loop happened to leave bound, printed that row's arrows, and charged an attempt. Wrong
data, silently.

## Alternatives

| Option | Why not |
|---|---|
| Always show the `SongDupes` picker | No leak and no wrong data, but it taxes every ambiguous title with an extra interaction — and it discards the prototype's genuinely good behaviour of crediting a player who named the right song |
| Answer-preference, then picker when nothing matches | Keeps the credit *and* avoids wrong data — but receiving the picker then tells the player "no Quon is the answer", eliminating several songs for zero attempts. A free hint disguised as a UI affordance |
| Reject ambiguous guesses outright | Punishes the player for the catalog's naming, and `quon` is a perfectly reasonable thing to type |
| Prototype behaviour as-is | Compares against an arbitrary candidate and charges for it |

## Decision

Guess resolution is deterministic and never opens a picker:

0. **The typed name matches the answer chart's own names or aliases, exact tier only** →
   **win**, regardless of catalog visibility. See §Rule 0.
1. **Unique match** → resolve to it.
2. **Ambiguous, one candidate is the answer** → resolve to *that one*; the player wins.
   Naming the right song counts, whichever duplicate they meant.
3. **Ambiguous, none is the answer** → resolve to the closest **candidate not already on
   this board** (top-ranked by `SearchService`'s trigram similarity) and **consume an
   attempt**. Retyping the same ambiguous name therefore walks to the next reading of it.
4. **Unresolvable** — no match at all, or the song lacks the puzzle's revealed
   difficulty — **does not** consume an attempt. Carried over from the prototype.

### Rule 0: the answer outranks the cloak

`SearchService._chart_visible` gates **delisted songs and err charts on the same
`include_hidden` flag**, and chardle passes `False` everywhere except an err puzzle. A song
delisted *after* its puzzle was created therefore vanishes from resolution — including for
the player trying to name it — and the board becomes unwinnable through no fault of theirs.
The pool exclusions in [[chardle-mechanics|Chardle — Mechanics]] §Pool only run when the answer is *drawn*; they
cannot police what the catalog does afterwards.

So the answer is checked before the search runs:

- Typed name matches the **answer chart's** names or aliases → **win**, cloaked or not.
- Every other delisted song stays invisible, resolves to nothing, and comes back as an
  **invalid, free** guess — unchanged.

**Exact tier only.** A fuzzy match here would hand the win to a near-miss, which is the one
thing rule 3 exists to prevent. Use the same exact-candidate semantics as
`SearchService._exact_candidates`, never `_top_tier`'s fuzzy tail.

This is narrow by construction: an err answer is impossible outside an err puzzle, and an
err puzzle already passes `include_hidden=True`, so rule 0 only ever fires for a
delisted-mid-game answer. It removes the need for a void state or a sweep.

### Candidates are filtered before any rule runs

A candidate that does not carry the puzzle's revealed difficulty is **dropped from the list
first**; rules 1–3 apply to what survives, and an empty list is rule 4.

Without that ordering rules 3 and 4 disagree about the same guess — rule 3 would resolve to
a candidate and charge for it, rule 4 would call that same song unresolvable and refund it.
Filtering first makes "ambiguous" mean "ambiguous among *playable* readings", which is the
only reading a player can act on.

### Cycling

Rule 3's "not already on this board" is what lets a player reach the other Quon without a
picker:

```
"quon"  → [Quon-A, Quon-B], neither on board → Quon-A   attempt spent
"quon"  → Quon-A on board                     → Quon-B   attempt spent
"quon"  → both on board                       → duplicate, free
```

It needs **no new state**. Duplicate rejection already keys on the *resolved chart*
(`UNIQUE (session_id, song_difficulty_id)`), so the board is the cursor, and the sequence
self-terminates through the existing free-rejection path. It also survives interleaving —
`quon`, `tempestissimo`, `quon` still advances — because nothing remembers what was typed
last.

**Cycling is bounded to a genuine title collision.** It walks the exact-match tier only,
never the fuzzy tail. Unbounded, it corrupts an ordinary repeat:

> A player retypes `tempestissimo` having already guessed it. Unique match, already on the
> board, so an unbounded skip resolves to the next *fuzzy* candidate — an unrelated song —
> and charges an attempt for a song they never named.

A unique match already on the board is a **duplicate**: free rejection, no cycling.
`SearchService._top_tier` already draws this line — it returns exact candidates when any
exist and only falls back to the fuzzy tail otherwise.

Cycling composes with rule 2 rather than competing with it: if either duplicate *is* the
answer, the first guess already resolves to it and the game is won, so cycling only ever
runs when every candidate is wrong.

Rule 3 is what closes the leak the runner-up alternative opens: because ambiguity always
resolves silently, the player never learns anything from *how* the game responded, only
from the row itself.

## Consequences

- **The board must identify which song it measured.** A row that says only `Quon` when
  the player meant the other Quon is the game lying about its own comparison. **Cycling
  raises the stakes**: a cycled board carries two rows both reading `Quon`. Two mechanisms,
  in order — the **jacket**, which separates them visually at no text cost, and a **pack or
  artist label rendered only when `name_en` is non-unique**. The label is the sole
  mechanism when art is missing or when the board is text-only, so a text renderer makes it
  mandatory rather than conditional. Rendering requirement — see
  [[h-chardle-board-rendering]].
- **Cycling is a reply-path mechanism only.** `SearchService.candidate_songs` returns
  `(song_id, name_en, artist, pack_name)`, so slash-command autocomplete already
  disambiguates on screen and hands back one song. The reply path is the one with no way
  to disambiguate, which is exactly where cycling earns its keep.
- Rule 2 short-circuits before rule 3, so the arbitrary-candidate case only ever arises
  when *every* candidate is wrong. The arrows still differ between duplicates, so
  labelling remains mandatory.
- Chardle owns no matching logic. Ranking is `SearchService`'s, and if its similarity
  ordering changes, chardle's tie-breaking changes with it — correctly.
- `SongDupes` stays unused by chardle. It is not dead code; `/song` needs it, where a
  pick costs the user nothing.

## Enforced at

Not yet built. Target: `GuessService` in `src/coda/chardle/guess.py` — see
[[chardle-module|chardle (module)]].
