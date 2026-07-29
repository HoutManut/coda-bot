"""Don't post a play to a surface that has already shown it.

``/recent`` *causes* the duplicate it looks like a victim of: it drives a real
poll cycle, that cycle ingests the play, and the poster consumes exactly those
new plays. Whenever ``/recent`` surfaces a play the poller had not stored yet, a
live update for that same play follows. Common case, not a corner case.

Suppression is per DESTINATION, not per requester. ``/recent``'s success reply
is public (it defers without ``ephemeral``, and a deferred response fixes its
flags at defer time), so the channel it replied in has genuinely shown the play
to everyone watching -- including anyone co-linked to the same Arcaea account,
who would have received that one shared message. If the user's live destination
is a *different* channel, that channel has shown nothing and still gets its
post; a DM key carries the ``discord_id``, so one user's ``/recent`` never
suppresses another's DM.

Deliberately NOT suppressed across destinations: a ``/recent`` run in a channel
leaves the user's DM copy alone, because the DM is their archive.
"""

from __future__ import annotations

from time import monotonic

# ("channel", channel_id) or ("dm", discord_id) -- the same key the poster sends
# on, so "did this surface already show it" is one lookup.
type Destination = tuple[str, int]

# Bounds memory only. It can never suppress a LATER sighting of the same play,
# because there is no later sighting -- ingest offers a play exactly once, ever.
TTL = 900.0


class PostSuppressor:
    """Plays a destination has already displayed. In-memory, expiring.

    Process-local by design: a restart mid-window costs one duplicate, which is
    not worth a table.
    """

    def __init__(self) -> None:
        self._marks: dict[tuple[Destination, int], float] = {}

    def mark(self, destination: Destination, play_score_id: int) -> None:
        """Record that ``destination`` has shown this play."""
        now = monotonic()
        self._prune(now)
        self._marks[(destination, play_score_id)] = now

    def suppressed(self, destination: Destination, play_score_id: int) -> bool:
        """Whether ``destination`` already showed this play, recently enough."""
        marked_at = self._marks.get((destination, play_score_id))
        if marked_at is None:
            return False
        if monotonic() - marked_at > TTL:
            del self._marks[(destination, play_score_id)]
            return False
        return True

    def _prune(self, now: float) -> None:
        expired = [key for key, at in self._marks.items() if now - at > TTL]
        for key in expired:
            del self._marks[key]
