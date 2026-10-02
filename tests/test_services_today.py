from datetime import datetime

import pytest

from services.data_extract import SnapshotReadResult, SnapshotStatus
from services.today import build_today_report


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
        ({"name": "Bieg"}, {"daily_health": [{"rhr": 45, "stress_avg": 20}], "sleep": [{"score": 95}], "hrv": [{"status": "BALANCED", "last_night": 50, "baseline_low": 40, "baseline_high": 60}]}, "follow_plan"),
        (None, {}, "rest"),
        ({"name": "Bieg"}, {}, "rest"),
    ],
)
def test_build_today_report_suggestion_rule(planned, data, expected, tmp_path):
    report = build_today_report(snapshot=_snapshot(**data), planned=planned,
                                availability={"available": False}, now=datetime(2026, 10, 2))
    assert report.suggestion == expected


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
