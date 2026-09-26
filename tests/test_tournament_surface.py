"""The Discord-facing seams: the crew key, the custom-id contract, and how an
omitted option resolves.

The custom-id parser is the one with teeth. Lightbulb's own Menu and Modal
components ride the same InteractionCreateEvent stream, so a parser that is
loose about what it claims silently eats other features' clicks.
"""

from __future__ import annotations

import pytest

from coda.db.enums import DifficultyClass, ThreadVisibility
from coda.extensions.tournament import (
    HOME_TYPES,
    home_row,
    parse_custom_id,
    reads_as_ready,
)
from coda.settings import ConfigService, Scope
from coda.tournaments import defaults, transport
from coda.tournaments.threads import roster_key


class TestCustomIds:
    def test_reads_our_own(self):
        assert parse_custom_id("tourney:act:12") == ("act", 12)
        assert parse_custom_id("tourney:ready:3") == ("ready", 3)
        assert parse_custom_id("tourney:home:456") == ("home", 456)

    @pytest.mark.parametrize(
        "custom_id",
        [
            "chardle:daily",        # another feature's persistent button
            "req:5:yes",            # approvals
            "song:c:41",            # song browser
            "tourney:act",          # truncated
            "tourney:act:abc",      # unparseable id
            "tourney:explode:1",    # unknown action
            "tourney:act:1:extra",  # over-long
            "",
        ],
    )
    def test_disclaims_everything_else(self, custom_id):
        assert parse_custom_id(custom_id) is None

    def test_carries_no_turn_number(self):
        """A match outlives restarts, so the turn is read from the DB on every
        click and never encoded in the id."""
        assert parse_custom_id("tourney:act:12") == ("act", 12)

    def test_the_home_button_round_trips_its_channel(self):
        row = home_row(1234567890123)
        custom_id = row.components[0].custom_id
        assert parse_custom_id(custom_id) == ("home", 1234567890123)


class TestHomeOffer:
    def test_a_thread_is_not_a_candidate_home(self):
        """Threads are what hangs OFF the home channel, so one cannot be it."""
        import hikari

        assert hikari.ChannelType.GUILD_PUBLIC_THREAD not in HOME_TYPES
        assert hikari.ChannelType.GUILD_PRIVATE_THREAD not in HOME_TYPES
        assert hikari.ChannelType.GUILD_TEXT in HOME_TYPES


class TestCrewKey:
    def test_order_does_not_matter(self):
        assert roster_key([7, 2, 5]) == roster_key([5, 7, 2])

    def test_duplicates_collapse(self):
        assert roster_key([3, 3, 1]) == [1, 3]

    def test_a_different_crew_is_a_different_key(self):
        assert roster_key([1, 2]) != roster_key([1, 2, 3])


class TestThreadName:
    def test_head_to_head(self):
        assert transport.thread_name(["alice", "bob"]) == "alice vs bob"

    def test_a_crew_is_summarised(self):
        assert transport.thread_name(["alice", "b", "c", "d"]) == "alice +3"

    def test_stage_label_leads(self):
        assert transport.thread_name(
            ["alice", "bob"], "QF1") == "QF1 - alice vs bob"

    def test_truncated_to_discords_limit(self):
        assert len(transport.thread_name(["x" * 80, "y" * 80])) == 100


class TestDefaults:
    async def chosen(self, db, **kw):
        base = dict(difficulty_class=DifficultyClass.FTR, song_mode=False)
        return await defaults.resolve(
            db, ConfigService(), defaults.Chosen(**{**base, **kw}),
            guild_id=1, channel_id=2, user_id=3,
        )

    async def test_unset_options_fall_back_to_the_registry(self, db):
        options = await self.chosen(db)
        assert options.best_of == 3
        assert options.pick_ban is True
        assert options.open_join is False
        assert options.visibility is ThreadVisibility.PUBLIC
        assert options.levels.unbounded

    async def test_typed_options_win(self, db):
        options = await self.chosen(
            db, best_of="7", bans=False, visibility="public", level="9-10+")
        assert options.best_of == 7
        assert options.pick_ban is False
        assert options.visibility is ThreadVisibility.PUBLIC
        assert options.levels == (await self.chosen(db, level="9-10+")).levels

    async def test_a_guild_default_fills_the_gap(self, db):
        settings = ConfigService()
        await settings.set_value(
            db, "tournament_default_level", Scope.GUILD, 1, "10-11", 3)
        options = await self.chosen(db)
        assert not options.levels.unbounded

    async def test_typed_any_overrides_a_guild_band(self, db):
        settings = ConfigService()
        await settings.set_value(
            db, "tournament_default_level", Scope.GUILD, 1, "10-11", 3)
        assert (await self.chosen(db, level="any")).levels.unbounded

    async def test_a_typed_bad_band_is_refused(self, db):
        with pytest.raises(ValueError):
            await self.chosen(db, level="nonsense")

    async def test_a_stored_bad_band_falls_back_to_any(self, db):
        """resolve() hands back whatever is stored without re-checking it, so a
        band written before a validation change must not brick every match."""
        settings = ConfigService()
        await settings.set_value(
            db, "tournament_default_level", Scope.GUILD, 1, "9-10+", 3)
        await settings.set_value(
            db, "tournament_default_level", Scope.GUILD, 1, "?", 3)
        assert (await self.chosen(db)).levels.unbounded

    async def test_any_class_is_song_mode(self, db):
        options = await self.chosen(db, song_mode=True)
        assert options.difficulty_class is None


class TestChatReady:
    """A word in the thread standing in for the Ready button.

    The listener sees every message in every guild, so this test is really
    about what it must NOT claim: a loose match here would mark someone ready
    for saying the opposite, and would do it from ordinary conversation.
    """

    @pytest.mark.parametrize(
        "content",
        ["ready", "Ready", "  ready  ", "ready!", "r", "go",
         "yep", "next", "done", "let's go", "OK."],
    )
    def test_reads_as_ready(self, content):
        assert reads_as_ready(content)

    @pytest.mark.parametrize(
        "content",
        [
            "ready in a sec",   # the opposite of ready
            "not ready",
            "gg",               # said AFTER a round, never before one
            "gg wp",
            "gg ez",            # conversation, not a signal
            "almost done",
            "go on then",
            "",
            "   ",
            "readying up",
            "?",
            "+",                # bare punctuation guesses at intent
        ],
    )
    def test_does_not_read_as_ready(self, content):
        assert not reads_as_ready(content)
