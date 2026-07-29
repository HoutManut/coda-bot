"""Per-account browser identity for request cloaking.

Each account -- bot or player -- uses ONE fixed, coherent Chrome build
for its whole life.
"""

from __future__ import annotations

import contextlib
import contextvars
import random
from collections.abc import Iterator
from typing import NamedTuple, TypedDict


class BrowserIdentity(TypedDict):
    """One coherent Chrome header set. Stored verbatim as JSONB on the row."""

    user_agent: str
    sec_ch_ua: str
    sec_ch_ua_platform: str
    sec_ch_ua_mobile: str


class _Platform(NamedTuple):
    ua_token: str
    sec_ch_ua_platform: str


# Desktop platforms. ua_token and sec_ch_ua_platform are the two halves of the
# same fact, kept together so a generated pair can never disagree.
PLATFORMS: list[_Platform] = [
    _Platform("Windows NT 10.0; Win64; x64", '"Windows"'),
    _Platform("Macintosh; Intel Mac OS X 10_15_7", '"macOS"'),
    _Platform("X11; Linux x86_64", '"Linux"'),
    _Platform("X11; CrOS x86_64 14541.0.0", '"Chrome OS"'),
]

# Chrome major versions to draw from.
CHROME_VERSIONS: list[int] = list(range(116, 139))  # ceiling last bumped 2026-07

# The GREASE brand Chrome mixes into sec-ch-ua to keep parsers honest. The exact
# token and version vary across builds; these are all real forms Chrome has
# shipped.
GREASE_BRANDS: list[str] = [
    '"Not_A Brand";v="24"',
    '"Not)A;Brand";v="99"',
    '"Not/A)Brand";v="8"',
    '"Not-A.Brand";v="99"',
    '"Not.A/Brand";v="24"',
    '"Not;A=Brand";v="99"',
]


def generate() -> BrowserIdentity:
    """Build a fresh, internally consistent Chrome identity.

    Everything derives from one ``(platform, major)`` pair, so UA, ``sec-ch-ua``
    and platform hint agree by construction. Called once at seed time to give an
    account its permanent build; re-seeding an existing account should keep its
    stored one rather than call this again -- a browser does not change overnight.
    """
    platform = random.choice(PLATFORMS)
    major = random.choice(CHROME_VERSIONS)
    ua = (
        f"Mozilla/5.0 ({platform.ua_token}) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"
    )
    # Chrome randomizes the order of the three brands per build; mirror that.
    brands = [
        f'"Chromium";v="{major}"',
        f'"Google Chrome";v="{major}"',
        random.choice(GREASE_BRANDS),
    ]
    random.shuffle(brands)
    return BrowserIdentity(
        user_agent=ua,
        sec_ch_ua=", ".join(brands),
        sec_ch_ua_platform=platform.sec_ch_ua_platform,
        sec_ch_ua_mobile="?0",
    )


# The header set used when no identity is bound (a hand-inserted row that was
# never seeded, or a stray call outside any session).
DEFAULT_IDENTITY: BrowserIdentity = {
    "user_agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
    ),
    "sec_ch_ua": (
        '"Google Chrome";v="138", "Chromium";v="138", "Not_A Brand";v="24"'
    ),
    "sec_ch_ua_platform": '"Windows"',
    "sec_ch_ua_mobile": "?0",
}


def coerce(raw: object) -> BrowserIdentity | None:
    """Validate a stored ``browser_identity`` JSONB blob into an identity.

    Defensive, in the DTO spirit: a row written by an older seed (or hand-edited)
    may be missing keys, and a partial set is worse than the default because it
    is inconsistent. All four keys present and stringy, or fall back to None.
    """
    if not isinstance(raw, dict):
        return None
    keys = ("user_agent", "sec_ch_ua", "sec_ch_ua_platform", "sec_ch_ua_mobile")
    if not all(isinstance(raw.get(k), str) for k in keys):
        return None
    return BrowserIdentity(**{k: raw[k] for k in keys})  # type: ignore[typeddict-item]


_current: contextvars.ContextVar[BrowserIdentity | None] = contextvars.ContextVar(
    "arcaea_browser_identity", default=None
)


@contextlib.contextmanager
def bind(identity: BrowserIdentity | None) -> Iterator[None]:
    """Bind ``identity`` for every wire request in this task, restoring on exit.

    ``None`` is allowed and binds nothing (``current`` falls back to the
    default): a caller can pass a row's stored identity straight through without
    first checking whether it has one.
    """
    token = _current.set(identity)
    try:
        yield
    finally:
        _current.reset(token)


def current() -> BrowserIdentity:
    """The bound identity, or :data:`DEFAULT_IDENTITY` if none. Never None, so
    ``_headers`` always emits a complete, consistent set."""
    return _current.get() or DEFAULT_IDENTITY
