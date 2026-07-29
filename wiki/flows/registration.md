---
type: flow
status: active
entrypoint: "/register method:code|account (src/coda/extensions/register.py)"
touches: [players, sessions, arcaea, db]
created: 2026-07-21
updated: 2026-07-21
tags: [flow, registration, arcaea]
---

# Registration

## Trigger

`/register` — an ephemeral slash command that opens a modal (never a plain text arg, so a
friend code or a password never lands in the visible command bar). Two independent methods,
`code` and `account`; both funnel into `RegistrationService`.

> [!warning] may be reversed by handoffs
> This page describes the flow **as built**, which already incorporates handoffs 01/02
> (owner-approval, ownership provenance) and 05 (dropping the fake-not-found oracle) per
> `players/service.py` and `players/reserved.py`'s own docstrings. A parallel ingest agent
> is processing the handoff notes directly and may have finer detail or catch a further
> reversal this page does not yet reflect (`06-credentials-changed-server-side.md` in
> particular, given [[w-third-auth-envelope]]).

## Path — friend-code method

1. `coda.utils.friend_code.clean_friend_code(raw)` — strip **separators only**
   (`123 456-789` → `123456789`), reject anything not exactly 9 digits. **Before any
   network call.** See [[w-friend-code-strip]].
2. `reserved.check_static(code, discord_id)` — refuse easter-egg codes
   (`000000001`/`000000002`) and the owner's code (unless the caller is in `OWNER_IDS`).
   Still no network call.
3. `reserved.is_bot_account(db, code)` — refuse if the code belongs to one of our own bot
   accounts, with a plain "you can't use that friend code" (not a fake not-found — see
   [[w-honest-bot-code-refusal]]).
4. `RegistrationService.current_account(db, discord_id)` — if the caller already links a
   **different** account, raise `AlreadyLinkedElsewhere` here, before any friend slot is
   touched.
5. `_find_by_code(db, code)` — known already?
   - **Known and holds a bot** (`bot_account_id` set): zero API calls, link only. This fast
     path is also what makes a later `602` a genuine drift signal rather than the normal
     case.
   - **Known but strayed** (`bot_account_id` is None — a prior `/unregister` released it):
     `_reacquire` — re-place on a bot account and reactivate in place, so the account's
     `play_scores` history (kept on stray) reattaches.
   - **Not known**: `_acquire` — `_place_and_add` (below), then create the `ArcaeaAccount`
     row.
6. `_place_and_add(pool, code)`: `pool.place(code, exclude=...)` picks a bot account with
   live capacity (`sessions/pool.py::_capacity`, always read from `/me` + `/friend/me`, never
   the stored hints), then `session.call(endpoints.add_friend, code)`.
   - `PlayerNotFound` (401) → `PlayerUnreachable` — a **player** error, fail to the user, do
     not retry another account.
   - `AlreadyFriend` (602) → re-read `/friend/me` and diff against known ids — recovers
     drift.
   - `ApiError` (any other code, e.g. the never-observed cap-exceeded case, or the last-slot
     placement race) → exclude this bot account, retry the next one, up to
     `_MAX_PLACEMENT_ATTEMPTS = 3`. Beyond that, the last `ApiError` is re-raised — a visible
     failure, never a silent `NoCapacity`.
7. `endpoints.unknown_friends(response, known)` — the response never carries the code that
   was submitted, so the caller diffs the friends list against what it already knew.
   `_exactly_one` refuses ambiguity outright (more than one candidate → `AmbiguousFriend`,
   never a guess — guessing would mis-attribute a stranger's scores).
8. `_link(db, discord_id, account, via=CODE)` — decide the link outcome (see matrix below).
9. `NeedsApproval` → no row created; the extension DMs the current owner via
   `link_approval.request_link`. Otherwise commit and return `Registration`.

## Path — own-credentials method

1. `reserved.is_bot_email(db, email)` — refuse before spending a login (bot accounts are
   keyed by unique email).
2. `identity.generate()` — a fresh coherent browser identity for this login, bound around
   the whole registration (and every later poll for this player).
3. `auth.login(email, password)` → `(sid, expires_at)`, then `fetch_me(sid)` — the login
   itself is not skippable work here; the caller needs `/me`'s `user_id` to know who this
   even is.
4. `current_account` no-switching check, same as the code path but compared on
   `arc_user_id`.
5. Find-or-create `ArcaeaAccount` by `arc_user_id`. **`bot_account_id` is left alone** if the
   account already exists — adding credentials never disturbs an existing friend link, which
   is what keeps free batched polling forever.
6. `_link(db, discord_id, account, via=ACCOUNT)` — a **proof**, so it can promote over
   code-linkers or coexist with an existing proven owner (matrix below).
7. `_store_credential` — encrypt and persist email/password (Fernet), the fresh `sid` +
   `expires_at`, the bound browser identity, and `arcaea_online_expire_ts` from `/me` (the
   tier-3 discriminator, compared against `now()` at read time — never stored as a stale
   boolean).

## Link-outcome matrix (`_link`)

| Situation | `via=CODE` | `via=ACCOUNT` |
|---|---|---|
| No existing links | `Linked` (new owner) | `Linked` (new owner) |
| Same Discord user already holds it | `AlreadyRegistered` | `_prove_in_place` — upgrades the existing link to proven, seizing ownership unless another proven owner already exists |
| Someone else owns it, unproven (code-linked) | `NeedsApproval` — **no row created**, owner is asked | `ProvenOverCode` — promotes, demotes the code-linkers |
| Someone else owns it, proven (account-linked) | `NeedsApproval` | `ProvenCoexists` — both coexist, ownership unmoved, first owner notified (no gate) |

Credentials always outrank a bare code claim: **logging in is the only real proof** an
account belongs to the caller.

## Failure modes

| Failure | Where it surfaces | User-visible result |
|---|---|---|
| Malformed/wrong-length code | `clean_friend_code` | "that's not a friend code" (before any wire call) |
| Reserved code (easter egg / owner / bot) | `reserved.check_static` / `is_bot_account` | Named refusal message, honest — never a fake not-found |
| Already linked to a *different* account | `current_account` check | `AlreadyLinkedElsewhere` |
| Nonexistent friend code | `add_friend` → `PlayerNotFound` (401) | `PlayerUnreachable` — fail to user, no retry |
| Every bot account full | `NoCapacity` after `place()` exhausts `active()` | "no capacity" — genuinely terminal, needs a human to seed another account |
| Diff yields >1 or 0 candidates | `_exactly_one` | `AmbiguousFriend` — refuses to guess, logged for manual reconcile |
| Bad credentials | `auth.login` → `InvalidCredentials` (403) | Terminal — never retried |
| Contested code claim | `_link` → `NeedsApproval` | DM to current owner; 24h expiry or closed DMs → refuse. Silence never means yes |

## Ordering constraints

- **Local validation (shape, reserved codes) must run before any wire call.** lowiro does
  not validate friend-code shape server-side — a malformed code and a well-formed-but-fake
  one both answer `401`. Skipping local validation loses the ability to tell a user "that's
  not a friend code" instead of the much worse "no such player".
- **The no-switching check must run before `_acquire`/`place()`.** `AlreadyLinkedElsewhere`
  is raised ahead of any friend slot being consumed on the code path, and after
  login-but-before-row-create on the credentials path — a switch attempt must never burn a
  pool slot or friend a bot account on an account it will refuse to link.
- **`_diff_live_friends` (the 602 recovery) must re-read `/friend/me`, never trust the error
  body** — a duplicate-add error carries no friends list to diff against.
- **Demote-before-insert in `_link`'s `ProvenOverCode` branch**: existing code-linkers'
  `is_owner` is flushed to `False` *before* the new owner row is inserted, so the partial
  unique index (`at most one is_owner per account`) never observes two owners at once.

## Related

`[[players]]`, `[[sessions (module)]]`, `[[arcaea (module)]]`,
`[[Session Lease]]`, `[[w-friend-code-strip]]`, `[[w-honest-bot-code-refusal]]`
