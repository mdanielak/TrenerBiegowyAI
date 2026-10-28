# -*- coding: utf-8 -*-
"""Testy dla services/stats.py i strony /stats."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from services.data_extract import SnapshotReadResult, SnapshotStatus
from services.stats import StatsReport, build_stats_report, normalize_weeks

pytestmark = pytest.mark.usefixtures("testclient_sockets")

TODAY = date(2026, 10, 28)  # środa


def _snapshot(data, status=SnapshotStatus.FRESH):
    return SnapshotReadResult(status=status, data=data)


def _data():
    days = [(TODAY - timedelta(days=offset)).isoformat() for offset in range(60)]
    return {
        "activities": [
            {"date": "2026-10-27 07:00", "type": "running/generic", "distance_km": 8.0, "duration_min": 45.0},
            {"date": "2026-10-20 07:00", "type": "running/generic", "distance_km": 10.0, "duration_min": 55.0},
            {"date": "2026-10-21 07:00", "type": "cycling/road", "distance_km": 30.0, "duration_min": 60.0},
        ],
        "daily_health": [{"date": day, "rhr": 50 if index < 7 else 54, "stress_avg": 20} for index, day in enumerate(days)],
        "sleep": [{"date": day, "score": 80} for day in days[::2]],
        "hrv": [],
    }


def test_weeks_are_limited_to_known_options():
    assert normalize_weeks("12") == 12
    assert normalize_weeks("5") == 8
    assert normalize_weeks("abc") == 8


def test_weekly_load_counts_runs_only_and_marks_the_current_week():
    report = build_stats_report(snapshot=_snapshot(_data()), today=TODAY, weeks=4)

    assert report.status == "ok"
    assert report.start == date(2026, 10, 5)
    assert [week.monday for week in report.weekly] == [
        date(2026, 10, 5), date(2026, 10, 12), date(2026, 10, 19), date(2026, 10, 26)]
    assert [week.distance_km for week in report.weekly] == [0, 0, 10.0, 8.0]
    assert [week.is_current for week in report.weekly] == [False, False, False, True]


def test_missing_measurements_stay_missing_not_zero():
    report = build_stats_report(snapshot=_snapshot(_data()), today=TODAY, weeks=4)

    assert report.metrics["hrv"].average is None
    assert report.metrics["hrv"].measured_days == 0
    sleep = report.metrics["sleep"]
    assert None in [value for _, value in sleep.points]
    assert sleep.average == 80


def test_recent_days_are_compared_with_the_range_average():
    rhr = build_stats_report(snapshot=_snapshot(_data()), today=TODAY, weeks=4).metrics["rhr"]

    assert rhr.recent_average == 50
    assert rhr.average > rhr.recent_average
    assert rhr.higher_is_better is False


def test_missing_and_invalid_snapshots_are_reported():
    assert build_stats_report(snapshot=None, today=TODAY).status == "snapshot_missing"
    invalid = _snapshot(None, status=SnapshotStatus.INVALID)
    assert build_stats_report(snapshot=invalid, today=TODAY).status == "snapshot_invalid"


def test_stats_page_renders_trends_with_polish_numbers():
    requested = []

    def provider(weeks):
        requested.append(weeks)
        return build_stats_report(snapshot=_snapshot(_data()), today=TODAY, weeks=weeks)

    client = TestClient(create_app(stats_report_provider=provider))
    response = client.get("/stats?weeks=4")

    assert response.status_code == 200
    assert requested == [4]
    assert "Kilometry tydzień po tygodniu" in response.text
    assert "Ostatnie 4 tygodnie" in response.text
    assert 'aria-current="page">4 tygodnie' in response.text
    assert "niżej niż średnia" in response.text
    assert "Za mało pomiarów, żeby narysować wykres." in response.text


def test_stats_page_explains_a_missing_snapshot():
    client = TestClient(create_app(stats_report_provider=lambda weeks: StatsReport(status="snapshot_missing")))
    response = client.get("/stats")

    assert response.status_code == 404
    assert "python -m trainer sync" in response.text


def test_axis_stays_within_the_metric_scale():
    from api.views.stats import _axis_bounds
    assert _axis_bounds([1.0, 9.5], (0, 10)) == (0, 10)
    assert _axis_bounds([70.0, 98.0], (0, 100))[1] == 100
    assert _axis_bounds([45.0, 55.0]) == (43, 57)


def test_weeks_carry_phase_range_longest_run_and_plan_minutes():
    from services.strategy import parse_strategy
    from tests.test_services_strategy import SAMPLE

    report = build_stats_report(snapshot=_snapshot(_data()), today=TODAY, weeks=4,
                                strategy=parse_strategy(SAMPLE), planned_minutes={date(2026, 10, 19): 120})

    last_full = report.weekly[-2]
    assert last_full.phase_name == "Stabilizacja" and last_full.phase_km == (28, 38)
    assert last_full.longest_km == 10.0
    assert last_full.planned_min == 120
    assert report.weekly[0].planned_min is None


def test_phase_view_describes_the_last_full_week_in_words():
    from api.views.stats import _stats_view
    from services.strategy import parse_strategy
    from tests.test_services_strategy import SAMPLE

    report = build_stats_report(snapshot=_snapshot(_data()), today=TODAY, weeks=4,
                                strategy=parse_strategy(SAMPLE), planned_minutes={date(2026, 10, 19): 110})
    view = _stats_view(report)

    assert view["phase"]["name"] == "Stabilizacja"
    assert view["phase"]["week_number"] == 5
    assert [row["status"] for row in view["phase"]["rows"]] == ["poniżej zakresu", "poniżej zakresu"]
    assert view["plan_rows"] == [{"label": "19.10", "planned": 110, "done": 55, "share": 50, "is_current": False}]
    assert any(bar["band"] for bar in view["weekly_chart"]["bars"])


def test_planned_minutes_follow_mid_week_revisions(tmp_path, monkeypatch):
    import json
    from services.stats import planned_minutes_by_week

    monkeypatch.setattr("services.plan_files.TRAINING_PLANS_DIR", tmp_path)
    month = tmp_path / "2026-10"
    month.mkdir()

    def plan(start, end, minutes):
        days = [(date.fromisoformat(start) + timedelta(days=i)).isoformat()
                for i in range((date.fromisoformat(end) - date.fromisoformat(start)).days + 1)]
        return {"start_date": start, "end_date": end,
                "workouts": [{"date": d, "type": "easy", "duration_min": minutes} for d in days]}

    (month / "19-25.json").write_text(json.dumps(plan("2026-10-19", "2026-10-25", 30)), encoding="utf-8")
    (month / "22-25.json").write_text(json.dumps(plan("2026-10-22", "2026-10-25", 10)), encoding="utf-8")

    result = planned_minutes_by_week(date(2026, 10, 12), date(2026, 10, 19))

    assert result == {date(2026, 10, 19): 3 * 30 + 4 * 10}
