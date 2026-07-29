"""The single HTTP funnel to lowiro's private webapi.

Every request in this package goes through :func:`request`, which is what makes
rate limiting and envelope parsing single-point rather than sprinkled.

This module -- and this package -- **never imports coda.db and never persists
anything**. ``auth.login`` returns a sid; the caller writes it. That is the whole
reason no session-store protocol needs injecting here.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

import aiohttp

from coda.arcaea import identity
from coda.arcaea.errors import ArcaeaError, TransportError, UnexpectedResponse

logger = logging.getLogger(__name__)

BASE_URL = "https://webapi.lowiro.com"

# Rate limiting under real load is completely untested -- every capture to date
# is a handful of manual requests. Start conservative; this is the one knob.
# All bot accounts share one host and one IP, so the limit is GLOBAL, not
# per-session. (Per-session locks exist too, in sessions/session.py, but they
# prevent double-login rather than flooding -- different concern, both needed.)
MAX_CONCURRENT = 2
MIN_INTERVAL = 0.5

# Explicit and deliberately short of aiohttp's 300 s default. lowiro's origin is
# PROVEN capable of hanging a request open (the FormData capture: it sat until
# Cloudflare's 100 s gateway timeout) and nothing guarantees Cloudflare cuts
# every hang. A hung request holds one of MAX_CONCURRENT limiter slots AND its
# account's login lock, so an unbounded wait stalls the whole wire layer -- 30 s
# turns that into a typed, skippable TransportError instead.
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)


def _headers() -> dict[str, str]:
    """Mirror the site's real browser headers for the current bot account.

    Spoofing is insurance, not a requirement: a bare curl with a default UA and
    no Origin/Referer returns 200 today. Keep it anyway -- Cloudflare fronts this
    API and can tighten bot rules with no notice, the cost is a static dict, and
    the bot accounts are hand-made and unreplaceable.

    The UA and ``sec-ch-ua*`` triplet come from the account's bound
    :mod:`~coda.arcaea.identity` -- one fixed, self-consistent Chrome build per
    account -- so a rotating UA can never contradict a frozen platform hint. The
    rest are the constants a real Chrome XHR to this API sends: ``sec-fetch-*``
    describe a same-site CORS fetch, and ``Priority`` is what Chrome tags an XHR.
    """
    who = identity.current()
    return {
        "Origin": "https://arcaea.lowiro.com",
        "Referer": "https://arcaea.lowiro.com/",
        "User-Agent": who["user_agent"],
        "sec-ch-ua": who["sec_ch_ua"],
        "sec-ch-ua-mobile": who["sec_ch_ua_mobile"],
        "sec-ch-ua-platform": who["sec_ch_ua_platform"],
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "sec-fetch-site": "same-site",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
        "Priority": "u=1, i",
    }


class _RateLimiter:
    """A concurrency cap plus a floor on the gap between request starts.

    Any bulk walk must share this instance so it cannot starve the poller.
    """

    def __init__(self, max_concurrent: int, min_interval: float) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._min_interval = min_interval
        self._lock = asyncio.Lock()
        self._last_start = 0.0

    async def __aenter__(self) -> None:
        await self._semaphore.acquire()
        # If cancellation lands in the wait below, __aenter__ never returns, the
        # async-with body is never entered, and __aexit__ never runs -- so the
        # acquired slot must be given back here or it leaks permanently.
        # BaseException because CancelledError is not an Exception.
        try:
            async with self._lock:
                wait = self._last_start + self._min_interval - time.monotonic()
                if wait > 0:
                    await asyncio.sleep(wait)
                self._last_start = time.monotonic()
        except BaseException:
            self._semaphore.release()
            raise

    async def __aexit__(self, *exc: object) -> None:
        self._semaphore.release()


_limiter = _RateLimiter(MAX_CONCURRENT, MIN_INTERVAL)
_session: aiohttp.ClientSession | None = None


def encode_multipart(fields: dict[str, str]) -> tuple[bytes, str]:
    """Build a multipart/form-data body by hand. Returns ``(body, content_type)``.

    Do not replace with `aiohttp.FormData` -- see wiki/gotchas/w-formdata-504.md.
    Values are validated, not escaped: a name or value containing CRLF or the
    boundary token raises ``ArcaeaError`` rather than corrupting the framing.
    """
    boundary = f"----WebKitFormBoundary{uuid.uuid4().hex[:16]}"
    for name, value in fields.items():
        for label, token in (("name", name), ("value", value)):
            if "\r" in token or "\n" in token or boundary in token:
                raise ArcaeaError(
                    f"multipart {label} contains an unframable character "
                    "(CRLF or boundary)"
                )
    parts = [
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
        f"{value}\r\n"
        for name, value in fields.items()
    ]
    parts.append(f"--{boundary}--\r\n")
    return "".join(parts).encode(), f"multipart/form-data; boundary={boundary}"


def _get_session() -> aiohttp.ClientSession:
    """One ClientSession for the process, created lazily.

    Created on first use rather than at import so importing this module never
    requires a running event loop.

    Uses a ``DummyCookieJar`` so the session stores and sends NOTHING from a jar:
    every sid is passed as an explicit Cookie header instead. This is not an
    optimization, it is correctness. lowiro sets the ``sid`` with ``Domain=lowiro.com``
    (not ``webapi.lowiro.com``), and a default aiohttp jar matches cookies against
    parent domains -- so it would store one account's sid and then merge it into
    the Cookie header of a request meant for a DIFFERENT account, silently sending
    account A's session as account B. With N bot accounts sharing this one session
    that is a cross-account auth leak. A no-op jar makes the explicit header the
    only source of the sid. ``request_with_cookie`` still reads the login's Set-Cookie
    via ``resp.cookies``, which is parsed from the response directly and does not
    depend on the jar.
    """
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            cookie_jar=aiohttp.DummyCookieJar(), timeout=REQUEST_TIMEOUT
        )
        logger.debug("created aiohttp session for %s", BASE_URL)
    return _session


async def close() -> None:
    """Close the shared session. Call on bot shutdown."""
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
        logger.info("closed arcaea http session")
    _session = None


# --- TEMPORARY INSTRUMENT: tear down once the limit's shape is known ---------
# _DIAGNOSTIC_HEADERS / _diagnostics / _is_pushback / _log_non_2xx exist to
# answer one open question: what does lowiro (or Cloudflare in front of it) do
# under real polling load? Nothing else reads them and no behaviour depends on
# them. Once a genuine 429 or challenge has been observed and written down in
# `wiki/domains/auth-and-sessions.md`, delete this block -- keep at most the
# pushback WARNING as a live alert. Leaving the full capture in permanently
# means a log file accumulating envelope-failure noise forever for no reader.
#
# Whitelisted headers, never dumped wholesale: the same response carries
# Set-Cookie, and that is a live sid. None of these has ever appeared in a
# capture -- which is the point; the first real limit announces itself in one of
# them or in a Cloudflare challenge body.
_DIAGNOSTIC_HEADERS = (
    "Retry-After",
    "RateLimit",
    "RateLimit-Policy",
    "X-RateLimit-Limit",
    "X-RateLimit-Remaining",
    "X-RateLimit-Reset",
    "cf-ray",
    "cf-mitigated",
    "Server",
)

# Statuses that mean infrastructure pushed back rather than lowiro answering.
# 401/403/404 are excluded deliberately -- they are the NORMAL envelope failures
# (a missing friend is a 404), so warning on them would bury the real signal.
_PUSHBACK_STATUSES = frozenset({408, 429})

# Paths whose request carried a password. Their response body is never logged --
# only the status and the whitelisted headers, which is all the rate-limit
# signal we want from them anyway. Today the login body is just
# ``{"isLoggedIn": true}`` or an error envelope, but "the credential path never
# emits a body into a log file" is the invariant, not a fact about today's shape.
_CREDENTIAL_PATHS = ("/auth/login",)


def _diagnostics(resp: aiohttp.ClientResponse) -> str:
    """Render the whitelisted rate-limit/CDN headers present on a response."""
    found = {k: resp.headers[k] for k in _DIAGNOSTIC_HEADERS if k in resp.headers}
    return repr(found) if found else "no rate-limit headers"


def _is_pushback(resp: aiohttp.ClientResponse) -> bool:
    """True if the reply looks like a limiter or WAF rather than the API."""
    return (
        resp.status in _PUSHBACK_STATUSES
        or resp.status >= 500
        or "cf-mitigated" in resp.headers
        or "Retry-After" in resp.headers
    )


def _loggable(path: str, body: Any) -> Any:
    """The body as it may be written to a log -- redacted on credential paths."""
    return "<redacted: credential path>" if path in _CREDENTIAL_PATHS else body


def _log_non_2xx(
    resp: aiohttp.ClientResponse, method: str, path: str, body: Any
) -> None:
    """Record status, body shape and rate-limit headers for any non-2xx reply.

    Pure observation -- the envelope rule still stands, callers branch on the
    body and never on the status. This exists because every capture to date is a
    handful of manual requests, so the shape of a real rate limit is unknown;
    deliberately probing for it risks a hand-made, unreplaceable bot account,
    and passive logging learns the same thing for free the first time it happens.

    Forced onto the file handler regardless of its threshold: routine envelope
    failures are DEBUG-worthy on a console but are exactly the record we want on
    disk when a limit finally shows up weeks from now.

    Only a **pushback** reply is forced to discord -- it is the one that answers
    the open question, and it should arrive as a ping rather than be found later
    in a file. Routine envelope failures (a 404 for a missing friend, a 401 for a
    dead session) are explicitly held back: they happen constantly, and this
    routing must not start posting them if the discord threshold is ever lowered.
    A cloaked 403 lands in the pushback set on its ``cf-mitigated`` header, which
    is exactly what separates it from a login 403.
    """
    if 200 <= resp.status < 300:
        return
    # Envelope failures are routine and would drown the console at WARNING.
    pushback = _is_pushback(resp)
    level = logging.WARNING if pushback else logging.DEBUG
    logger.log(
        level,
        "%s %s -> HTTP %s [%s] body=%.200s",
        method,
        path,
        resp.status,
        _diagnostics(resp),
        _loggable(path, body),
        extra={"file": True, "discord": pushback},
    )


async def _decode_json(resp: aiohttp.ClientResponse, method: str, path: str) -> Any:
    """Decode the response as JSON, or raise :class:`UnexpectedResponse`.

    Also logs any non-2xx reply on the way through -- the one funnel every
    response passes, so no call site can forget.
    """
    try:
        body = await resp.json(content_type=None)
    except ValueError:
        # Only decode the raw text on the failure path -- the body is
        # already cached by the failed json() read, so this is free here
        # and skipped entirely on the common success path.
        text = await resp.text()
        # A non-JSON body is the single most likely form of a WAF block, so this
        # one carries the headers too, stays at ERROR regardless of status, and
        # goes to discord unconditionally -- a challenge page is the single
        # strongest evidence available about what is rate limiting us, and it is
        # rare enough that forcing it can never become noise.
        logger.error(
            "%s %s returned non-JSON (HTTP %s) [%s]: %.200s",
            method,
            path,
            resp.status,
            _diagnostics(resp),
            _loggable(path, text),
            extra={"file": True, "discord": True},
        )
        raise UnexpectedResponse(
            f"{method} {path} returned non-JSON (HTTP {resp.status})"
        ) from None
    _log_non_2xx(resp, method, path, body)
    return body


async def request(
    method: str,
    path: str,
    *,
    sid: str | None = None,
    json_body: dict[str, Any] | None = None,
    form: dict[str, str] | None = None,
) -> Any:
    """Perform one rate-limited request and return the decoded JSON body.

    ``form`` is encoded by :func:`encode_multipart`, never ``aiohttp.FormData``.
    Does not interpret the body -- callers pass it to
    :func:`errors.raise_for_envelope`. Raises :class:`UnexpectedResponse` for a
    non-JSON response and :class:`TransportError` for no response at all, so the
    full failure surface is typed ``ArcaeaError``.

    The sid is sent as an explicit Cookie header, never via a cookie jar -- see
    wiki/modules/arcaea.md on ``DummyCookieJar``.
    """
    headers = _headers()
    if sid is not None:
        headers["Cookie"] = f"sid={sid}"

    data: bytes | None = None
    if form is not None:
        data, content_type = encode_multipart(form)
        headers["Content-Type"] = content_type

    url = f"{BASE_URL}{path}"
    async with _limiter:
        logger.debug("%s %s (authed=%s)", method, path, sid is not None)
        session = _get_session()
        # TimeoutError and ConnectionResetError are both OSError subclasses, so
        # (ClientError, OSError) is the whole "no response body" surface.
        try:
            async with session.request(
                method, url, headers=headers, json=json_body, data=data
            ) as resp:
                # Status is never branched on: on /webapi/* it is noise. A
                # non-2xx one is logged inside _decode_json, for every caller.
                return await _decode_json(resp, method, path)
        except (aiohttp.ClientError, OSError) as exc:
            logger.warning("%s %s transport failure: %r", method, path, exc)
            raise TransportError(f"{method} {path}: {exc!r}") from exc


async def request_with_cookie(
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
) -> tuple[Any, str | None]:
    """Like :func:`request`, but also returns the ``sid`` the response set.

    Only login needs this. The sid rotates at every auth boundary, so it must be
    captured from the login response and never from an earlier one.
    """
    headers = _headers()
    if json_body is not None:
        headers["Content-Type"] = "application/json;charset=UTF-8"

    url = f"{BASE_URL}{path}"
    async with _limiter:
        logger.debug("%s %s (capturing sid)", method, path)
        session = _get_session()
        try:
            async with session.request(method, url, headers=headers, json=json_body) as resp:
                body = await _decode_json(resp, method, path)
                cookie = resp.cookies.get("sid")
                return body, cookie.value if cookie is not None else None
        except (aiohttp.ClientError, OSError) as exc:
            logger.warning("%s %s transport failure: %r", method, path, exc)
            raise TransportError(f"{method} {path}: {exc!r}") from exc
