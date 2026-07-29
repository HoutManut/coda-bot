---
type: gotcha
status: active
severity: high
area: wire
verified: 2026-07-17
created: 2026-07-21
updated: 2026-07-21
tags: [gotcha, potential, ptt, wire, sentinel]
aliases: ["PTT `-1` means HIDDEN, not a low rating — and it's a different field from chart CC"]
---

# PTT `-1` means HIDDEN, not a low rating — and it's a different field from chart CC

## Symptom

A hidden player's PTT renders as `-0.01` (blind ×100 decode of `-1`); or a hidden player sorts
to the very bottom of a PTT-ranked list as if they were rated `0`, instead of being excluded/
labeled unknown; or code that means "chart constant" reads `friend.rating` (or vice versa) and
silently operates on the wrong scale.

## Cause

Two structurally unrelated fields share the name `rating`:

| Field | Object | Scale | `-1` sentinel meaning |
|-------|--------|-------|------------------------|
| Chart constant (CC) | `song_difficulties.rating` | ×10 | N/A — `err`-only, see [[d-level-cc-sentinel-values]] |
| PTT | `friend.rating` / player object | ×100 | **Hidden** — player opted out of the rating mechanic |

Owner-verified 2026-07-17: a hidden player's PTT sends `-1` on **both** the friend view and the
account's own `/webapi/user/me` — no fallback exists to recover a real number from either path.
A naive `stored / 100.0` decode of `-1` produces `-0.01`, a plausible-looking but wrong number
that silently corrupts any average/sort/comparison it enters.

## The wrong fix

1. Decoding PTT with the same "treat `<=0` as unknown, otherwise divide" logic borrowed from CC
   handling ([[d-level-cc-sentinel-values]]) — the scales differ (×10 vs ×100) and the *meaning*
   of the sentinel differs (err-only-N/A vs. player-hidden), so sharing decode logic between the
   two fields is a trap even though both use `-1`.
2. Sorting a hidden player to the bottom of a leaderboard "as if" they were rated `0` — an
   *unknown* PTT is not a *low* one; the player may be far above everyone on the list.
3. Substituting our own computed PTT (see [[Potential]] §Traps) into a passive surface just
   because the server's `rating` is `-1` — hiding is a render-boundary rule that must suppress
   **every recoverable form** of the value (a b30 average, a per-play rating listing, a
   rating-sorted position), not just the literal `rating` field. Showing our own number "since
   theirs is hidden" defeats the entire feature.

## The right handling

- Check `rating == -1` before any arithmetic; treat it as "unknown", never as `0` or a
  reconstructable negative.
- Never let `-1` reach a sort comparator, average, or arithmetic expression un-guarded.
- Suppress on **passive** surfaces (leaderboard, auto-posted embed, profile card); show on
  **self-invoked** rating commands only (`/b30` and friends) — invocation is consent, and rating
  commands are self-only by design so the check is structural, not a per-surface hidden-player
  carve-out. See [[Potential]] §Traps.
- Keep ingesting and computing PTT/pools for hidden players unchanged — the hide is a display
  rule only, applied at render time, never at ingest.
- Name the two `rating` fields distinctly in code/DTOs (e.g. `chart_constant` vs. `ptt`) rather
  than propagating the wire's shared name past the DTO boundary, to make the ×10-vs-×100 mixup
  structurally harder.

## Regression signal

Any PTT value between `-0.02` and `0.00` appearing anywhere in output; a hidden player appearing
at the bottom (rather than absent/labeled) of a PTT-sorted list; a passive surface showing a
number for a player whose `rating` is `-1`.
