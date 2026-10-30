# -*- coding: utf-8 -*-
"""W dzień wolny strona główna pokazuje najbliższy trening z planu."""
from datetime import datetime

from api.views.today import _next_workout_view
from services import today as today_service


def _plans(by_monday):
    return lambda day: by_monday.get(day.strftime("%Y-%m-%d"))


def test_next_workout_skips_rest_and_past_and_falls_back_to_next_week(monkeypatch):
    this_week = {"workouts": [
        {"date": "2026-10-26", "type": "easy", "name": "Miniony"},
        {"date": "2026-10-29", "type": "rest", "name": "Odpoczynek"},
    ]}
    next_week = {"workouts": [{"date": "2026-11-03", "type": "long", "name": "Długi bieg"}]}
    plans = {"2026-10-28": this_week, "2026-11-04": next_week}
    monkeypatch.setattr(today_service, "find_current_plan", _plans(plans))
    found = today_service._next_plan_workout(datetime(2026, 10, 28, 9))
    assert found["name"] == "Długi bieg"


def test_next_workout_view_says_tomorrow_or_the_day_and_watch_state():
    tomorrow = _next_workout_view({"date": "2026-10-29", "name": "Interwały", "duration_min": 50,
                                   "hr_zone": "Z4", "garmin_upload": True}, "2026-10-28")
    later = _next_workout_view({"date": "2026-11-01", "name": "Długi bieg"}, "2026-10-28")
    assert (tomorrow["when"], tomorrow["garmin_upload"]) == ("Jutro", True)
    assert later["when"] == "Niedziela, 1 listopada" and later["garmin_upload"] is False
    assert _next_workout_view(None, "2026-10-28") is None
