"""Decide whether one play is worth a live update, for one user.

Two kinds of setting, and the difference is the whole design:

* **Triggers** are OR-ed -- "is this play worth telling someone about".
* **Gates** are AND-ed over the result -- "do I care about this chart at all".

OR-ing a level gate would make "10+ only" a *reason* to post, so a level-3 pure
memory would still post. AND-ing the triggers would make ``pb`` + ``pm`` mean "a
PB that is also a PM", so picking two would usually produce silence. Keeping
them apart is also what makes the guild floor cheap: a floor is just more gates,
and gates compose by AND with no ambiguity.

Nothing here posts anything. ``poster.py`` calls :func:`evaluate` once per
(play, linked user) pair, sharing one :class:`PlayFacts` across every user
linked to the same account so the account-level queries run once per play.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from coda.db.models import LiveUpdateChannel, LiveUpdatePref, PlayScore, SongDifficulty
from coda.scores.b30 import B30Service
from coda.utils.scoring import PURE_MEMORY, Grade, grade_of


@dataclass(frozen=True)
class Filters:
    """One user's filter set, as stored on ``live_update_prefs``."""

    post_all: bool
    post_pb: bool
    post_pm: bool
    post_fr: bool
    best_of: int | None
    min_grade: Grade | None
    min_level: int | None

    @classmethod
    def of(cls, pref: LiveUpdatePref) -> Filters:
        return cls(
            post_all=pref.post_all,
            post_pb=pref.post_pb,
            post_pm=pref.post_pm,
            post_fr=pref.post_fr,
            best_of=pref.best_of,
            min_grade=None if pref.min_grade is None else Grade(pref.min_grade),
            min_level=pref.min_level,
        )


@dataclass(frozen=True)
class ChannelFloor:
    """A guild's bar for one of its allowlisted channels. Gates only.

    Carries ``guild_id`` because the caller needs it anyway to resolve the
    ``timezone`` setting at guild scope, and the row it comes from already has it.
    """

    guild_id: int
    min_level: int | None
    min_grade: Grade | None

    @classmethod
    def of(cls, row: LiveUpdateChannel) -> ChannelFloor:
        return cls(
            guild_id=row.guild_id,
            min_level=row.min_level,
            min_grade=None if row.min_grade is None else Grade(row.min_grade),
        )


class PlayFacts:
    """Account-level facts about one play, computed at most once each.

    A play can belong to several Discord users (``PlayerLink`` is many-to-one
    onto ``ArcaeaAccount``), and their filters differ, but "is this a PB" and
    "where does it rank" are properties of the *account*. One instance per play,
    reused across every linked user, so two users linking one account never make
    the bot pay twice.
    """

    def __init__(
        self,
        db: AsyncSession,
        b30: B30Service,
        row: PlayScore,
        chart: SongDifficulty | None,
    ) -> None:
        self._db = db
        self._b30 = b30
        self._row = row
        self._chart = chart
        self._previous_best: int | None = None
        self._previous_best_loaded = False
        self._rank: int | None = None
        self._rank_loaded = False

    async def previous_best(self) -> int | None:
        """The account's best score on this chart BEFORE this play, or None.

        Keyed on the resolved chart when there is one and on the wire tuple
        otherwise, so an unresolved play still gets a real PB answer -- wire
        identity is always present, which is why ``pb`` works on charts the
        catalog has never heard of.
        """
        if self._previous_best_loaded:
            return self._previous_best

        query = select(PlayScore.score).where(
            PlayScore.arcaea_account_id == self._row.arcaea_account_id,
            PlayScore.id != self._row.id,
        )
        if self._chart is not None:
            query = query.where(PlayScore.song_difficulty_id == self._chart.id)
        else:
            query = query.where(
                PlayScore.wire_song_id == self._row.wire_song_id,
                PlayScore.wire_difficulty == self._row.wire_difficulty,
            )
        scores = list((await self._db.execute(query)).scalars())

        self._previous_best = max(scores) if scores else None
        self._previous_best_loaded = True
        return self._previous_best

    async def is_pb(self) -> bool:
        """Whether this play STRICTLY beats every earlier one on the chart.

        Strict: an equal score is a distinct row under ``uq_play_identity`` (a
        different ``time_played``) but it is not a new achievement.
        """
        previous = await self.previous_best()
        return previous is None or self._row.score > previous

    async def previous_grade(self) -> Grade | None:
        """The grade of the previous best score, or None if there was none."""
        previous = await self.previous_best()
        return None if previous is None else grade_of(previous)

    async def rank(self) -> int | None:
        """This chart's 1-based place in the account's full ranking.

        None for an unresolved chart: no CC means no play rating, so there is
        nothing to rank. That is arithmetic, not policy.
        """
        if self._rank_loaded:
            return self._rank
        self._rank_loaded = True
        if self._chart is None:
            return None
        result = await self._b30.compute(
            self._db,
            self._row.arcaea_account_id,
            rank_for_difficulty_id=self._chart.id,
        )
        self._rank = result.requested_rank
        return self._rank


async def evaluate(
    row: PlayScore,
    chart: SongDifficulty | None,
    filters: Filters,
    floor: ChannelFloor | None,
    facts: PlayFacts,
) -> bool:
    """Whether this play should be posted for a user with these filters.

    Ordered cheapest-first and short-circuiting: a failed gate ends evaluation
    with zero queries, the score-only triggers are field comparisons, and the
    two that cost a query come last.
    """
    if not _gates_pass(row, chart, filters, floor):
        return False

    if filters.post_all:
        return True
    if filters.post_pm and row.score >= PURE_MEMORY:
        return True
    # Own-path only: the friend payload carries no lost_count, so this is None
    # rather than 0 for a friend-tier sighting and must not be read as a recall.
    if filters.post_fr and row.lost_count == 0:
        return True

    if filters.min_grade is not None and await _grade_up(row, filters.min_grade, facts):
        return True
    # bX implies pb -- a play that does not beat the chart's best cannot move a
    # ranking built from best-per-chart -- so pb settles both, and is asked once.
    if not (filters.post_pb or filters.best_of):
        return False
    if not await facts.is_pb():
        return False
    if filters.post_pb:
        return True

    rank = await facts.rank()
    return rank is not None and filters.best_of is not None and rank <= filters.best_of


def _gates_pass(
    row: PlayScore,
    chart: SongDifficulty | None,
    filters: Filters,
    floor: ChannelFloor | None,
) -> bool:
    """Every set gate must pass, or nothing posts regardless of triggers."""
    grade = grade_of(row.score)
    if floor is not None and floor.min_grade is not None and grade < floor.min_grade:
        return False
    return _level_gate_passes(chart, filters.min_level) and _level_gate_passes(
        chart, None if floor is None else floor.min_level
    )


def _level_gate_passes(chart: SongDifficulty | None, minimum: int | None) -> bool:
    """Fail CLOSED on an unresolved chart: no level known, no post.

    A decision, not a consequence. Failing open would void the gate on exactly
    the charts most likely to be new and high-level, which is the opposite of
    what someone setting "10+ only" asked for. The cost is real -- ``reconcile``
    resolves the chart later, but the post has already been skipped and
    ``ingest`` never re-offers the play.
    """
    if minimum is None:
        return True
    return chart is not None and chart.level >= minimum


async def _grade_up(row: PlayScore, minimum: Grade, facts: PlayFacts) -> bool:
    """First time this account reaches a grade on this chart, at or above ``minimum``.

    Fires on a CROSSING, never on every play at that grade: "any play at >= EX"
    would fire on nearly every play a strong player makes and would swamp ``pb``
    under OR. No previous play means any play clearing the floor is a crossing.
    """
    grade = grade_of(row.score)
    if grade < minimum:
        return False
    previous = await facts.previous_grade()
    return previous is None or grade > previous
