"""What the board draws. Data only: no Discord, no PIL, no I/O.

Everything above this file produces a ``MatchView``; everything below it draws
one. That is what lets the text board be replaced by a composed image without
touching a query, and what lets both exist without a second data path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from coda.catalog.labels import class_short
from coda.db.enums import DifficultyClass, MatchState
from coda.tournaments.levels import LevelRange

EntryState = Literal[
    "available", "banned", "picked", "playing", "played", "unplayed"
]
Action = Literal["ban", "pick"]
# Where a playing match is between rounds. `open` is the validity window,
# `grace` the slack the poller needs to SEE a play that landed inside it, and
# `break` the rest between the result landing and the next chart being named.
Phase = Literal["open", "grace", "break"]


def countdown(deadline_ms: int) -> str:
    """A deadline as Discord's own relative timestamp. It ticks on its own, and
    it is in the reader's timezone rather than the bot's."""
    return f"<t:{deadline_ms // 1000}:R>"


@dataclass(frozen=True)
class ChartRef:
    """One chart as the board names it."""

    title: str
    artist: str
    difficulty_class: DifficultyClass
    # lowiro's alternate Beyond appearance ("Inscribed"). Not a class -- a
    # different name for the same one, so it travels with the class it renames.
    alt: bool
    # Already decoded. A sentinel level or CC renders "?", never a number.
    level_display: str
    cc_display: str
    spoilered: bool

    @property
    def class_label(self) -> str:
        """The short class label this chart is named by."""
        return class_short(self.difficulty_class, self.alt).upper()


@dataclass(frozen=True)
class SideScore:
    """One side's answer to one round."""

    score: int | None
    time_played_ms: int | None
    # WHICH chart they played. In song mode the two sides choose different
    # difficulties, so a result row that does not say this is unreadable.
    chart: ChartRef | None


@dataclass(frozen=True)
class RoundResult:
    ordinal: int
    scores: list[SideScore]
    winner_side: int | None
    tied: bool


@dataclass(frozen=True)
class PoolEntry:
    entry_id: int
    # None in song mode: the entry is a song and the round's set is several of
    # its difficulties.
    chart: ChartRef | None
    song_title: str
    state: EntryState
    acted_by_side: int | None
    auto: bool
    # When it was picked or banned. The pool is ordered for the BOARD, so this
    # is the only thing that says which action was the most recent one -- what
    # a turn prompt has to name before it asks for the next.
    acted_at_ms: int | None
    round_ordinal: int | None
    result: RoundResult | None

    @property
    def display(self) -> str:
        """How the chart is named wherever it is named -- board, beat, prompt.

        One definition, because the three appear in the same thread minutes
        apart and a player matching one against another should not have to
        wonder whether two spellings mean two charts.
        """
        if self.chart is None:
            # Song mode: the entry is a song and the player picks the class.
            return f"**{self.song_title}**, any difficulty"
        chart = self.chart
        return (
            f"**{chart.title}** {chart.class_label} "
            f"{chart.level_display} ({chart.cc_display})"
        )


@dataclass(frozen=True)
class Side:
    # Both names are kept rather than one resolved string: the Arcaea name is
    # whose SCORES these are, and is the only name that exists when a player
    # joined before the Discord one could be captured.
    arcaea_name: str
    discord_name: str | None
    discord_id: int | None
    rounds_won: int
    ready: bool

    @property
    def name(self) -> str:
        """What to call them. Discord first -- a thread is a Discord room, and
        people recognise each other by the name Discord shows."""
        return self.discord_name or self.arcaea_name


@dataclass(frozen=True)
class Turn:
    # Position in the pick/ban sequence. Carried so a prompt can be keyed to
    # THIS turn: "whose turn it is" repeats every other turn, and a key that
    # repeats would let one prompt stand for two different waits.
    index: int
    side_index: int
    action: Action
    deadline_ms: int


@dataclass(frozen=True)
class MatchView:
    """One match, as of ``now_ms``."""

    match_id: int
    kind: Literal["quick", "tournament"]
    stage_label: str | None
    state: MatchState
    best_of: int
    pick_ban: bool
    # Only meaningful while drafting: the roster freezes when the match starts.
    open_join: bool
    levels: LevelRange
    # None = the match is song mode: players choose their own difficulty.
    difficulty_class: DifficultyClass | None
    sides: list[Side]
    pool: list[PoolEntry]
    turn: Turn | None
    winner_side: int | None
    # Which beat a playing match is inside, when it ends, and the round it is
    # about -- for `break`, the round it PRECEDES. All three are None outside
    # `playing`. The three are one field's worth of state, so they move
    # together and the board can never print a countdown to the wrong thing.
    phase: Phase | None
    phase_ends_ms: int | None
    phase_ordinal: int | None
    # Passed in, never read from the clock, so a board is reproducible in a test.
    now_ms: int

    @property
    def song_mode(self) -> bool:
        return self.difficulty_class is None

    @property
    def head_to_head(self) -> bool:
        return len(self.sides) == 2
