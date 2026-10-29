from datetime import datetime

import pytest

from services.data_extract import SnapshotReadResult, SnapshotStatus
from services import today
from services.today import build_today_report


def test_readiness_chart_does_not_connect_days_without_measurements():
    from types import SimpleNamespace
    from api.views.today import _readiness_chart

    days = [SimpleNamespace(readiness={"score": value} if value is not None else None,
                            weekday_index=index, temporal_state="past")
            for index, value in enumerate([6, 7, None, 4, 5, None, 8])]
    chart = _readiness_chart(days)
    assert len(chart["lines"]) == 2
    assert len(chart["areas"]) == 2
    assert chart["lines"][0].split() == [f"{p['x']},{p['y']}" for p in chart["points"][:2]]
    assert chart["lines"][1].split() == [f"{p['x']},{p['y']}" for p in chart["points"][3:5]]
    assert chart["points"][2]["score"] is None


def _snapshot(status=SnapshotStatus.FRESH, **data):
    return SnapshotReadResult(status, {"activities": [], "daily_health": [], "sleep": [], "hrv": [], **data})


@pytest.mark.parametrize(
    ("snapshot", "expected"),
    [
        (None, "profile_missing"),
        (SnapshotReadResult(SnapshotStatus.MISSING), "snapshot_missing"),
        (SnapshotReadResult(SnapshotStatus.INVALID), "snapshot_invalid"),
        (_snapshot(), "ok"),
    ],
)
def test_build_today_report_has_expected_status(snapshot, expected, tmp_path):
    report = build_today_report(snapshot=snapshot, planned=None, availability=None,
                                now=datetime(2026, 10, 2, 8, 0))
    assert report.status == expected


def test_build_today_report_sorts_yesterday_and_uses_requested_weekday(tmp_path):
    report = build_today_report(
        snapshot=_snapshot(activities=[
            {"date": "2026-10-01 17:14"},
            {"date": "2026-10-01 07:05"},
            {"date": "2026-10-01 16:28"},
        ]),
        planned=None,
        availability={"available": False},
        now=datetime(2026, 10, 2, 8, 0),
    )
    assert [item["date"] for item in report.yesterday_activities] == [
        "2026-10-01 07:05", "2026-10-01 16:28", "2026-10-01 17:14",
    ]
    assert report.weekday_index == 4


@pytest.mark.parametrize(
    ("planned", "data", "expected"),
    [
        ({"name": "Bieg"}, {"daily_health": [{"date": "2026-10-02", "rhr": 45, "stress_avg": 20}],
                            "sleep": [{"date": "2026-10-02", "score": 95}],
                            "hrv": [{"date": "2026-10-02", "status": "BALANCED", "last_night": 50,
                                     "baseline_low": 40, "baseline_high": 60}]}, "follow_plan"),
        ({"name": "Bieg"}, {"daily_health": [{"date": "2026-10-02", "rhr": 60, "stress_avg": 55}],
                            "sleep": [{"date": "2026-10-02", "score": 40}]}, "rest"),
        (None, {}, "rest"),
        # Brak pomiarów nie odwołuje treningu: to brak danych, a nie zła ocena.
        ({"name": "Bieg"}, {}, "follow_plan"),
    ],
)
def test_build_today_report_suggestion_rule(planned, data, expected, tmp_path):
    report = build_today_report(snapshot=_snapshot(**data), planned=planned,
                                availability={"available": False}, now=datetime(2026, 10, 2))
    assert report.suggestion == expected


def test_yesterdays_measurements_never_count_as_today():
    data = {"daily_health": [{"date": "2026-10-01", "rhr": 60, "stress_avg": 50}],
            "sleep": [{"date": "2026-10-01", "score": 40}],
            "hrv": [{"date": "2026-10-01", "status": "LOW", "last_night": 30, "baseline_low": 40, "baseline_high": 60}]}
    report = build_today_report(snapshot=_snapshot(**data), planned=None,
                                availability={"available": False}, now=datetime(2026, 10, 2))
    assert report.readiness["level"] == "no_data"
    assert report.signals == {"sleep_score": None, "hrv_status": None, "rhr": None, "stress_avg": None}


def test_no_measurements_show_no_red_banner_and_no_zero_score(testclient_sockets):
    from fastapi.testclient import TestClient
    from api.main import create_app

    report = build_today_report(snapshot=_snapshot(), planned=None, availability={"available": False},
                                now=datetime(2026, 10, 2))
    page = TestClient(create_app(report_provider=lambda: report)).get("/").text
    assert "Brak pomiarów z nocy" in page and "health-alert" not in page
    assert '<span class="ring-score">—</span>' in page


def test_build_today_report_uses_none_for_missing_signals_and_keeps_stale_data(tmp_path):
    report = build_today_report(
        snapshot=_snapshot(SnapshotStatus.STALE), planned=None,
        availability={"available": False}, now=datetime(2026, 10, 2),
    )
    assert report.status == "ok"
    assert report.snapshot_status is SnapshotStatus.STALE
    assert report.readiness is not None
    assert report.signals == {
        "sleep_score": None, "hrv_status": None, "rhr": None, "stress_avg": None,
    }


def test_build_today_report_keeps_snapshot_timestamp(tmp_path):
    report = build_today_report(
        snapshot=_snapshot(timestamp="2026-10-02T09:14:00+00:00"), planned=None,
        availability={"available": False}, now=datetime(2026, 10, 2),
    )
    assert report.snapshot_timestamp == "2026-10-02T09:14:00+00:00"


def test_build_today_report_includes_trends_for_report_date(tmp_path):
    report = build_today_report(
        snapshot=_snapshot(
            daily_health=[
                {"date": "2026-10-02", "rhr": 48, "stress_avg": 25},
                {"date": "2026-10-01", "rhr": 50, "stress_avg": 30},
            ],
            sleep=[
                {"date": "2026-10-02", "score": 90},
                {"date": "2026-10-01", "score": 80},
            ],
        ),
        planned=None,
        availability={"available": False},
        now=datetime(2026, 10, 2),
    )

    assert report.trends["rhr"]["direction"] == "down"
    assert report.trends["rhr"]["favorable"] is True
    assert report.trends["sleep_score"]["direction"] == "up"


def test_execution_is_none_without_planned_workout(tmp_path):
    report = build_today_report(snapshot=_snapshot(), planned=None, availability=None,
                                now=datetime(2026, 10, 2))
    assert report.execution is None


def test_execution_copies_matched_today_activity_values(tmp_path):
    planned = {"date": "2026-10-02", "workout_id": 7, "name": "Spokojny bieg", "distance_km": 5}
    activity = {"date": "2026-10-02 07:00", "activity_id": 12, "type": "running",
                "name": "Spokojny bieg", "distance_km": 5.0, "duration_min": 31.5,
                "avg_hr": 140, "max_hr": 155, "pace": "6:18"}
    report = build_today_report(snapshot=_snapshot(activities=[activity]), planned=planned,
                                availability=None, now=datetime(2026, 10, 2))
    assert report.execution == {
        "happened": True, "match_method": "heuristic", "certain": True,
        "activity_id": 12, "distance_km": 5.0, "duration_min": 31.5,
        "avg_hr": 140, "max_hr": 155, "pace": "6:18", "review_key": "2026-10-02:7",
    }


def test_execution_without_today_activity_has_none_values(tmp_path):
    planned = {"date": "2026-10-02", "workout_id": 7, "name": "Bieg"}
    report = build_today_report(snapshot=_snapshot(), planned=planned, availability=None,
                                now=datetime(2026, 10, 2))
    assert report.execution["happened"] is False
    assert report.execution["match_method"] == "unmatched"
    assert all(report.execution[key] is None for key in (
        "activity_id", "distance_km", "duration_min", "avg_hr", "max_hr", "pace",
    ))


def test_execution_is_uncertain_for_ambiguous_match(tmp_path):
    planned = {"date": "2026-10-02", "name": "Bieg", "distance_km": 5}
    activities = [
        {"date": "2026-10-02 07:00", "type": "running", "distance_km": 5},
        {"date": "2026-10-02 08:00", "type": "running", "distance_km": 5},
    ]
    report = build_today_report(snapshot=_snapshot(activities=activities), planned=planned,
                                availability=None, now=datetime(2026, 10, 2))
    assert report.execution["match_method"] == "ambiguous"
    assert report.execution["certain"] is False


def test_today_activities_are_separate_from_yesterday(tmp_path):
    report = build_today_report(snapshot=_snapshot(activities=[
        {"date": "2026-10-01 07:00", "activity_id": 1},
        {"date": "2026-10-02 08:00", "activity_id": 3},
        {"date": "2026-10-02 06:00", "activity_id": 2},
    ]), planned=None, availability=None, now=datetime(2026, 10, 2))
    assert [item["activity_id"] for item in report.today_activities] == [2, 3]
    assert [item["activity_id"] for item in report.yesterday_activities] == [1]


def test_review_key_is_stable_for_same_planned_workout(tmp_path):
    planned = {"date": "2026-10-02", "workout_id": 7, "name": "Bieg"}
    first = build_today_report(snapshot=_snapshot(), planned=planned, availability=None,
                               now=datetime(2026, 10, 2))
    second = build_today_report(snapshot=_snapshot(), planned=planned, availability=None,
                                now=datetime(2026, 10, 2))
    assert first.execution["review_key"] == second.execution["review_key"]


def test_execution_uses_first_of_multiple_planned_workouts(tmp_path):
    planned = [
        {"date": "2026-10-02", "workout_id": 7, "name": "Pierwszy"},
        {"date": "2026-10-02", "workout_id": 8, "name": "Drugi"},
    ]
    report = build_today_report(snapshot=_snapshot(), planned=planned, availability=None,
                                now=datetime(2026, 10, 2))
    assert report.planned == planned[0]
    assert report.execution["review_key"] == "2026-10-02:7"
    assert report.execution["planned_count"] == 2


@pytest.mark.parametrize("schedule_status", ["pending", "unknown"])
def test_unconfirmed_schedule_is_not_a_planned_today_workout(monkeypatch, schedule_status):
    entry = {
        "workout_id": 7, "name": "Bieg", "status": "active", "date": None,
        "intended_date": "2026-10-02", "schedule_status": schedule_status,
    }
    monkeypatch.setattr(today, "list_workouts", lambda status: [entry])

    assert today._today_registry_entries("2026-10-02") == []


def test_confirmed_schedule_remains_a_planned_today_workout(monkeypatch):
    entry = {
        "workout_id": 7, "name": "Bieg", "status": "active", "date": "2026-10-02",
        "intended_date": "2026-10-02", "schedule_status": "confirmed",
    }
    monkeypatch.setattr(today, "list_workouts", lambda status: [entry])

    assert today._today_registry_entries("2026-10-02") == [entry]
