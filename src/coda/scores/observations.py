"""The last play -- and PTT rating -- the poller SAW for an account, stored or not.

This exists for one case: an account with tracking off is still fetched -- an
on-demand ``/recent`` polls it -- but its plays never reach ``play_scores``.

Not storage: entries expire, nothing is durable, and a restart empties it. The
poller fills it for EVERY observed play, tracked or not, so the read path has no
tracking branch -- for a tracked account the cache and the DB simply agree.

Rating is cached alongside but never persisted anywhere: it is read only to
decide whether a player currently hides their PTT, and a stale "visible" answer
would leak a number they just hid.
"""

from __future__ import annotations

from time import monotonic

from coda.arcaea.dto.score import ScoreResult

# How long an observation stays servable. Long enough to cover a slow refresh
# and a user re-running the command, short enough that a play from an hour ago
# is never presented as the current one.
TTL = 300.0


class ObservationCache:
    """Latest observed play per ``arc_user_id``. In-memory, expiring."""

    def __init__(self) -> None:
        self._entries: dict[int, tuple[ScoreResult, float]] = {}
        self._ratings: dict[int, tuple[float | None, float]] = {}

    def record(self, result: ScoreResult) -> None:
        """Remember a play, unless an older one would overwrite a newer one.

        The guard is on ``time_played`` rather than arrival order: keys are
        polled out of order, so a later call is not a later play.

        It is deliberately strict (``>``, not ``>=``), which means an equal
        ``time_played`` overwrites. That is only safe because one path authors
        any given play (``poller._friend_scores``) -- when both did, a
        detail-less friend sighting could replace the detailed own one.
        """
        existing = self._entries.get(result.arc_user_id)
        if existing is not None and existing[0].time_played > result.time_played:
            return
        self._entries[result.arc_user_id] = (result, monotonic())

    def latest(self, arc_user_id: int) -> ScoreResult | None:
        """The account's last observed play, or None once it has expired."""
        entry = self._entries.get(arc_user_id)
        if entry is None:
            return None
        result, recorded_at = entry
        if monotonic() - recorded_at > TTL:
            del self._entries[arc_user_id]
            return None
        return result

    def record_rating(self, arc_user_id: int, rating: float | None) -> None:
        """Remember a fetched PTT, where None is the wire's hidden sentinel.

        No ordering guard, unlike :meth:`record`: a rating is a current-state
        reading, not a play, so the newest fetch always wins.
        """
        self._ratings[arc_user_id] = (rating, monotonic())

    def latest_rating(self, arc_user_id: int) -> tuple[float | None, bool]:
        """``(rating, was_observed)``. ``was_observed=False`` means never fetched
        or expired -- callers must treat that as hidden, never as visible."""
        entry = self._ratings.get(arc_user_id)
        if entry is None:
            return None, False
        rating, recorded_at = entry
        if monotonic() - recorded_at > TTL:
            del self._ratings[arc_user_id]
            return None, False
        return rating, True
