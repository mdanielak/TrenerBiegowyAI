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
                {"day": "2026-10-02", "rhr": 48, "stress_avg": 25},
                {"day": "2026-10-01", "rhr": 50, "stress_avg": 30},
            ],
            sleep=[
                {"day": "2026-10-02", "score": 90},
                {"day": "2026-10-01", "score": 80},
            ],
        ),
        planned=None,
        availability={"available": False},
        now=datetime(2026, 10, 2),
    )

    assert report.trends["rhr"]["direction"] == "down"
    assert report.trends["rhr"]["favorable"] is True
    assert report.trends["sleep_score"]["direction"] == "up"
