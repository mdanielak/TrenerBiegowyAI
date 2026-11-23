# -*- coding: utf-8 -*-
"""Decyzja tygodnia jako czysta funkcja: kolejność warunków to hierarchia zdrowie > start > rytm > wykonanie."""
import pytest

from services.week_decision import decide_week

BASE = dict(pain=False, rhr_up=0, struggling=False, hrv_low=False, adherence=1.0, returning=False,
            hr_too_high=False, short_history=False, week_minutes=[100, 100, 100, 100], race_days=None, goal="hm")


@pytest.mark.parametrize(("change", "expected"), [
    ({}, ("doloz", "ready")),
    ({"pain": True, "race_days": 3}, ("regeneracja", "pain")),            # ból ważniejszy niż start
    ({"rhr_up": 6, "race_days": 3}, ("odpusc", "rhr_up")),
    ({"race_days": 3, "week_minutes": [90, 100, 110, 120]}, ("odpusc", "race_week")),  # start przed cofnięciem
    ({"week_minutes": [90, 100, 110, 120]}, ("odpusc", "step_back")),
    ({"week_minutes": [90, 100, 110, 120], "short_history": True}, ("doloz", "ready")),  # za mało danych na rytm
    ({"adherence": 0.5}, ("utrzymaj", "low_adherence")),
    ({"hrv_low": True}, ("utrzymaj", "hrv_low")),
    ({"hrv_low": True, "rhr_up": 3}, ("odpusc", "hrv_rhr")),
    ({"week_minutes": [100, 100, 120, 90]}, ("utrzymaj", "stabilise")),
])
def test_the_order_of_signals(change, expected):
    week = decide_week(**{**BASE, **change})
    assert (week.decision, week.cause) == expected


def test_taper_weeks_follow_the_distance():
    marathon = [decide_week(**{**BASE, "goal": "marathon", "race_days": days}) for days in (3, 10, 17, 24)]
    assert [w.taper_factor for w in marathon] == [0.5, 0.7, 0.85, None]
    assert marathon[3].taper and marathon[3].decision == "utrzymaj"
