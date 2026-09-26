---
type: meta
title: "Hot Cache"
status: active
created: 2026-07-21
updated: 2026-09-05
tags: [meta, hot]
aliases: ["Recent Context"]
---

# Hot Cache

Overwritten each session. Start here, then [[index|the master catalog]].

## This session — ownership answered (2026-09-03)

[[h-ownership-blob-open-before-building]] **closed**, by having its premise removed.
[[handoff-11-ownership-blob|Handoff 11]] assumed lowiro *"never reports unlocked state"*.
**It does.** `/webapi/user/me` carries `packs`, `singles`, `world_songs`; every id maps onto
the catalog with **no translation table**; coverage by derivation is **552/552**. A
credentialed player needs **no declaration at song grain**. Full record:
[[ownership-worksheet-2026-09-03]] (the catalog diffed against one live t3 payload + 146
owner answers).

**`world_songs` is misnamed** — "held, and not accounted for by `packs` or `singles`", a
catch-all from unrelated routes. And **neither array is a denial**: the `extend_*` packs are
buyable whole *and* released free through world mode, so the measured account both owned
packs whose songs were mostly absent from `world_songs`, and listed all of `extend_3`/`_4`
while owning neither. **Pack ownership is sufficient, never necessary; absence is unknown,
never locked.**

**66 of 67 Beyond charts are gated.** The worksheet's apparent contradiction — `included` per
pack vs `story` per chart — is **two independent axes** (owner): *acquisition* is always "with
its pack or song", *unlock* is a world map or story progression. 50 world · 16 story · 1 free
(Your Best Nightmare, `undertale`). Both unlock values mean **ask the player**; they stay
distinct because world unlocks take time while story cost varies per chart.

**Eternal is not a gate at all** — 109 songs, no wire signal, none needed. Opens by ordinary
play. `playable(etr) = playable(song)`; pools draw it freely.

**No cross-pack grants exist.** `guardina`/`diein`/`desive` are world unlocks whose *map* has
a prerequisite, not grants from another pack. The catalog needs no grant-edge field; the
worksheet's section on it was struck.

### The spine: OWNED ≠ UNLOCKED

> *"we should have a whole new OWNED and UNLOCKED system"* — owner

**OWNED** = did you acquire it (bought / free / free with another pack). **UNLOCKED** = have
you satisfied the in-game condition (world map, story, beginner mission, fragments).
**`playable = OWNED ∧ UNLOCKED`**, `has_score` proves both. Both axes reach chart grain *and*
pack grain — `epilogue` is a whole pack, free with `finale`, gated behind story.

Design calls (all owner): t2/t3 songs **derived**, no input · Beyond **asked**, of everyone ·
t1 **declares**, `playable = declared ∪ has_score` · **both** surfaces (inline picker + blob)
· stored at **chart** grain · tournament `pool.owned_by_all` **confirmed wanted**, no longer
blocked. Manual surface measures at **49 one-checkbox packs + 14 mixed + ~254 song toggles**.

## Open, decided but unapplied

[[h-world-unlock-corrections]] — **18 wrong `world_unlock` rows** (7 stale-unflagged in
`extend_3`/`extend_4`, 11 wrongly flagged, three of those songs whose *Beyond* carries the
unlock) plus one stale pack name (`extend_3` → "Extend Archive 3"; `extend_4`'s "World Extent
4" is correct as stored). **No code or data changed this session** — documentation only, by
instruction.

Also found: `song_difficulties.world_unlock` already overrides at chart grain, used by 7 rows
(all `byd`, all `True` over a `False` song) — 7 of the 50 world-earned Beyonds. Right grain,
14% of the cases.

## Where tournaments stand

Match layer built 2026-09-02, spot-checked and clock-fixed 2026-09-03 (flat 300 s window, the
break as a rest, two beats per round — see [[log|Log]]). **`best`-score mode retired
2026-09-05** ([[h-first-score-is-the-only-rule]]): a round counts each player's first valid
score, the `scoring_rule` column and the `rule:` option are gone, and the early
window/grace exits stopped being conditional. Ownership is now the one *unblocked*
pool filter. Five deferred pages remain: [[h-tournament-sticky-board]],
[[h-tournament-untracked-participants]], [[h-tournament-one-match-per-thread]],
[[h-tournament-pool-sizing]], [[h-tournament-spot-check-leftovers]];
[[h-tournament-attempt-overhead]] closed with `best`. The formats layer
([[handoff-14-tournament-formats|handoff 14]]) is still unbuilt.

**Opened 2026-09-04, still open: the first-score rule does not mean one attempt**
([[h-tournament-quit-rerolls-first]]).
A quit submits nothing, so the flat 300 s is a ~3-reroll budget — aimed, because an open
round's scores render live — handed only to players who know the trick. No window length
closes it; the proposal is a **co-submission band** anchored on the first submission, made
safe by Link Play submitting every score together (hard deaths included), plus a roll call
before `start_ms`. Nothing built; awaiting owner sign-off.

## Related

[[ownership-worksheet-2026-09-03]] · [[catalog|Catalog]] §Ownership ·
[[h-world-unlock-corrections]] · [[tournaments|Tournaments]] · [[log|Log]] · [[index|Index]]
