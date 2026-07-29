"""Ingest observed plays into ``play_scores``.

Identity is the wire tuple ``(arcaea_account_id, wire_song_id, wire_difficulty,
score, time_played)``, shared by friend and own sightings; friend `DO NOTHING`,
own `DO UPDATE` on detail columns. ``source`` is derived from `play_id is not
None`. See wiki/modules/scores.md.

The poller no longer routes a play down both paths (``_friend_scores`` yields
own-covered players), so a cross-path conflict is now only reachable in the
window where a player gains or loses own credentials. The conflict handling
below stays as the backstop for exactly that -- it is not the steady state.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from sqlalchemy import literal_column, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from coda.arcaea.dto.score import ScoreResult
from coda.db.models import ArcaeaAccount, PlayScore

logger = logging.getLogger(__name__)

# Columns an own sighting fills; a friend sighting never writes these, so it
# cannot overwrite them with NULLs on a row that already has them.
_DETAIL_COLUMNS = (
    "shiny_pure_count",
    "pure_count",
    "far_count",
    "lost_count",
    "health",
    "clear_type",
    "modifier",
    "wire_play_id",
)


class ScoreStore:
    """Stateless; takes the session per call, like RegistrationService."""

    async def ingest(
        self, db: AsyncSession, results: Iterable[ScoreResult]
    ) -> list[int]:
        """UPSERT observed plays; return the row ids that were genuinely new.

        "New" means a first-time INSERT of that identity -- not an own sighting
        enriching a row a friend sighting already wrote. That subset is what the
        live-update feed posts; enrichment is silent.

        Row ids, not ``ScoreResult``s: the poster reads the row back in its own
        session, since the poller's is short-lived and detaches anything it
        returns moments later. Ids come out in ``results`` order, so a caller
        that sorts by ``time_played`` first gets a time-ordered batch for free.

        A ``ScoreResult`` whose ``arc_user_id`` maps to no ``ArcaeaAccount`` is
        skipped (we know no such player). So is one whose account has
        ``tracking_enabled=False`` -- this is the single choke point both read
        paths pass through, so the opt-out is enforced here and nowhere else.
        The caller is responsible for not passing never-played placeholders --
        an empty ``recent_score`` yields no ``ScoreResult`` in the first place.
        """
        results = list(results)
        if not results:
            return []

        accounts = await self._resolve_accounts(db, results)

        new_play_ids: list[int] = []
        for result in results:
            account = accounts.get(result.arc_user_id)
            if account is None:
                logger.debug(
                    "score for unknown arc_user_id %s -- skipping", result.arc_user_id
                )
                continue
            account_id, tracking_enabled = account
            if not tracking_enabled:
                logger.debug(
                    "score for account %s whose tracking is off -- not recording",
                    account_id,
                )
                continue
            inserted_id = await self._upsert(db, result, account_id)
            if inserted_id is not None:
                new_play_ids.append(inserted_id)
        return new_play_ids

    async def _resolve_accounts(
        self, db: AsyncSession, results: list[ScoreResult]
    ) -> dict[int, tuple[int, bool]]:
        """Map each ``arc_user_id`` to ``(arcaea_accounts.id, tracking_enabled)``."""
        arc_ids = {r.arc_user_id for r in results}
        rows = await db.execute(
            select(
                ArcaeaAccount.arc_user_id,
                ArcaeaAccount.id,
                ArcaeaAccount.tracking_enabled,
            ).where(ArcaeaAccount.arc_user_id.in_(arc_ids))
        )
        return {
            arc_user_id: (account_id, tracking_enabled)
            for arc_user_id, account_id, tracking_enabled in rows
        }

    async def _upsert(
        self, db: AsyncSession, result: ScoreResult, account_id: int
    ) -> int | None:
        """UPSERT one play. Return its id iff this was a first-time INSERT.

        The own path always returns a row (INSERT or UPDATE), so it cannot use
        row-presence to tell them apart; ``xmax = 0`` is Postgres's marker for a
        tuple inserted by this statement rather than updated. The friend path
        does DO NOTHING, so a returned row already means "inserted".
        """
        values = row_values(result, account_id)

        if result.play_id is None:
            # Friend sighting: identity only, yield to any existing row.
            stmt = (
                insert(PlayScore)
                .values(**values)
                .on_conflict_do_nothing(constraint="uq_play_identity")
                .returning(PlayScore.id)
            )
            return (await db.execute(stmt)).scalar_one_or_none()

        # Own sighting: enrich detail on conflict, leave the resolved chart FK
        # and observed_at alone (both belong to the first sighting).
        stmt = insert(PlayScore).values(**values)
        stmt = (
            stmt.on_conflict_do_update(
                constraint="uq_play_identity",
                set_={
                    col: getattr(stmt.excluded, col) for col in _DETAIL_COLUMNS
                }
                | {"source": stmt.excluded.source},
            )
            .returning(PlayScore.id, literal_column("(xmax = 0)").label("inserted"))
        )
        row_id, inserted = (await db.execute(stmt)).one()
        return row_id if inserted else None


def row_values(result: ScoreResult, account_id: int) -> dict[str, object]:
    """Flatten a ``ScoreResult`` into ``play_scores`` column values.

    ``source`` is derived from the presence of a play id: only the own endpoint
    supplies one. score/time_played are written verbatim -- score 0 is a real
    score, never coerced away.

    Public because ``/recent`` builds a DETACHED ``PlayScore`` from it to render
    a play that was observed but deliberately never stored (tracking off). That
    is the only legitimate use outside this module -- it maps columns, it does
    not decide anything.
    """
    return {
        "arcaea_account_id": account_id,
        "wire_song_id": result.song_id,
        "wire_difficulty": result.difficulty,
        "score": result.score,
        "time_played": result.time_played,
        "song_difficulty_id": result.difficulty_id,
        "shiny_pure_count": result.shiny_pure_count,
        "pure_count": result.pure_count,
        "far_count": result.far_count,
        "lost_count": result.lost_count,
        "health": result.health,
        "clear_type": result.clear_type,
        "modifier": result.modifier,
        "wire_play_id": result.play_id,
        "source": "own" if result.play_id is not None else "friend",
    }
