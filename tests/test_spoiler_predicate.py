"""Which charts a flagged version covers.

The rule that regresses silently is inheritance: a chart leaves ``version``
NULL to mean "the song's", so a song flagged as a spoiler must cover its charts
without any of them naming the version, while a chart that *does* override wins
over its song in both directions.
"""

from __future__ import annotations

import pytest

from coda.catalog import spoilers
from coda.db.models import Song, SongDifficulty


@pytest.fixture(autouse=True)
def _no_flags(monkeypatch):
    """Every test states its own flagged set; none leaks into the next."""
    monkeypatch.setattr(spoilers, "_flagged", frozenset())


def _flag(monkeypatch, *versions: str) -> None:
    monkeypatch.setattr(spoilers, "_flagged", frozenset(versions))


def _song(version: str) -> Song:
    return Song(song_id="s", version=version)


def _chart(version: str | None = None) -> SongDifficulty:
    return SongDifficulty(song_id="s", version=version)


def test_nothing_is_spoilered_by_default():
    assert spoilers.is_spoilered("7.0") is False
    assert spoilers.chart_spoilered(_song("7.0"), _chart()) is False


def test_chart_inherits_its_song_version(monkeypatch):
    _flag(monkeypatch, "7.0")
    assert spoilers.chart_spoilered(_song("7.0"), _chart(None)) is True


def test_chart_override_wins_over_an_unflagged_song(monkeypatch):
    """The case the whole per-chart decision exists for: an old song that got a
    new Beyond in the flagged version."""
    _flag(monkeypatch, "7.0")
    song = _song("4.0")
    assert spoilers.chart_spoilered(song, _chart("7.0")) is True
    assert spoilers.chart_spoilered(song, _chart(None)) is False


def test_chart_override_also_wins_the_other_way(monkeypatch):
    """A chart that names an *older* version is not spoilered by its song."""
    _flag(monkeypatch, "7.0")
    assert spoilers.chart_spoilered(_song("7.0"), _chart("4.0")) is False


def test_song_is_spoilered_when_any_chart_is(monkeypatch):
    _flag(monkeypatch, "7.0")
    song = _song("4.0")
    charts = [_chart(None), _chart(None), _chart("7.0")]
    assert spoilers.song_spoilered(song, charts) is True


def test_song_is_not_spoilered_when_no_chart_is(monkeypatch):
    _flag(monkeypatch, "7.0")
    song = _song("4.0")
    assert spoilers.song_spoilered(song, [_chart(None), _chart("5.0")]) is False


def test_song_with_no_charts_falls_back_to_its_own_version(monkeypatch):
    """A song seeded before its charts must not render in the clear."""
    _flag(monkeypatch, "7.0")
    assert spoilers.song_spoilered(_song("7.0"), []) is True


def test_a_missing_version_is_never_spoilered(monkeypatch):
    """Some catalog rows carry an empty version; flagging must not catch them
    by accident."""
    _flag(monkeypatch, "7.0")
    assert spoilers.is_spoilered(None) is False
    assert spoilers.is_spoilered("") is False


def test_versions_match_exactly_not_by_prefix(monkeypatch):
    """`7.0` must not drag in `7.0.1` or `17.0`."""
    _flag(monkeypatch, "7.0")
    assert spoilers.is_spoilered("7.0") is True
    assert spoilers.is_spoilered("7.01") is False
    assert spoilers.is_spoilered("17.0") is False


def test_several_versions_can_be_flagged_at_once(monkeypatch):
    _flag(monkeypatch, "7.0", "6.9")
    assert spoilers.chart_spoilered(_song("6.9"), _chart()) is True
    assert spoilers.chart_spoilered(_song("7.0"), _chart()) is True
    assert spoilers.chart_spoilered(_song("6.8"), _chart()) is False


class TestNewestSongsAutocomplete:
    """The empty-query ``/song`` suggestion is ordered by ``idx`` descending, so
    it is the newest content by construction -- the one autocomplete path that
    hands spoilered names to someone who typed nothing."""

    @pytest.mark.asyncio
    async def test_flagged_versions_drop_out_of_the_newest_suggestion(
        self, db, monkeypatch
    ):
        from sqlalchemy import select

        from coda.catalog.autocomplete import song_choices
        from coda.db.models import Song

        newest_version = await db.scalar(
            select(Song.version).order_by(Song.idx.desc()).limit(1)
        )
        monkeypatch.setattr(spoilers, "_flagged", frozenset())
        before = {song_id for _label, song_id in await song_choices(db, "")}

        _flag(monkeypatch, newest_version)
        after = {song_id for _label, song_id in await song_choices(db, "")}

        suppressed = before - after
        assert suppressed, "flagging the newest version suppressed nothing"
        # Everything dropped must actually be on the flagged version, and
        # nothing on it may survive.
        for song_id in suppressed:
            assert await db.scalar(
                select(Song.version).where(Song.song_id == song_id)
            ) == newest_version
        for song_id in after:
            assert await db.scalar(
                select(Song.version).where(Song.song_id == song_id)
            ) != newest_version
        # The filter runs in SQL, before the limit, so the row count survives.
        assert len(after) == len(before)

    @pytest.mark.asyncio
    async def test_an_unflagged_catalog_is_untouched(self, db, monkeypatch):
        from coda.catalog.autocomplete import song_choices

        monkeypatch.setattr(spoilers, "_flagged", frozenset())
        rows = await song_choices(db, "")
        assert rows
        assert len(rows) == 25
