"""Typed exceptions, and the one place a lowiro response envelope is read.

Three unrelated error envelopes exist; branch on the body, never the status --
see wiki/gotchas/w-status-vs-body.md and wiki/gotchas/w-third-auth-envelope.md.
:func:`raise_for_login_envelope` reads the login envelope, :func:`raise_for_envelope`
the other two.
"""

from __future__ import annotations

from typing import Any


class ArcaeaError(Exception):
    """Base for every error raised out of this package."""


class ApiError(ArcaeaError):
    """An ``error_code`` we have no specific handling for.

    On ``add_friend`` this means "this account is unusable for this player, try
    the next one" -- which covers the cap-exceeded case without our knowing its
    code (it has never been captured).
    """

    def __init__(self, error_code: int | None, body: Any = None) -> None:
        self.error_code = error_code
        self.body = body
        super().__init__(f"lowiro returned error_code {error_code}")


class TransportError(ArcaeaError):
    """The request never produced a response body: DNS, TCP, TLS, or timeout.

    TRANSIENT, and account-agnostic -- it says nothing about the credentials,
    the session, or the player. Raised by ``client.request`` so that every
    ``except ArcaeaError`` (pool skip-and-continue, release's never-raise
    contract) covers a network blip the same way it covers a bad envelope.

    For a write (``add_friend``/``remove_friend``) the outcome is AMBIGUOUS --
    lowiro may or may not have processed it before the connection died. Callers
    must not blind-retry a write; the 602/AlreadyFriend recovery and reconcile
    exist to absorb exactly this drift.
    """


class SessionExpired(ArcaeaError):
    """``error_code: 203`` -- no valid session. TRANSIENT.

    Spans absent, unauthenticated, and tampered cookies alike. This is the
    authoritative "session is dead" signal; ``expires_at`` is only an
    optimization. Re-login once, retry once, then fail. Never loop.
    """


class PlayerNotFound(ArcaeaError):
    """``error_code: 401`` -- no such friend code. A PLAYER error, not an account one.

    Must NOT flag the bot account and must NOT trigger a next-account retry:
    every account returns 401 for the same nonexistent code. Fail to the user.
    This is the distinction that is easiest to get backwards.
    """


class AlreadyFriend(ArcaeaError):
    """``error_code: 602`` -- already on this account's friends list.

    Recoverable, but the error body carries no friends list to diff, so the
    caller must re-read /friend/me to find the player.
    """


class InvalidCredentials(ArcaeaError):
    """403 from /auth/login. TERMINAL.

    Credentials are wrong and will not fix themselves. Deactivate the row and
    stop.
    """


class UnexpectedResponse(ArcaeaError):
    """The body was not shaped like either known envelope.

    Raised instead of a bare KeyError so that "lowiro changed the API" is
    distinguishable from a bug in our own parsing.
    """


# error_code -> exception. Anything absent becomes ApiError, deliberately:
# unknown codes must stay recoverable rather than crash a poll.
_CODES: dict[int, type[ArcaeaError]] = {
    203: SessionExpired,
    401: PlayerNotFound,
    602: AlreadyFriend,
}


def raise_for_login_envelope(status: int, body: Any) -> None:
    """Raise :class:`InvalidCredentials` if ``body`` is /auth/login's rejection.

    Kept separate from :func:`raise_for_envelope` on purpose: the
    ``{"error": {...}}`` shape is a *login* envelope, and only ``/auth/login``
    may interpret it. A ``/webapi/*`` body that ever grows an ``error`` key is
    an API change to surface as UnexpectedResponse -- not a reason to declare
    working credentials terminally dead.

    Terminal ONLY on an actual HTTP 403 -- lowiro's real "wrong password" reply.
    A Cloudflare/gateway error page during an outage can carry the exact same
    ``{"error": {...}}`` shape under a 500, and that must never be read as a
    dead credential: it deactivates a hand-made, unreplaceable bot account for
    something that fixes itself when lowiro comes back. See
    wiki/gotchas/w-login-403-not-status-gated.md.
    """
    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict):
        return
    detail = f"{error.get('name')} {error.get('message')}"
    if status != 403:
        raise UnexpectedResponse(
            f"login returned an error-shaped body under HTTP {status}, not 403 "
            f"-- treating as transient, not a dead credential: {detail}"
        )
    raise InvalidCredentials(f"login rejected: {detail}")


def raise_for_envelope(body: Any) -> dict[str, Any]:
    """Validate a ``/webapi/*`` response body, raising the typed error it carries.

    Returns the body unchanged on success so callers can chain. The HTTP status
    is deliberately not a parameter -- it carries no information this does not,
    and accepting it would invite branching on it. The login envelope is NOT
    handled here -- see :func:`raise_for_login_envelope`.
    """
    if not isinstance(body, dict):
        raise UnexpectedResponse(f"expected a JSON object, got {type(body).__name__}")

    if body.get("success") is True:
        return body

    # The HTTP-401 dead-session envelope. Same meaning as error_code 203 -- the
    # authenticated sid was rejected -- so re-login once. Kept specific: an
    # unknown "code" still falls through to UnexpectedResponse rather than being
    # silently retried.
    if body.get("code") == "UnauthorizedError":
        raise SessionExpired(f"session rejected: {body.get('message')!r}")

    if body.get("success") is False:
        code = body.get("error_code")
        specific = _CODES.get(code) if isinstance(code, int) else None
        if specific is not None:
            raise specific(f"lowiro returned error_code {code}")
        raise ApiError(code, body)

    raise UnexpectedResponse(f"unrecognized envelope: {body!r}")
