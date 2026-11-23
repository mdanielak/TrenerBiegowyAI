# -*- coding: utf-8 -*-
"""Ocena tygodnia biegowego: dane lokalne, komentarz AI, zapis i przycisk na stronie Plan."""
import time
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from ai.week_review import WeekComment, build_week_message
from services import plan as plan_service
from services.actions import review_week, week_review_key
from services.jobs import UserMessageError
from tests.test_api_plan import _app, _csrf
from tests.test_plan_remove import ORIGIN, TODAY, _future_plan

pytestmark = pytest.mark.usefixtures("testclient_sockets")
WEEK = "2026-09-28"
RUN = {"date": "2026-09-28T07:00:00", "type": "running", "duration_min": 41, "distance_km": 6.8,
       "avg_hr": 131, "max_hr": 149}


@pytest.fixture
def plans_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("services.plan_files.TRAINING_PLANS_DIR", tmp_path / "plans")
    monkeypatch.setattr("trainer.config.AI_DATA_EXPORT_ENABLED", True)
    monkeypatch.setattr("trainer.config.AI_API_KEY", "test-key")
    plan_service.save_plan(_future_plan())


def _call(*, today=TODAY, runs=(RUN,), captured=None, saved=None):
    class Provider:
        def chat(self, system, message, **kwargs):
            if captured is not None:
                captured.update(system=system, message=message)
            return WeekComment(komentarz="Pięć zdań. Drugie. Trzecie. Czwarte. Piąte.")

    return review_week(
        week_start=WEEK, today=today, snapshot_reader=lambda: {"activities": list(runs)},
        profile_loader=lambda: {"hr_zone_floors": {"z1": 96, "z2": 122}},
        provider_factory=Provider,
        save=(lambda **kw: saved.update(kw)) if saved is not None else (lambda **kw: None))


def test_week_review_sends_local_numbers_and_saves_under_a_week_key(plans_dir):
    captured, saved = {}, {}
    result = _call(captured=captured, saved=saved)

    assert result["comment"].startswith("Pięć zdań")
    assert saved["review_key"] == "week:2026-09-28" == week_review_key(WEEK)
    message = captured["message"]
    assert "PLAN TYGODNIA" in message and "WYKONANIE (Z ZEGARKA)" in message
    assert "41 min, 6,8 km, średnie tętno 131 bpm" in message
    assert "od 5 do 7 zdań" in captured["system"] and '{"komentarz":' in captured["system"]


def test_week_review_needs_a_workout_that_already_passed(plans_dir):
    with pytest.raises(UserMessageError):
        _call(today=datetime(2026, 9, 28, 6, 0), runs=())


def test_message_is_deterministic_and_has_no_none():
    kwargs = dict(plan={"workouts": []}, summary={}, week_runs=[], runner={}, note="")
    assert build_week_message(**kwargs) == build_week_message(**kwargs)
    assert "None" not in build_week_message(**kwargs)


def test_plan_page_offers_the_button_and_the_job_returns_the_comment(tmp_path, plans_dir):
    saved = {}
    calls = []

    def operation(*, week_start):
        calls.append(week_start)
        saved[week_review_key(week_start)] = "Komentarz do tygodnia."

    app = _app(tmp_path, plan=_future_plan(), week_review_operation=operation,
               review_loader=lambda *, review_key: {"comment": saved[review_key]} if review_key in saved else None)
    with TestClient(app) as client:
        page = client.get(f"/plan?week={WEEK}").text
        assert "Oceń mój tydzień biegowy" in page and 'action="/actions/week-review"' in page
        sent = client.post("/actions/week-review", headers={**ORIGIN, "X-Requested-With": "fetch"},
                           data={"csrf_token": _csrf(client, f"/plan?week={WEEK}"), "week_start": WEEK})
        assert sent.json()["state"] in {"running", "busy"}
        for _ in range(100):
            status = client.get(f"/actions/week-review/status?week={WEEK}").json()
            if status["state"] != "running":
                break
            time.sleep(0.05)
        reopened = client.get(f"/plan?week={WEEK}").text
    assert calls == [WEEK]
    assert status == {"state": "done", "comment": "Komentarz do tygodnia."}
    assert "Komentarz do tygodnia." in reopened and "Oceń tydzień ponownie" in reopened


def test_week_review_rejects_bad_csrf_with_json(tmp_path):
    with TestClient(_app(tmp_path, plan=_future_plan())) as client:
        _csrf(client, f"/plan?week={WEEK}")
        response = client.post("/actions/week-review", headers={**ORIGIN, "X-Requested-With": "fetch"},
                               data={"csrf_token": "zly", "week_start": WEEK})
    assert response.status_code == 403 and response.json()["state"] == "failed"
