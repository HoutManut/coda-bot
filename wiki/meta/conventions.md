---
type: meta
title: "Conventions"
status: active
created: 2026-07-21
updated: 2026-07-21
tags: [meta, conventions]
---
# Conventions

## Frontmatter

Every page carries at minimum:

```yaml
type: source | domain | module | flow | decision | gotcha | question | meta
status: stub | active | stale | superseded
created: YYYY-MM-DD
updated: YYYY-MM-DD
tags: []
```

Wire-touching pages add:

```yaml
verified: YYYY-MM-DD    # when this was last checked against the live API
grade: A | B | C        # confidence grade from arcaea-auth-behavior.md
```

Code-touching pages add `path:` pointing at the `src/` package or file.

## Staleness

The private webapi ships no versioning and no deprecation notice. A wire claim with no
`verified:` date is untrusted. When the wire contradicts a page, **re-capture** — do not
edit code to match a stale page.

## Precedence

1. Live wire behavior
2. `src/` — shipped code
3. `CLAUDE.md`
4. this wiki

Within the wiki, a later `decisions/` entry outranks an older `sources/` page: handoff
notes recorded reversals of the source docs by design.

A wiki page that disagrees with anything above it is a bug in the wiki.

## Vocabulary

In-game terms internally: **pure / far / lost**. The API's `perfect` / `near` / `miss`
stop at the DTO boundary in `src/coda/arcaea/`. Wiki pages follow the internal vocabulary
and note the wire name once, where the mapping is described.

## Linking

Link liberally. A `[[Page]]` with no file yet marks work worth doing, not an error —
`wiki-lint` reports them as intentional stubs when the target is listed in [[index|Index]].
