---
type: gotcha
status: active
severity: high
area: wire
verified: 2026-07-17
created: 2026-07-21
updated: 2026-07-21
tags: [gotcha, wire, dto]
aliases: ["`/webapi/user/me` no longer carries a `friends` key"]
---

# `/webapi/user/me` no longer carries a `friends` key

## Symptom

`data['friends']` (a bare, unguarded subscript) raises `KeyError: 'friends'` on **every**
call to `GET /webapi/user/me` today — not intermittently, not on some accounts, always.

## Cause

lowiro moved the friends list off `/webapi/user/me` and onto its own endpoint,
`GET /webapi/friend/me`, at some point after the old client (`arcaea_online/`) was written.
Evidence this is a *change* and not a misreading of a document that was always wrong: the
old `MeResponseDTO.from_json` does `friends = [MeFriendDTO.from_json(x) for x in
data['friends']]` — a **direct subscript with no `.get()`**. That code shipped and worked,
so the key existed when it was written. Against today's API it is confirmed absent on two
independent accounts read end to end: a fresh throwaway (3,294 bytes, no `friends` key) and
a played-in main account with 22 friends (33 KB, 52 top-level keys, still no `friends` key —
so it is not an artifact of an empty profile). `CLAUDE.md` used to document the old
`/webapi/user/me`-carries-friends behavior; it has since been corrected.

This is presented in the source doc as the load-bearing lesson of the whole capture: the
private webapi ships **no versioning and no deprecation window**. A key present today can
vanish, and the failure mode is the worst kind — a hard crash on every call, not a graceful
degradation.

## The wrong fix

Patching the symptom by wrapping the old subscript in a broad `try/except KeyError: friends
= []` right where it fails. That silences the crash but is still reading the wrong endpoint
— it would report "this account has zero friends" for every account, forever, instead of
reading the data that actually exists at its new location. The fix is not defensiveness
around a dead code path; it is finding the data.

## The right handling

Friends come from a **separate** endpoint, `GET /webapi/friend/me`
(`src/coda/arcaea/endpoints.py::fetch_friends`), which is also **far lighter** than
`/webapi/user/me` (267 bytes vs 3,294 bytes for one friend) — use it for score polling;
reach for `/webapi/user/me` only when own-profile fields are actually needed
(`dto/me.py`'s module docstring states this explicitly). More generally, every DTO in
`src/coda/arcaea/dto/` uses `.get()` with explicit defaults and validates shape at the
boundary, raising `UnexpectedResponse` ("lowiro changed the API") rather than a bare
`KeyError` from inside a comprehension — see `dto/friend.py::parse_friend`,
`dto/me.py::parse_me`.

## Regression signal

Any new `KeyError` surfacing from inside `coda.arcaea.dto` — by design, that should never
happen; a DTO parse failure should always be a typed `UnexpectedResponse` with a description
of what was missing. A bare `KeyError` traceback from a DTO module is the regression signal
itself: it means a direct subscript slipped back in somewhere.
