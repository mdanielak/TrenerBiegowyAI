# -*- coding: utf-8 -*-
"""Usuwanie zaplanowanego treningu: z planu, a gdy był wysłany, także z zegarka."""
import copy
import time
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from services import plan as plan_service
from services.actions import remove_plan_workout
from services.jobs import JobStore
from tests.test_api_plan import _app, _csrf, _plan

pytestmark = pytest.mark.usefixtures("testclient_sockets")
ORIGIN = {"Origin": "http://testserver"}
TODAY = datetime(2026, 10, 2, 12, 0)  # piątek, jak w _app


def _future_plan():
    """Pn i wt miniony, pt dziś na zegarku (id 77), sob przyszły bez wysyłki."""
    plan = copy.deepcopy(_plan())
    days = {w["day"]: w for w in plan["workouts"]}
    days["fri"].update(type="easy", name="Bieg łatwy 40 min", duration_min=40, hr_zone="Z2",
                       garmin_upload=True, garmin_workout_id=77)
    days["sat"].update(type="long", name="Długi bieg 90 min", duration_min=90, hr_zone="Z2")
    return plan


@pytest.fixture
def plans_dir(tmp_path, monkeypatch):
    directory = tmp_path / "plans"
    monkeypatch.setattr("services.plan_files.TRAINING_PLANS_DIR", directory)
    plan_service.save_plan(_future_plan())
    return directory


def _day(date):
    plan = plan_service.load_week_plan(datetime(2026, 9, 28))
    return next(w for w in plan["workouts"] if w["date"] == date)


def test_plan_only_turns_the_day_into_rest_without_touching_garmin(plans_dir):
    calls = []
    remove_plan_workout(week_start="2026-09-28", day="2026-10-03", today=TODAY,
                        workout_deleter=lambda *a, **k: calls.append(a))
    day = _day("2026-10-03")
    assert (day["type"], day["name"], day["day"]) == ("rest", "Odpoczynek", "sat")
    assert calls == []


def test_from_garmin_deletes_the_watch_workout_then_saves(plans_dir):
    calls = []

    def deleter(workout_id, **kwargs):
        assert _day("2026-10-02")["type"] == "easy"  # plan jeszcze niezmieniony
        calls.append((workout_id, kwargs))

    remove_plan_workout(week_start="2026-09-28", day="2026-10-02", from_garmin=True,
                        today=TODAY, workout_deleter=deleter)
    assert calls == [(77, {"reason": "usunięty z planu"})]
    day = _day("2026-10-02")
    assert day["type"] == "rest" and day["garmin_upload"] is False and day["garmin_workout_id"] is None


def test_garmin_error_leaves_the_plan_unchanged(plans_dir):
    def deleter(*args, **kwargs):
        raise RuntimeError("Garmin nie odpowiada")

    with pytest.raises(RuntimeError):
        remove_plan_workout(week_start="2026-09-28", day="2026-10-02", from_garmin=True,
                            today=TODAY, workout_deleter=deleter)
    assert _day("2026-10-02")["garmin_workout_id"] == 77


@pytest.mark.parametrize("date", ["2026-09-28", "2026-09-30", "2026-10-09"])
def test_past_rest_and_unknown_days_are_refused(plans_dir, date):
    with pytest.raises(ValueError):
        remove_plan_workout(week_start="2026-09-28", day=date, today=TODAY)


def test_the_x_is_only_on_today_and_future_workouts(tmp_path):
    with TestClient(_app(tmp_path, plan=_future_plan())) as client:
        page = client.get("/plan?week=2026-09-28").text
    assert 'aria-label="Usuń trening Bieg łatwy 40 min"' in page
    assert 'aria-label="Usuń trening Długi bieg 90 min"' in page
    assert 'aria-label="Usuń trening Tempo 3×8 min"' not in page  # wtorek już minął
    assert 'id="usun"' not in page
    # Przyszły trening jeszcze nie wysłany ma szary zegarek; wysłany zielony; minione dni żadnego szarego.
    assert page.count('aria-label="Trening nie jest jeszcze na zegarku Garmin"') == 1


def test_confirmation_offers_the_watch_only_when_the_workout_is_there(tmp_path):
    with TestClient(_app(tmp_path, plan=_future_plan())) as client:
        on_watch = client.get("/plan?week=2026-09-28&remove=2026-10-02").text
        plan_only = client.get("/plan?week=2026-09-28&remove=2026-10-03").text
        past = client.get("/plan?week=2026-09-28&remove=2026-09-29").text
    assert "Usuń z planu i z zegarka" in on_watch and "Usuń tylko z planu" in on_watch
    assert "Ten trening jest też na zegarku." in on_watch
    assert 'id="usun" role="alertdialog"' in on_watch and 'tabindex="-1" autofocus' in on_watch  # fokus na oknie
    assert "Usuń z planu i z zegarka" not in plan_only and ">Usuń z planu</button>" in plan_only
    assert 'id="usun"' not in past


def test_remove_requires_csrf(tmp_path):
    with TestClient(_app(tmp_path, plan=_future_plan())) as client:
        response = client.post("/actions/plan/remove",
                               data={"week_start": "2026-09-28", "date": "2026-10-03", "scope": "plan"})
    assert response.status_code == 403


def test_plan_scope_removes_at_once_and_returns_to_the_week(tmp_path, plans_dir):
    with TestClient(_app(tmp_path, plan=_future_plan())) as client:
        token = _csrf(client, "/plan?week=2026-09-28")
        response = client.post("/actions/plan/remove", follow_redirects=False, headers=ORIGIN, data={
            "csrf_token": token, "week_start": "2026-09-28", "date": "2026-10-03", "scope": "plan"})
    assert response.status_code == 303 and response.headers["location"] == "/plan?week=2026-09-28"
    assert _day("2026-10-03")["type"] == "rest"


def test_garmin_scope_runs_as_a_job(tmp_path, plans_dir, monkeypatch):
    deleted = []
    monkeypatch.setattr("services.actions._garmin_session",
                        lambda: (None, lambda workout_id, **kwargs: deleted.append(workout_id)))
    with TestClient(_app(tmp_path, plan=_future_plan())) as client:
        token = _csrf(client, "/plan?week=2026-09-28")
        client.post("/actions/plan/remove", follow_redirects=False, headers=ORIGIN, data={
            "csrf_token": token, "week_start": "2026-09-28", "date": "2026-10-02", "scope": "garmin"})
        store = JobStore(tmp_path / "jobs")
        for _ in range(50):
            jobs = [j for j in store.list_jobs().jobs if j.operation == "plan_remove"]
            if jobs and jobs[0].status in ("succeeded", "failed"):
                break
            time.sleep(0.1)
        page = client.get("/plan?week=2026-09-28").text
    assert jobs[0].status == "succeeded" and deleted == [77]
    assert _day("2026-10-02")["type"] == "rest"
    assert "Trening usunięty z planu i z zegarka." in page
