# -*- coding: utf-8 -*-
"""Oś wykresu sygnału nie może robić z wahania o 1 bpm dramatycznego skoku."""
from api.views.stats import _axis_bounds


def test_small_swings_get_a_minimum_axis_span():
    low, high = _axis_bounds([48, 49, 50, 51], min_span=10)
    assert high - low >= 10 and low <= 48 and high >= 51


def test_minimum_span_respects_the_scale_of_the_metric():
    low, high = _axis_bounds([1, 2, 2], domain=(0, 10), min_span=4)
    assert low == 0 and high - low >= 4


def test_wide_data_is_not_squeezed():
    assert _axis_bounds([40, 80], min_span=10) == _axis_bounds([40, 80])
