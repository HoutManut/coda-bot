"""The last play the poller SAW for an account, stored or not.

This exists for one case: an account with tracking off is still fetched -- an
on-demand ``/recent`` polls it -- but its plays never reach ``play_scores``, so
there is nothing for the command to read back. Writing the row and deleting it
afterwards would leak on a crash and would fire the live-update feed's "new
play" signal on the way through, so the observation is handed over in memory
instead.

Not storage: entries expire, nothing is durable, and a restart empties it. The
poller fills it for EVERY observed play, tracked or not, so the read path has no
tracking branch -- for a tracked account the cache and the DB simply agree.
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

    def record(self, result: ScoreResult) -> None:
        """Remember a play, unless an older one would overwrite a newer one.

        A cycle can observe the same account on both paths, and the friend path
        may lag the own path by a poll interval, so the guard is on
        ``time_played`` rather than arrival order.
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
