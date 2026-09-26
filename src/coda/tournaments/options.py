"""The option tables a quick match is configured from. Pure -- no I/O.

One table per choice, mapping the STORED value to the label a picker shows.
Three surfaces offer the same choices -- the `/tournament quick` picker, the
`/config` enum behind it, and the resolver in `defaults.py` -- and they used to
spell each list out separately, so a new best-of was three edits and a silent
drift if you made two of them.

A leaf on purpose: `settings/registry.py` reads these, and anything that
imports `coda.settings` (as `defaults.py` does) cannot be what it reads.
"""

from __future__ import annotations

BEST_OF: dict[str, str] = {
    "1": "Best of 1",
    "3": "Best of 3",
    "5": "Best of 5",
    "7": "Best of 7",
}

# Public leads: it is the default, and a picker should open on it. A match
# thread is a room in a server, and a room nobody can look into cannot be
# joined, cheered at, or found again by anyone but the two people in it.
VISIBILITY: dict[str, str] = {
    "public": "Public",
    "private": "Private",
}


def values(table: dict[str, str]) -> tuple[str, ...]:
    """The stored values, for a ``ConfigKey``'s enum type."""
    return tuple(table)
