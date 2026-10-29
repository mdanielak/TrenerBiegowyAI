# -*- coding: utf-8 -*-
"""Testy strony /plan i akcji planu w dashboardzie."""
from __future__ import annotations

import re
from datetime import datetime

from fastapi.testclient import TestClient
import pytest

from api.main import create_app
from services.data_extract import SnapshotReadResult, SnapshotStatus
from services.jobs import JobStore
from services.today import TodayReport


# Pozycja treningu (z rejestru albo z planu AI) ma ikonę rodzaju treningu.
_PLAN_ITEM_MARKER = '<span class="item-icon kind-icon"><img class="asset" src="/assets/03_activity/kind_'


pytestmark = pytest.mark.usefixtures("testclient_sockets")


def _readiness():
    return {
        "score": 8.0, "max_score": 10.0, "raw_score": 8.0, "available_max_score": 10.0,
        "insufficient_data": False, "missing_metrics": [], "available_metrics": ["sleep"],
        "data_coverage": 0.25, "confidence": "high", "level": "ready", "rhr": 48.0,
        "hrv_status": "BALANCED", "hrv_last": 52.0, "hrv_baseline": "40-60",
        "sleep_score_val": 85.0, "sleep_total": 7.5, "stress": 22.0, "details": [],
    }


def _report(**overrides):
    values = {
        "status": "ok",
        "date": "2026-10-02",
        "weekday_index": 4,
        "snapshot_status": SnapshotStatus.FRESH,
        "planned": None,
        "yesterday_date": "2026-10-01",
        "yesterday_activities": [],
        "readiness": _readiness(),
        "signals": {"sleep_score": 85, "hrv_status": "BALANCED", "rhr": 48, "stress_avg": 22},
        "availability": {"available": True, "min_minutes": 30, "max_minutes": 60},
        "suggestion": "follow_plan",
        "snapshot_timestamp": None,
    }
    values.update(overrides)
    return TodayReport(**values)


def _plan_workout():
    return {
        "day": "fri", "date": "2026-10-02", "type": "easy", "name": "Bieg łatwy 45 min",
        "description": "Spokojne tempo.", "distance_km": 7.5, "duration_min": 45,
        "pace_target": None, "hr_target": "122-136 bpm", "hr_zone": "Z2",
        "garmin_upload": False, "garmin_workout_id": None, "notes": "",
    }


def _rest_workout(day, date, description=""):
    return {
        "day": day, "date": date, "type": "rest", "name": "Odpoczynek",
        "description": description, "distance_km": None, "duration_min": None,
        "pace_target": None, "hr_target": None, "hr_zone": None,
        "garmin_upload": False, "garmin_workout_id": None, "notes": "",
    }


def _plan():
    """Pełny tydzień planu: dwa treningi z uwagami, przerwa z powodem i cztery dni odpoczynku."""
    workouts = [
        {
            "day": "mon", "date": "2026-09-28", "type": "easy", "name": "Bieg łatwy 45 min",
            "description": "Spokojne tempo, czuj rozmiar.", "distance_km": 7.5, "duration_min": 45,
            "pace_target": None, "hr_target": "122-136 bpm", "hr_zone": "Z2",
            "garmin_upload": False, "garmin_workout_id": None,
            "notes": "Zostaw siły na weekend.",
        },
        {
            "day": "tue", "date": "2026-09-29", "type": "tempo", "name": "Tempo 3×8 min",
            "description": "Trzy powtórzenia w zadanym tempie.", "distance_km": 10.0,
            "duration_min": 60, "pace_target": "4:20-4:25", "hr_target": "152-166 bpm",
            "hr_zone": "Z3", "garmin_upload": True, "garmin_workout_id": 42,
            "notes": "Wycisnij na trzecim powtórzeniu.",
        },
        _rest_workout("wed", "2026-09-30", "Przerwa z powodu bólu kolana."),
        _rest_workout("thu", "2026-10-01"),
        _rest_workout("fri", "2026-10-02"),
        _rest_workout("sat", "2026-10-03"),
        _rest_workout("sun", "2026-10-04"),
    ]
    return {
        "start_date": "2026-09-28", "end_date": "2026-10-04", "priority": "normal",
        "focus": "Baza tygodnia", "summary": "Jeden akcent i dwa biegi regeneracyjne.",
        "generated_at": "2026-09-27T20:00:00+00:00",
        "workouts": workouts,
    }


def _registry_workout(name="Bieg z zegarka"):
    """Wpis rejestru Garmina: to, co faktycznie jest w kalendarzu zegarka."""
    return {
        "workout_id": 7,
        "name": name,
        "date": "2026-10-02",
        "spec": {"kind": "hr_zone_run", "duration_min": 45, "zone_number": 2},
    }


def _execution():
    return {
        "happened": False,
        "match_method": "none",
        "certain": True,
        "activity_id": None,
        "distance_km": None,
        "duration_min": None,
        "avg_hr": None,
        "max_hr": None,
        "pace": None,
        "review_key": "2026-10-02:7",
    }


def _app(tmp_path, *, plan=None, report=None, ai_ready=True, plan_operation=None,
         snapshot_provider=None, recommendation_loader=None, **kwargs):
    if snapshot_provider is None:
        snapshot_provider = lambda: SnapshotReadResult(status=SnapshotStatus.FRESH, data={})
    return create_app(
        report_provider=lambda: report or _report(),
        plan_provider=lambda monday: plan,
        profile_provider=lambda: {"name": "Maciej", "hr_zone_floors": {"z1": 96, "z2": 122},
                                  "target_race": "półmaraton", "target_date": "2027-10-17"},
        ai_settings_provider=lambda: {"key_present": ai_ready, "export_enabled": ai_ready},
        availability_provider=lambda: {"mon": {"available": True, "min_minutes": 35, "max_minutes": 45}},
        review_loader=lambda **review_kwargs: None,
        recommendation_loader=recommendation_loader or (lambda **loader_kwargs: None),
        job_store=JobStore(tmp_path / "jobs"),
        lock_directory=tmp_path / "locks",
        now_provider=lambda: datetime(2026, 10, 2, 12, 0),
        plan_operation=plan_operation,
        snapshot_provider=snapshot_provider,
        **kwargs,
    )


def _csrf(client, path="/plan"):
    page = client.get(path)
    match = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    if match is None:
        raise RuntimeError("Brak tokenu CSRF na stronie testowej.")
    return match.group(1)


def test_plan_page_renders_with_the_plan_navigation_active(tmp_path):
    with TestClient(_app(tmp_path)) as client:
        response = client.get("/plan")

    assert response.status_code == 200
    assert "Plan treningowy" in response.text
    assert 'href="/plan" aria-current="page"' in response.text


def test_plan_page_shows_empty_state_without_a_plan(tmp_path):
    with TestClient(_app(tmp_path)) as client:
        response = client.get("/plan")

    assert response.status_code == 200
    assert "Nie ma jeszcze planu na ten tydzień." in response.text


def test_plan_page_shows_the_week_and_its_days(tmp_path):
    with TestClient(_app(tmp_path, plan=_plan())) as client:
        response = client.get("/plan")

    assert response.status_code == 200
    assert "Baza tygodnia" in response.text
    assert "Bieg łatwy 45 min" in response.text
    assert "122-136 bpm" in response.text


def test_plan_page_shows_kind_icon_zone_chip_and_shape_of_the_week(tmp_path):
    with TestClient(_app(tmp_path, plan=_plan())) as client:
        response = client.get("/plan")

    assert response.status_code == 200
    assert 'src="/assets/03_activity/kind_easy.png"' in response.text
    assert 'class="zone-chip z2"' in response.text
    assert response.text.count('<rect class="chart-bar"') == 2


def test_plan_page_shows_readiness_pill_only_for_measured_days(tmp_path):
    snapshot = SnapshotReadResult(
        status=SnapshotStatus.FRESH,
        data={"daily_health": [{"date": "2026-09-28", "rhr": 48, "stress_avg": 20}]},
    )

    with TestClient(_app(tmp_path, plan=_plan(), snapshot_provider=lambda: snapshot)) as client:
        response = client.get("/plan")

    assert response.status_code == 200
    pills = re.findall(r'class="pill \w+">([\d.]+) z ([\d.]+)</span>', response.text)
    assert len(pills) == 1
    assert "Gotowość zmierzona w 1 z 7 dni." in response.text


def test_plan_page_warns_when_the_snapshot_is_stale(tmp_path):
    snapshot = SnapshotReadResult(status=SnapshotStatus.STALE, data={})

    with TestClient(_app(tmp_path, plan=_plan(), snapshot_provider=lambda: snapshot)) as client:
        response = client.get("/plan")

    assert response.status_code == 200
    assert "Dane o aktywnościach mogą być nieaktualne." in response.text


def test_plan_page_lists_notes_only_for_days_that_have_them(tmp_path):
    with TestClient(_app(tmp_path, plan=_plan())) as client:
        response = client.get("/plan")

    assert response.status_code == 200
    assert "Uwagi do planu" in response.text
    notes_section = response.text.split("Uwagi do planu", 1)[1]
    assert notes_section.count('class="list-item"') == 3
    assert "Spokojne tempo, czuj rozmiar." in notes_section
    assert "Zostaw siły na weekend." in notes_section
    assert "Przerwa z powodu bólu kolana." in notes_section
    assert "1 października 2026" not in notes_section


def test_plan_page_navigates_between_weeks_relative_to_the_displayed_one(tmp_path):
    with TestClient(_app(tmp_path, plan=_plan())) as client:
        current = client.get("/plan")
        previous = client.get("/plan?week=2026-09-21")

    assert "28 września 2026 – 4 października 2026" in current.text
    assert "Ten tydzień" not in current.text
    assert 'href="/plan?week=2026-09-21"' in current.text
    assert 'href="/plan?week=2026-10-05"' in current.text

    assert "21 września 2026 – 27 września 2026" in previous.text
    assert 'href="/plan?week=2026-09-14"' in previous.text
    assert 'href="/plan?week=2026-09-28"' in previous.text


def test_plan_action_rejects_request_without_csrf(tmp_path):
    with TestClient(_app(tmp_path)) as client:
        response = client.post("/actions/plan", data={"week_start": "2026-09-28"},
                               headers={"Origin": "http://testserver"})

    assert response.status_code == 403
    assert "Nie można potwierdzić, że żądanie pochodzi z tej strony." in response.text
    assert JobStore(tmp_path / "jobs").list_jobs().jobs == []


def test_plan_action_queues_a_background_job(tmp_path):
    calls = []

    with TestClient(_app(tmp_path, plan_operation=lambda **kwargs: calls.append(kwargs))) as client:
        token = _csrf(client)
        response = client.post("/actions/plan", data={"csrf_token": token, "week_start": "2026-09-28"},
                               headers={"Origin": "http://testserver"}, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/plan"
    jobs = JobStore(tmp_path / "jobs").list_jobs().jobs
    assert [job.operation for job in jobs] == ["plan"]
    assert calls == [{"week_start": "2026-09-28"}]


def test_plan_action_is_blocked_without_ai_consent(tmp_path):
    with TestClient(_app(tmp_path, ai_ready=False)) as client:
        token = _csrf(client)
        response = client.post("/actions/plan", data={"csrf_token": token, "week_start": "2026-09-28"},
                               headers={"Origin": "http://testserver"}, follow_redirects=False)

    assert response.status_code == 400
    assert "Generowanie planu wymaga włączenia wysyłania danych do AI." in response.text
    assert JobStore(tmp_path / "jobs").list_jobs().jobs == []


def test_dashboard_shows_the_ai_plan_workout_for_today(tmp_path):
    report = _report(plan_workout=_plan_workout())

    with TestClient(_app(tmp_path, report=report)) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "Bieg łatwy 45 min" in response.text
    assert "To trening z planu AI." in response.text
    assert "Zapytaj AI, co dziś zrobić" in response.text


def test_dashboard_shows_the_plan_workout_beside_the_registry_workout(tmp_path):
    report = _report(planned=_registry_workout(), execution=_execution(),
                     plan_workout=_plan_workout())

    with TestClient(_app(tmp_path, report=report)) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "Bieg z zegarka" in response.text
    assert "Bieg łatwy 45 min" in response.text
    assert response.text.count(_PLAN_ITEM_MARKER) == 2
    assert "To trening z planu AI." in response.text


def test_dashboard_hides_the_plan_item_when_the_watch_already_has_it(tmp_path):
    report = _report(planned=_registry_workout(name="Bieg łatwy 45 min"), execution=_execution(),
                     plan_workout=_plan_workout())

    with TestClient(_app(tmp_path, report=report)) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.text.count(_PLAN_ITEM_MARKER) == 1


def test_dashboard_shows_the_recommendation_in_its_own_card(tmp_path):
    recommendation = {
        "readiness": "ready_with_reserves",
        "recommendation": "Zrób lekki bieg 30 minut.",
        "planned_workout": None,
        "adjustment_needed": False,
        "reasoning_summary": "Zmęczenie jest niewielkie, więc tempo może być równe.",
        "warnings": ["Uwaga: ból kolana."],
    }

    with TestClient(_app(tmp_path, recommendation_loader=lambda **kwargs: recommendation)) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "Co dziś zrobić" in response.text
    assert "Zrób lekki bieg 30 minut." in response.text
    assert "Zmęczenie jest niewielkie, więc tempo może być równe." in response.text
    assert "Uwaga: ból kolana." in response.text
    assert response.text.index("Trening na dziś") < response.text.index("Co dziś zrobić")
    assert response.text.index("Co dziś zrobić") < response.text.index("Twoja dostępność")
