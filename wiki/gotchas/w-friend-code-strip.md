---
type: gotcha
status: active
severity: high
area: wire
verified: 2026-07-17
created: 2026-07-21
updated: 2026-07-21
tags: [gotcha, wire, validation]
aliases: ["Stripping every non-digit manufactures a fake friend code"]
---

# Stripping every non-digit manufactures a fake friend code

## Symptom

A user pastes obvious garbage into `/register` — say `00000002ie1oi2ee` — and instead of
"that's not a friend code", the bot friends a stranger (or, worse, silently proceeds as if a
9-digit code were entered) and reports "no such player" for something that was never a code
in the first place.

## Cause

lowiro's `add_friend` endpoint does **not** validate friend-code shape server-side. Verified
live (2026-07-17): a well-formed nonexistent code (`000000000`), a too-short code
(`0000000`), and a 16-character alphanumeric string (`00000002ie1oi2ee`) all return the
**identical** `404 {"success":false,"error_code":401}` — the same "player not found" the
server gives for a legitimate typo. There is no distinct malformed-input error code; lowiro
treats "not a real code" and "not even a code" identically. So whatever local validation the
bot does *is the only thing* that can distinguish "you typed garbage" from "you typed a real
9-digit code that happens not to exist".

`00000002ie1oi2ee` is not an arbitrary example — it is the specific string a naive "strip
every non-digit" rule reduces to a plausible-looking 9-digit code: stripping the letters
`i`, `e`, `o` from `00000002ie1oi2ee` leaves `000000022`, nine digits, which the bot would
then happily send to lowiro as if the user had typed a real code.

## The wrong fix

**"Strip every non-digit from the input"** — the old client's rule. It looks generous
(handles copy-paste noise, stray letters, whatever) but it manufactures a plausible 9-digit
code out of garbage input rather than rejecting it. The failure mode is not a crash; it is a
**wrong, misleading success** — the bot proceeds to call lowiro with a fabricated code and
then reports "no such player" for something the user never actually typed as a code, which
is a confusing and unactionable message.

## The right handling

`src/coda/utils/friend_code.py::clean_friend_code` strips **separators only** — whitespace,
hyphens, underscores, dots (`_SEPARATORS = re.compile(r"[\s\-_.]+")`) — so `123 456-789`
normalizes to `123456789`, but any letter anywhere in the input makes the regex match fail
and raises `InvalidFriendCode` immediately. This runs **before any network call**, in both
`RegistrationService.register_by_code` and `reserved.check_static`'s call site, precisely
because lowiro's own answer (`401`, indistinguishable from a real typo) tells the user
nothing useful — local validation is what buys the honest "that's not a friend code"
message instead.

## Regression signal

Watch for any code path that calls `re.sub(r"\D", "", raw)` (or equivalent "keep only
digits") instead of the separators-only pattern, or that constructs a friend code from user
input without going through `clean_friend_code` first. A user report of "the bot said 'no
such player' for something that clearly wasn't a real code" is the field signal.
