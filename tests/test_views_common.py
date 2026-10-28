# -*- coding: utf-8 -*-
"""Testy polskiego formatowania liczb i odmiany w widokach."""
import math

import pytest

from api.views.common import _format_number, _format_score, _plural


@pytest.mark.parametrize("value, expected", [
    (15.0, "15"),
    (6.1, "6,1"),
    (5.26, "5,3"),
    (8, "8"),
    ("65–79", "65–79"),
    (None, None),
    (True, True),
])
def test_format_number_uses_polish_decimal_comma(value, expected):
    assert _format_number(value) == expected


def test_format_number_leaves_non_finite_values_untouched():
    assert math.isnan(_format_number(float("nan")))


def test_format_score_matches_number_format():
    assert _format_score(5.0) == "5"
    assert _format_score(3.5) == "3,5"


@pytest.mark.parametrize("count, expected", [
    (1, "trening"), (2, "treningi"), (4, "treningi"), (5, "treningów"),
    (12, "treningów"), (22, "treningi"), (0, "treningów"), (None, "treningów"),
])
def test_plural_follows_polish_rules(count, expected):
    assert _plural(count, "trening", "treningi", "treningów") == expected
