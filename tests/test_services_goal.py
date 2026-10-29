# -*- coding: utf-8 -*-
"""Testy postępu wobec celu długoterminowego."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from services.data_extract import SnapshotReadResult, SnapshotStatus
from services.goal import GoalReport, build_goal_report
from services.strategy import parse_strategy
from tests.test_services_strategy import SAMPLE

pytestmark = pytest.mark.usefixtures("testclient_sockets")

TODAY = date(2026, 10, 28)
PROFILE = {"target_date": "2027-10-17 (data robocza)", "target_time": "1:49:00", "current_hm_record": "1:58:30"}


def _run(day, km, minutes):
    return {"date": f"{day} 07:00", "type": "running/generic", "distance_km": km, "duration_min": minutes}


def _report(activities):
    snapshot = SnapshotReadResult(status=SnapshotStatus.FRESH, data={"activities": activities})
    return build_goal_report(snapshot=snapshot, strategy=parse_strategy(SAMPLE), profile=PROFILE, today=TODAY)


def test_countdown_pace_and_current_phase():
    report = _report([])

    assert report.target_date == date(2027, 10, 17)
    assert report.days_left == 354
    assert report.target_pace == "5:10"
    assert report.current_phase.name == "Stabilizacja"
    assert (report.week_number, report.total_weeks) == (5, 12)


def test_criteria_use_the_strategy_thresholds():
    activities = [
        _run("2026-10-25", 16.2, 95), _run("2026-10-21", 10.0, 52.5),
        _run("2026-10-20", 6, 35), _run("2026-10-14", 8, 45), _run("2026-10-07", 8, 45),
    ]
    criteria = {c.label: c for c in _report(activities).criteria}

    assert criteria["Długi bieg"].met is False and "16,2 km" in criteria["Długi bieg"].actual
    assert criteria["Test 10 km"].met is False and "52:30" in criteria["Test 10 km"].actual
    assert criteria["Częstotliwość"].met is False
    assert criteria["Objętość fazy"].met is True and "32,2 km" in criteria["Objętość fazy"].actual


def test_missing_test_run_is_unknown_not_failed():
    criteria = {c.label: c for c in _report([_run("2026-10-25", 5, 30)]).criteria}

    assert criteria["Test 10 km"].met is None
    assert criteria["Test 10 km"].actual == "brak biegu ~10 km w danych"


def test_without_strategy_or_snapshot():
    assert build_goal_report(snapshot=None, strategy=None, profile={}, today=TODAY).status == "strategy_missing"
    assert build_goal_report(snapshot=None, strategy=parse_strategy(SAMPLE), profile={}, today=TODAY).status == "snapshot_missing"


def test_goal_page_renders_phases_and_criteria():
    client = TestClient(create_app(goal_report_provider=lambda: _report([_run("2026-10-25", 12, 70)])))
    response = client.get("/goal")

    assert response.status_code == 200
    assert "za 354 dni" in response.text
    assert "jesteś tu · tydzień 5 z 12" in response.text
    assert "Kryteria gotowości" in response.text and "jeszcze nie" in response.text


def test_goal_page_explains_a_missing_strategy():
    client = TestClient(create_app(goal_report_provider=lambda: GoalReport(status="strategy_missing")))
    response = client.get("/goal")
    assert response.status_code == 404
    assert "Nie masz jeszcze strategii długoterminowej." in response.text
    assert "przyklad-strategii.md" in response.text and 'href="/wizard"' in response.text
