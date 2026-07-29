"""The filter grammar's parse step. Pure — no DB.

Value coercion is the part that regresses silently: a level is stored ``×2`` and
a CC ``×10``, so an off-by-one here is a wrong search, not an error.
"""

from __future__ import annotations

import pytest

from coda.catalog.query import Kind, Op, parse


def only(query: str):
    parsed = parse(query)
    assert parsed.error is None, parsed.error
    assert len(parsed.filters) == 1, parsed.filters
    return parsed.filters[0]


class TestNumericCoercion:
    def test_level_is_doubled(self):
        assert only("level>10").value == 20

    def test_plus_level_is_odd(self):
        spec = only("level:10+")
        assert (spec.op, spec.value) == (Op.EQ, 21)

    def test_greater_than_10_admits_10_plus(self):
        """21 (10+) and 22 (11) both exceed 20, so the encoding gives
        strictly-above for free."""
        assert only("level>10").value < 21

    def test_cc_is_decimal_shifted(self):
        spec = only("cc>=9.7")
        assert (spec.op, spec.value) == (Op.GTE, 97)

    def test_whole_cc(self):
        assert only("cc:10").value == 100

    def test_bpm_is_float(self):
        assert only("bpm>180").value == 180.0

    def test_note_is_int(self):
        assert only("note<1200").value == 1200

    def test_date_iso_to_epoch(self):
        assert only("date>2023-06-01").value == 1685577600


class TestNonNumericFields:
    def test_side_name_to_stored_id(self):
        spec = only("side:conflict")
        assert (spec.kind, spec.value) == (Kind.ENUM, 1)

    def test_entity_value_kept_as_text(self):
        spec = only("artist:sakuzyo")
        assert (spec.kind, spec.value) == (Kind.ENTITY, "sakuzyo")

    def test_quoted_value_keeps_its_space(self):
        assert only('pack:"eternal core"').value == "eternal core"

    def test_aliases_resolve_to_canonical_names(self):
        assert only("rating>=9.7").field == "cc"
        assert only("notes<1200").field == "note"
        assert only("lv>10").field == "level"


class TestComposition:
    def test_repeated_key_ands_rather_than_overwriting(self):
        parsed = parse("bpm>180 bpm<220")
        assert [(f.op, f.value) for f in parsed.filters] == [
            (Op.GT, 180.0),
            (Op.LT, 220.0),
        ]

    def test_bare_words_survive_alongside_filters(self):
        parsed = parse("sakuzyo level>10")
        assert parsed.text == "sakuzyo"
        assert len(parsed.filters) == 1

    def test_bare_query_is_normalized_not_filtered(self):
        parsed = parse("  Tempestissimo   BYD ")
        assert (parsed.text, parsed.filters) == ("tempestissimo byd", ())


class TestExistingSyntaxStillOwnsItsTokens:
    """The bare level/CC and ``<song> <class>`` paths in ``search.py`` must keep
    receiving these untouched."""

    @pytest.mark.parametrize("query", ["10+", "9.3", "11", "quon ftr"])
    def test_passes_through_as_text(self, query):
        parsed = parse(query)
        assert (parsed.text, parsed.filters, parsed.error) == (query, (), None)


class TestColonsInSongTitles:
    """Real aliases contain colons, so an unknown key before ``:`` is text."""

    @pytest.mark.parametrize(
        "query", ["carmine:scythe", "valhalla:0", "glory : road", "code: oblivion"]
    )
    def test_unknown_key_degrades_to_text(self, query):
        parsed = parse(query)
        assert parsed.filters == ()
        assert parsed.error is None


class TestEqualsSpelling:
    """``=`` is the other way to write ``:`` -- but only for a KNOWN key: no song
    title contains one, so an unknown key there is a typo, not text."""

    @pytest.mark.parametrize(
        ("colon", "equals"),
        [
            ("level:10", "level=10"),
            ("side:conflict", "side=conflict"),
            ('pack:"eternal core"', 'pack="eternal core"'),
            ("artist:sakuzyo", "artist=sakuzyo"),
        ],
    )
    def test_same_filter_either_way(self, colon, equals):
        assert parse(colon).filters == parse(equals).filters

    def test_unknown_key_with_equals_is_a_typo(self):
        assert parse("lvel=10").error is not None


class TestErrors:
    def test_unknown_key_with_comparison_is_a_typo(self):
        assert parse("foo>1").error is not None

    def test_bad_numeric_value(self):
        assert parse("level:abc").error is not None

    def test_bad_side_name(self):
        assert parse("side:purple").error is not None

    def test_comparison_on_an_equality_only_field(self):
        assert parse("artist>sakuzyo").error is not None

    def test_error_names_the_offender(self):
        assert "level" in parse("level:abc").error
