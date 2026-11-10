# -*- coding: utf-8 -*-
"""Zmiana jednego treningu w planie: przeniesienie, skrócenie, zamiana na spokojny bieg."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from services import plan as plan_service
from services.actions import edit_plan_workout
from tests.test_api_plan import _app, _csrf
from tests.test_plan_remove import ORIGIN, TODAY, _future_plan

pytestmark = pytest.mark.usefixtures("testclient_sockets")
WEEK = "2026-09-28"


@pytest.fixture
def plans_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("services.plan_files.TRAINING_PLANS_DIR", tmp_path / "plans")
    plan_service.save_plan(_future_plan())


def _day(date):
    plan = plan_service.load_week_plan(datetime(2026, 9, 28))
    return next(w for w in plan["workouts"] if w["date"] == date)


def test_shorten_cuts_a_quarter_and_keeps_the_name_in_step(plans_dir):
    edit_plan_workout(week_start=WEEK, day="2026-10-03", action="shorten", today=TODAY)
    day = _day("2026-10-03")
    assert (day["duration_min"], day["name"], day["type"]) == (70, "Długi bieg 70 min", "long")
    assert "Skrócono z 90 do 70 min" in day["notes"]


def test_easier_turns_a_long_run_into_an_easy_one(plans_dir):
    edit_plan_workout(week_start=WEEK, day="2026-10-03", action="easier", today=TODAY, profile_loader=dict)
    day = _day("2026-10-03")
    assert (day["type"], day["hr_zone"], day["pace_target"], day["duration_min"]) == ("easy", "Z2", None, 90)
    assert "Długi bieg 90 min" in day["notes"]


def test_move_swaps_days_and_takes_the_workout_off_the_watch_first(plans_dir):
    deleted = []

    def deleter(workout_id, **kwargs):
        assert _day("2026-10-02")["garmin_workout_id"] == 77  # plan jeszcze niezmieniony
        deleted.append(workout_id)

    edit_plan_workout(week_start=WEEK, day="2026-10-02", action="move", target="2026-10-03", today=TODAY,
                      workout_deleter=deleter)
    friday, saturday = _day("2026-10-02"), _day("2026-10-03")
    assert deleted == [77]
    assert (friday["name"], friday["day"]) == ("Długi bieg 90 min", "fri")
    assert (saturday["name"], saturday["day"]) == ("Bieg łatwy 40 min", "sat")
    assert saturday["garmin_upload"] is False and saturday["garmin_workout_id"] is None


def test_move_clips_to_the_new_days_window(plans_dir):
    from trainer.preferences import set_weekly_availability

    set_weekly_availability("sun", True, 30, 60)
    edit_plan_workout(week_start=WEEK, day="2026-10-03", action="move", target="2026-10-04", today=TODAY)
    sunday = _day("2026-10-04")
    assert sunday["duration_min"] == 60 and "limit dostępności" in sunday["notes"]


def test_move_refuses_a_pause_day_and_the_past(plans_dir):
    from trainer.preferences import add_planned_pause

    add_planned_pause("2026-10-04", "2026-10-04", "zabieg")
    with pytest.raises(ValueError, match="przerwa"):
        edit_plan_workout(week_start=WEEK, day="2026-10-03", action="move", target="2026-10-04", today=TODAY)
    with pytest.raises(ValueError, match="minął"):
        edit_plan_workout(week_start=WEEK, day="2026-10-03", action="move", target="2026-09-29", today=TODAY)
    assert _day("2026-10-03")["name"] == "Długi bieg 90 min"


@pytest.mark.parametrize(("date", "action"), [("2026-09-28", "shorten"), ("2026-10-02", "easier"),
                                              ("2026-10-03", "explode")])
def test_past_days_easy_runs_and_unknown_actions_are_refused(plans_dir, date, action):
    with pytest.raises(ValueError):
        edit_plan_workout(week_start=WEEK, day=date, action=action, today=TODAY)


def test_garmin_error_leaves_the_plan_unchanged(plans_dir):
    def deleter(*args, **kwargs):
        raise RuntimeError("Garmin nie odpowiada")

    with pytest.raises(RuntimeError):
        edit_plan_workout(week_start=WEEK, day="2026-10-02", action="shorten", today=TODAY, workout_deleter=deleter)
    assert (_day("2026-10-02")["duration_min"], _day("2026-10-02")["garmin_workout_id"]) == (40, 77)


def test_page_offers_the_changes_and_the_form_applies_them(tmp_path, plans_dir):
    with TestClient(_app(tmp_path, plan=_future_plan())) as client:
        page = client.get(f"/plan?week={WEEK}").text
        assert "Zmień ten trening" in page and "Skróć o ćwierć" in page and "Zamień na spokojny bieg" in page
        assert client.post("/actions/plan/edit", data={"week_start": WEEK, "date": "2026-10-03",
                                                       "action": "shorten"}).status_code == 403
        response = client.post("/actions/plan/edit", follow_redirects=False, headers=ORIGIN, data={
            "csrf_token": _csrf(client, f"/plan?week={WEEK}"), "week_start": WEEK, "date": "2026-10-03",
            "action": "shorten"})
    assert response.status_code == 303 and response.headers["location"] == f"/plan?week={WEEK}"
    assert _day("2026-10-03")["duration_min"] == 70
