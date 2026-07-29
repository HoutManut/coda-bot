"""Per-column feedback rules.

`_rating` mirrors `_version` rather than the distance-window `_ordered` every
other ordered column uses: same whole CC number is yellow regardless of raw
distance, so a guess can be numerically closer and still read red.
"""

from __future__ import annotations

from coda.chardle.feedback import Arrow, Cell, Color, UNKNOWN_CELL, _rating


def test_exact_rating_match_is_green() -> None:
    assert _rating(101, 101) == Cell(Color.GREEN)


def test_same_whole_cc_is_yellow_even_when_further_away() -> None:
    # 10.9 vs 10.1: same whole CC (10), further apart than the red case below.
    assert _rating(109, 101) == Cell(Color.YELLOW, Arrow.DOWN)


def test_different_whole_cc_is_red_even_when_closer() -> None:
    # 9.9 vs 10.1: different whole CC (9 vs 10), closer than the yellow case above.
    assert _rating(99, 101) == Cell(Color.RED, Arrow.UP)


def test_arrow_points_from_guess_to_answer() -> None:
    assert _rating(101, 109).arrow is Arrow.UP
    assert _rating(109, 101).arrow is Arrow.DOWN


def test_non_positive_guess_is_unknown() -> None:
    assert _rating(0, 101) is UNKNOWN_CELL


def test_delisted_negated_rating_is_unknown() -> None:
    # Delisted charts store a negated historical CC (catalog/labels.py), never a
    # value the arrow/major math should run on.
    assert _rating(-101, 101) is UNKNOWN_CELL
    assert _rating(101, -101) is UNKNOWN_CELL
