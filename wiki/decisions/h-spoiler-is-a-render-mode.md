---
type: decision
status: active
date: 2026-08-27
reverses:
created: 2026-08-27
updated: 2026-08-27
tags: [decision, catalog, discord, surface, rendering]
aliases: ["A spoilered version changes how a chart renders and who sees it, never whether it is found"]
---

# A spoilered version changes how a chart renders and who sees it, never whether it is found

## Context

A new game version ships songs people want to look up and others have not seen.
Every surface rendered a chart the same way regardless of age — a full-colour embed
with name, jacket, CC, level and note count, posted publicly into whatever channel the
command ran in — so there was no way to say "this is new, do not broadcast it".

The obvious implementation does not exist: **Discord has no spoiler flag for rich
embeds.** Only attachments (a `SPOILER_` filename prefix), message text (`||…||`) and
Components V2 items carry one. Jackets ride *inside* the embed
(`embed.set_thumbnail(file)`), where the prefix is ignored, and the difficulty buttons
are top-level action rows that nothing in the classic model can cover.

## Alternatives

| Option | Why not |
|---|---|
| `SPOILER_` on the jacket alone | The embed renders an `attachment://` reference inline and ignores the flag. Even if pulled out as a loose attachment, name/artist/CC/level and the buttons stay in the clear. |
| `\|\|…\|\|` in the description | Loses the colour stripe, fields and thumbnail layout, and still cannot blur the buttons. |
| Blur whole songs when any chart is new | Over-blurs: an old Future everyone has played for years goes dark because a Beyond landed. Rejected by the owner in favour of per-chart. |
| Hide spoilered charts from search | A much larger change across `SearchService`'s `include_hidden` seam, which already conflates err with delisted ([[d-chardle-dead-clue-columns]] is the bug that came from overloading it). Delisting (`_name_`) already exists for a hard hide. |
| A per-render `SELECT` for the flagged set | Every `/song`, `/score` and live post asks; and `Op.complete` is synchronous, so the `/run` completer cannot query at all. |

## Decision

**Spoiler is a rendering-and-visibility mode, not a catalog gate.**

1. A version is flagged by presence of a row in `spoiler_versions`, written only through
   `/run spoiler add|remove|list`. The flagged set is cached process-wide and refreshed
   on write and at startup.
2. A chart is spoilered iff its **effective** version is flagged —
   `COALESCE(song_difficulties.version, songs.version)`, via `catalog/resolution.effective`.
   So a Beyond added to an old song in a flagged version is spoilered and its Future is not.
3. **Every chart render is a Components V2 `Container`**, spoilered or not; `spoiler=True`
   is the only difference. One generic `embed → container` converter does this, so **no
   embed builder changed** — the embed survives as the authoring format because it is a
   far more convenient thing to build, and converting at the boundary keeps the blurred
   and unblurred cases one renderer rather than two that drift.
4. Rendering *everything* as a container is what makes the shape question disappear. A
   message's `IS_COMPONENTS_V2` flag can never be removed, so a mixed world would need a
   message to change shape when a button led from a plain view into a spoilered one —
   which Discord does not allow, and which cost a special case. With one shape there is
   no transition to handle and `apply()` simply edits.
5. Commands whose `ephemeral` option defaulted to `false` now default to **unset**
   (`default=None`), and `respond()` resolves unset to the payload's spoiler state. An
   explicit `ephemeral: false` still shares.
6. The empty-query `/song` autocomplete excludes flagged versions. It is ordered by
   `idx` descending, so it *is* the newest content by construction — the one
   autocomplete path that hands spoilered names to someone who typed nothing.

## Consequences

- **Search still finds spoilered songs.** `/song version:7.0`, a typed autocomplete
  query, and the list/pager views all still return them; the detail view blurs. This is
  deliberate — see Alternatives. Anything needing a hard hide uses delisting.
- **Chardle can still pick a spoilered chart as an answer** (`chardle/facts.py`). This is
  the one place the bot spoils *actively* rather than answering a question, and the only
  open leak worth a follow-up.
- `/recent` cannot flip to ephemeral: it defers before `request_refresh` says which play
  it is showing, and flags are fixed at defer time. Making it ephemeral would also break
  post suppression — `_mark_shown` would suppress a channel's live post that nobody in
  that channel saw. It gets the blur only.
- Live posts have no viewer to be ephemeral for, so they post blurred rather than being
  suppressed. Nothing is silently dropped.
- Three accepted fidelity losses, now paid on **every** chart render rather than only the
  blurred ones: inline fields stack instead of sitting three across, the embed's native
  timestamp becomes `<t:…>` markdown, and an author avatar icon is dropped (the section's
  one accessory slot holds the jacket). This is the price of one consistent look.
- Only `/song`, `/score`, `/calc`, `/recent` and the live poster moved. `/config`,
  `/register`, `/liveupdates`, `/tracking` and chardle still send plain embeds — they are
  a different visual language and never appear beside a chart.
- A chart-list button row still shows that a spoilered Beyond *exists* on an otherwise
  old song. Accepted: the existence of a chart is a far weaker signal than its name,
  jacket and CC, and search already reveals it.
- The cache is per-process. `/run spoiler` refreshes in-process, but a write from the
  admin app or raw SQL is not seen until restart. `/run` is the only sanctioned path.
- `spoiler_versions` is deliberately **not** in `dump-songs.sh`'s `SONG_TABLES`, matching
  `config_values` and `difficulty_search_config`: it describes a deployment, not the songs.

## Enforced at

`src/coda/catalog/spoilers.py` (the predicate + cache), `src/coda/utils/container.py`
(the converter), `src/coda/utils/render.py:respond`/`apply` (shape and ephemeral
default), `src/coda/ops/spoiler.py` (the owner surface),
`src/coda/catalog/autocomplete.py:_newest_songs`.
Pinned by `tests/test_container.py` and `tests/test_spoiler_predicate.py`.
