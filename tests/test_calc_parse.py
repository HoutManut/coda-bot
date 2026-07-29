"""/calc input parsing -- the silent-regression half of the command."""

from __future__ import annotations

import pytest

from coda.extensions.calc import _parse_cc, _parse_score
from coda.utils.scoring import MAX_SCORE, PURE_MEMORY


@pytest.mark.parametrize(
    "text",
    ["9123456", "9'123'456", "9,123,456", "9 123 456", " 9_123_456 "],
)
def test_dividers_are_stripped(text: str) -> None:
    assert _parse_score(text) == 9123456


def test_zero_is_a_real_score() -> None:
    assert _parse_score("0") == 0


@pytest.mark.parametrize(
    "text", ["", "abc", "912345678", "9.123.456", "9123456!", "-9123456"]
)
def test_non_scores_are_rejected(text: str) -> None:
    assert _parse_score(text) is None


def test_max_score_clears_the_densest_chart() -> None:
    """2221 notes is the catalog's densest chart today; the cap keeps headroom."""
    assert MAX_SCORE >= PURE_MEMORY + 2221


@pytest.mark.parametrize("score", [MAX_SCORE, PURE_MEMORY, PURE_MEMORY + 2221])
def test_reachable_scores_are_accepted(score: int) -> None:
    assert _parse_score(str(score)) == score


@pytest.mark.parametrize("score", [MAX_SCORE + 1, 11_000_000, 99_999_999])
def test_unreachable_scores_are_rejected(score: int) -> None:
    assert _parse_score(str(score)) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [("11", 11.0), ("11.0", 11.0), ("11.9", 11.9), ("11.37", 11.3), ("0.1", 0.1)],
)
def test_cc_truncates_to_one_decimal(text: str, expected: float) -> None:
    assert _parse_cc(text) == pytest.approx(expected)


@pytest.mark.parametrize("text", ["0", "0.0", "99", "abc", "10+", "11.", ""])
def test_out_of_range_or_non_numeric_cc_is_rejected(text: str) -> None:
    assert _parse_cc(text) is None
