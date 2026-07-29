"""Friend-code normalization and validation."""

from __future__ import annotations

import re

CODE_LENGTH = 9

_SEPARATORS = re.compile(r"[\s\-_.]+")
_NINE_DIGITS = re.compile(rf"^\d{{{CODE_LENGTH}}}$")


class InvalidFriendCode(ValueError):
    """Input is not shaped like a friend code."""


def clean_friend_code(raw: str) -> str:
    """Normalize user input to a bare 9-digit code.

    Raises :class:`InvalidFriendCode` if it is not one. Callers should surface
    that as "that's not a friend code" -- a different message from a code that
    is well-formed but unknown.
    """
    cleaned = _SEPARATORS.sub("", raw.strip())
    if not _NINE_DIGITS.match(cleaned):
        raise InvalidFriendCode(
            f"a friend code is exactly {CODE_LENGTH} digits; got {raw!r}"
        )
    return cleaned
