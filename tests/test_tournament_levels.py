"""The pool's level band. Pure — no DB.

Levels are stored ``×2`` (``+1`` for "+"), so a bound that decodes wrong is a
wrong pool rather than an error. The sentinel is the other trap: ``encode_level``
happily accepts "?" and answers ``-1``, which as a band bound would admit every
N/A chart in the catalog.
"""

from __future__ import annotations

import pytest

from coda.tournaments.levels import LevelRange, display, parse_level_range


class TestAny:
    def test_empty_is_any(self):
        assert parse_level_range("").unbounded

    def test_the_word_any_is_any(self):
        assert parse_level_range("any").unbounded

    def test_whitespace_and_case(self):
        assert parse_level_range("  ANY ").unbounded


class TestBounds:
    def test_single_level_is_a_closed_band(self):
        assert parse_level_range("9") == LevelRange(18, 18)

    def test_plus_level_is_odd(self):
        assert parse_level_range("10+") == LevelRange(21, 21)

    def test_range(self):
        assert parse_level_range("9-10+") == LevelRange(18, 21)

    def test_open_top(self):
        assert parse_level_range("9-") == LevelRange(18, None)

    def test_open_bottom(self):
        assert parse_level_range("-10") == LevelRange(None, 20)


class TestRejections:
    @pytest.mark.parametrize("raw", ["?", "-", "9-?", "abc", "9-10-11", "100", "9++"])
    def test_rejected(self, raw):
        with pytest.raises(ValueError):
            parse_level_range(raw)

    def test_sentinel_never_becomes_a_bound(self):
        """encode_level('?') is -1; a band built from it would admit every N/A."""
        with pytest.raises(ValueError):
            parse_level_range("?")

    def test_backwards_range_is_refused(self):
        with pytest.raises(ValueError):
            parse_level_range("11-9")


class TestDisplay:
    def test_any(self):
        assert display(LevelRange()) == "any level"

    def test_single(self):
        assert display(LevelRange(21, 21)) == "level 10+"

    def test_band(self):
        assert display(LevelRange(18, 21)) == "level 9-10+"

    def test_open_ends(self):
        assert display(LevelRange(18, None)) == "level 9 and above"
        assert display(LevelRange(None, 20)) == "level 10 and below"
