"""Login. Returns a session; never persists one."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from coda.arcaea.client import request_with_cookie
from coda.arcaea.errors import UnexpectedResponse, raise_for_login_envelope

logger = logging.getLogger(__name__)

# The cookie's Expires is always issued +30d, and it does NOT slide.
SESSION_LIFETIME = timedelta(days=30)


async def login(email: str, password: str) -> tuple[str, datetime]:
    """Authenticate and return ``(sid, expires_at)``.

    Raises :class:`~coda.arcaea.errors.InvalidCredentials` on a 403 (terminal --
    the caller deactivates the row and must never retry).

    The response body is only ``{"isLoggedIn": true}``; auth lives entirely in
    the ``sid`` cookie, so a client that ignores Set-Cookie gets nothing usable.
    """
    body, sid, status = await request_with_cookie(
        "POST", "/auth/login", json_body={"email": email, "password": password}
    )

    # Raises InvalidCredentials on the {"error": {...}} envelope under a genuine
    # 403. This is the only call site: the shape is login-specific, and the
    # login success body has no "success" key at all, so raise_for_envelope
    # never applies here.
    raise_for_login_envelope(status, body)

    if not (isinstance(body, dict) and body.get("isLoggedIn")):
        raise UnexpectedResponse(f"login returned an unrecognised body: {body!r}")

    if sid is None:
        # 200 + isLoggedIn but no cookie should be impossible; if lowiro ever
        # moves auth off the cookie this is where we find out.
        raise UnexpectedResponse("login succeeded but set no sid cookie")

    expires_at = datetime.now(UTC) + SESSION_LIFETIME
    logger.info("logged in %s, session expires %s", _redact(email), expires_at.date())
    return sid, expires_at


def _redact(email: str) -> str:
    """Mask an email for logs -- these lines reach shared log sinks."""
    local, _, domain = email.partition("@")
    head = local[:2] if len(local) > 2 else local[:1]
    return f"{head}***@{domain}" if domain else f"{head}***"
