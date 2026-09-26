"""Score storage: persist observed plays and detect which are new.

The poller reads ``recent_score`` (one play per account) and hands the parsed
``ScoreResult``s here. This layer owns the UPSERT that turns a stream of
observations into durable rows, and reports the genuinely-new plays so the
live-update feed can post them.
"""

from __future__ import annotations

from coda.scores.coordinator import PollCoordinator
from coda.scores.observations import ObservationCache
from coda.scores.potential import PotentialService
from coda.scores.service import ScoreStore
from coda.scores.tracking import TrackingService

__all__ = [
    "ObservationCache",
    "PollCoordinator",
    "PotentialService",
    "ScoreStore",
    "TrackingService",
]
