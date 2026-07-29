---
type: module
status: active
path: src/coda/players/
purpose: Registration (Discord user <-> ArcaeaAccount), reserved codes, own-path polling sessions, live-update destinations.
depends_on: [arcaea, sessions, db, crypto]
used_by: [extensions]
created: 2026-07-21
updated: 2026-07-21
tags: [module, players, registration]
---

# players

## Purpose

Turns a Discord user into a linked `ArcaeaAccount`, by friend code or by the player's own
lowiro credentials — the two paths are **orthogonal**, not alternatives (a player can hold
neither, either, or both). Also owns which friend codes are refused before ever reaching the
wire (`reserved.py`), the durable owner-approval flow for a contested code claim
(`link_approval.py`), and the own-credentials iterator the poller drives
(`session.py`, distinct from `sessions/session.py`).

## Public surface

| Symbol | File | What it does |
|---|---|---|
| `RegistrationService.register_by_code(db, discord_id, raw_code)` | `service.py` | Friend-code path. Returns `Registration` or `NeedsApproval` |
| `RegistrationService.register_by_credentials(db, discord_id, email, password)` | `service.py` | Own-credentials path. Returns `Registration`, `ProvenOverCode`, or `ProvenCoexists` |
| `RegistrationService.unlink_credentials(db, discord_id)` | `service.py` | Deletes a stored credential; friend link untouched |
| `RegistrationService.unregister(db, discord_id)` | `service.py` | Deletes the caller's link; strays the account if it was the last one |
| `RegistrationService.current_account(db, discord_id)` | `service.py` | The one account this Discord user links (enforces no-switching) |
| `check_static(code, discord_id)` / `is_bot_account(db, code)` / `is_bot_email(db, email)` | `reserved.py` | Refuse easter-egg codes, the owner's code, and our own bot accounts — before any network call |
| `PlayerSessionProvider(db, app)` | `session.py` | `.poll_sessions()` / `.session_for(id)` — yields own-path `(ArcaeaAccount, AccountSession)` pairs for the poller; `.handle_invalid(account)` — DM on terminal 403 |
| `request_link(...)` | `link_approval.py` | Durable Approve/Deny DM flow for a code claim on an already-owned account |
| clean-code entry point | `coda.utils.friend_code::clean_friend_code` | Local shape validation, separators-only strip — see [[w-friend-code-strip]] |

## Layer rules

- **Uses `sessions/` only through `SessionPool`/`BotSession`/`AccountSession`** — never
  touches a `sid` or a `bot_account_id` directly. Verified against `service.py`: the pool is
  always addressed through `SessionPool(db)`, and `_place_and_add` handles only `ApiError` /
  `PlayerNotFound` / `AlreadyFriend`, all exceptions from `arcaea/errors.py`, never a raw
  wire value.
- **`players/session.py` lives outside `sessions/` on purpose** — its terminal-403 handling
  ends in a Discord DM (`notify.py`), and `sessions/` must not import anything
  Discord-facing.
- **Reserved-code checks run before any network call**, for the identical reason local
  friend-code shape validation does: lowiro's answer (a plain 401, indistinguishable from a
  real typo) tells the user nothing useful. `check_static` and `is_bot_account`/`is_bot_email`
  both run pre-wire.
- **Credentials never appear in a public channel** — both registration paths use an
  ephemeral modal (`extensions/register.py`, outside this package's scope but the contract
  `players/service.py` is built for).

## State it owns

- Nothing directly — `RegistrationService` and `PlayerSessionProvider` are stateless classes
  taking an `AsyncSession` per call, matching the project's general service pattern. All
  state is `coda.db.models` rows: `ArcaeaAccount`, `PlayerLink`, `PlayerCredential`,
  `BotAccount` (read-only from this package's perspective, owned by `sessions/`).

## Related callouts

> [!warning] may be reversed by handoffs
> The owner-approval / ownership-provenance flow (`NeedsApproval`, `ProvenOverCode`,
> `ProvenCoexists`, `link_approval.py`) and the bot-code fake-not-found retirement in
> `reserved.py` both **already reflect** handoffs 01, 02 and 05 per this
> package's own docstrings — they are the built state, not a stale claim. A parallel ingest
> agent is processing the handoff notes directly; if that ingest surfaces anything this
> page does not yet reflect (e.g. further changes described in
> [[handoff-06-credentials-changed-server-side]] or [[handoff-11-ownership-blob]]), that
> ingest's pages win over this one per `wiki/meta/conventions.md`'s precedence order.

## Related

`[[Registration]]`, `[[sessions]]`, `[[arcaea]]`,
`[[w-friend-code-strip]]`, `[[w-local-friend-code-validation]]`
