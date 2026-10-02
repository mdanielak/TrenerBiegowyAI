from __future__ import annotations

import socket

from fastapi.testclient import TestClient
import pytest

from api.main import create_app
from services.data_extract import SnapshotStatus
from services.today import TodayReport
from services.week import DayAvailability, WeekActivity, WeekDayReport, WeekReport, WeekWorkout


_ORIGINAL_CONNECT = socket.socket.connect


@pytest.fixture(autouse=True)
def _testclient_socketpair(monkeypatch):
    """Pozwól TestClient utworzyć wyłącznie jego wewnętrzną parę gniazd."""
    def socketpair():
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _ORIGINAL_CONNECT(client, listener.getsockname())
        server, _ = listener.accept()
        listener.close()
        return server, client

    monkeypatch.setattr(socket, "socketpair", socketpair)


def _readiness(level="ready"):
    return {
        "score": 8.0,
        "max_score": 10.0,
        "raw_score": 8.0,
        "available_max_score": 10.0,
        "insufficient_data": False,
        "missing_metrics": [],
        "available_metrics": ["sleep"],
        "data_coverage": 1.0,
        "confidence": "high",
        "level": level,
        "rhr": 48.0,
        "hrv_status": "BALANCED",
        "hrv_last": 52.0,
        "hrv_baseline": "40-60",
        "sleep_score_val": 85.0,
        "sleep_total": 7.5,
        "stress": 22.0,
        "details": [],
    }


def _report(status="ok", snapshot_status=SnapshotStatus.FRESH, **overrides):
    values = {
        "status": status,
        "date": "2026-10-02",
        "weekday_index": 4,
        "snapshot_status": snapshot_status if status == "ok" else None,
        "planned": {"name": "Spokojny bieg", "spec": {"kind": "easy"}},
        "yesterday_date": "2026-10-01",
        "yesterday_activities": [{"date": "2026-10-01 07:30", "name": "Bieg", "distance_km": 5, "duration_min": 30, "avg_hr": 140}],
        "readiness": _readiness(),
        "signals": {"sleep_score": 85, "hrv_status": "BALANCED", "rhr": 48, "stress_avg": 22},
        "availability": {"available": True, "min_minutes": 30, "max_minutes": 60},
        "suggestion": "follow_plan",
    }
    values.update(overrides)
    return TodayReport(**values)


def _client(report):
    return TestClient(create_app(report_provider=lambda: report))


def _week_report(statuses=None, warnings=None):
    statuses = statuses or ["no_plan"] * 7
    days = []
    for index, status in enumerate(statuses):
        days.append(WeekDayReport(
            date=f"2026-09-{28 + index:02d}" if index < 3 else f"2026-10-{index - 2:02d}",
            weekday_index=index, temporal_state="today" if index == 4 else "past",
            availability=DayAvailability(False, 0, 0, False), status=status,
            warnings=[], workouts=[], activities=[],
        ))
    return WeekReport("2026-09-28", "2026-10-04", "2026-10-02", "local_registry", "ok",
                      SnapshotStatus.FRESH, None, warnings or [], days)


def _week_client(report):
    return TestClient(create_app(report_provider=lambda: _report(), week_report_provider=lambda: report))


def test_health_is_minimal_liveness():
    with _client(_report()) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}


@pytest.mark.parametrize(
    ("status", "expected_status", "command"),
    [
        ("profile_missing", 404, "python -m trainer setup"),
        ("snapshot_missing", 404, "python -m trainer sync"),
        ("snapshot_invalid", 503, "python -m trainer sync"),
    ],
)
def test_dashboard_shows_friendly_error_for_missing_data(status, expected_status, command):
    with _client(_report(status=status)) as client:
        response = client.get("/")
    assert response.status_code == expected_status
    assert command in response.text
    assert response.headers["cache-control"] == "no-store"


def test_dashboard_renders_ok_report_and_missing_signals():
    report = _report(signals={"sleep_score": None, "hrv_status": None, "rhr": None, "stress_avg": None})
    with _client(report) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "piątek" in response.text
    assert "<strong>Sen</strong><span>—</span>" in response.text
    assert "<strong>HRV</strong><span>—</span>" in response.text
    assert "<strong>Tętno spoczynkowe</strong><span>—</span>" in response.text
    assert "<strong>Stres</strong><span>—</span>" in response.text
    assert "<strong>Tętno spoczynkowe</strong><span>—</span>" in response.text
    assert "— bpm" not in response.text
    assert response.headers["cache-control"] == "no-store"


def test_dashboard_translates_hrv_status_and_formats_polish_summary():
    report = _report(
        readiness=_readiness(),
        signals={"sleep_score": 85, "hrv_status": "UNBALANCED", "rhr": 48, "stress_avg": 22},
    )
    with _client(report) as client:
        response = client.get("/")
    assert "<strong>HRV</strong><span>niezrównoważone</span>" in response.text
    assert "<strong>Tętno spoczynkowe</strong><span>48 bpm</span>" in response.text
    assert "<div class=\"score\">8<span> / 10</span>" in response.text
    assert "2 października 2026, piątek" in response.text
    assert "Dane są aktualne." in response.text
    assert "Realizuj zaplanowany trening spokojnie." in response.text


def test_dashboard_keeps_unknown_hrv_status_raw():
    report = _report(signals={"sleep_score": 85, "hrv_status": "CUSTOM_STATUS", "rhr": 48, "stress_avg": 22})
    with _client(report) as client:
        response = client.get("/")
    assert "<strong>HRV</strong><span>CUSTOM_STATUS</span>" in response.text


def test_dashboard_shows_stale_warning():
    with _client(_report(snapshot_status=SnapshotStatus.STALE)) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "Dane są nieaktualne" in response.text
    assert "python -m trainer sync" in response.text


def test_dashboard_does_not_show_warning_for_fresh_snapshot():
    with _client(_report()) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "Dane są nieaktualne" not in response.text


def test_dashboard_escapes_activity_name():
    report = _report(yesterday_activities=[{"date": "2026-10-01 07:30", "name": "<b>niezaufane</b>", "distance_km": 5, "duration_min": 30, "avg_hr": 140}])
    with _client(report) as client:
        response = client.get("/")
    assert "&lt;b&gt;niezaufane&lt;/b&gt;" in response.text
    assert "<b>niezaufane</b>" not in response.text


@pytest.mark.parametrize(
    ("status", "expected_status"),
    [("profile_missing", 404), ("snapshot_missing", 404), ("snapshot_invalid", 503)],
)
def test_readiness_uses_snapshot_error_policy(status, expected_status):
    with _client(_report(status=status)) as client:
        response = client.get("/readiness")
    assert response.status_code == expected_status


def test_readiness_returns_stale_data_with_warning():
    with _client(_report(snapshot_status=SnapshotStatus.STALE)) as client:
        response = client.get("/readiness")
    assert response.status_code == 200
    assert "nieaktualne" in response.json()["warning"]


def test_week_renders_seven_days_and_no_store():
    with _week_client(_week_report()) as client:
        response = client.get("/week")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    for weekday in ("Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"):
        assert weekday in response.text


def test_week_renders_all_day_status_labels():
    statuses = ["no_plan", "activity_only", "planned", "matched", "partially_matched", "no_record", "uncertain"]
    with _week_client(_week_report(statuses)) as client:
        response = client.get("/week")
    for label in ("Brak zapisanego treningu", "Aktywności bez zapisanego treningu", "Zaplanowane",
                  "Znaleziono wykonanie", "Znaleziono wykonanie części treningów",
                  "Brak wykonania w lokalnych danych", "Nie można jednoznacznie porównać"):
        assert label in response.text


def test_week_shows_all_workouts_and_activities_and_escapes_names():
    report = _week_report()
    report.days[0].workouts = [
        WeekWorkout(1, None, "<script>workout</script>", "running", "matched", 1, "heuristic", []),
        WeekWorkout(2, None, "Drugi trening", "running", "planned", None, "unmatched", []),
    ]
    report.days[0].activities = [
        WeekActivity(1, "2026-09-28 08:00", "running/generic", "<script>activity</script>", 5, 30, 1),
        WeekActivity(2, "2026-09-28 09:00", "walking/generic", "Spacer", None, None, None),
    ]
    with _week_client(report) as client:
        response = client.get("/week")
    assert "&lt;script&gt;workout&lt;/script&gt;" in response.text
    assert "&lt;script&gt;activity&lt;/script&gt;" in response.text
    assert "<script>" not in response.text
    assert "Drugi trening" in response.text and "Spacer" in response.text
    assert "— km" not in response.text and "— min" not in response.text


@pytest.mark.parametrize(
    ("status", "warnings", "expected"),
    [
        (SnapshotStatus.MISSING, [], "Plan widoczny"),
        (SnapshotStatus.INVALID, [], "Plan widoczny"),
        (SnapshotStatus.STALE, ["snapshot_stale"], "Dane o aktywnościach mogą być nieaktualne"),
    ],
)
def test_week_snapshot_states_are_not_errors(status, warnings, expected):
    report = _week_report(warnings=warnings)
    report.snapshot_status = status
    report.days[0].workouts = [WeekWorkout(1, None, "Plan widoczny", "running", "planned", None, "unmatched", [])]
    with _week_client(report) as client:
        response = client.get("/week")
    assert response.status_code == 200
    assert expected in response.text


def test_week_shows_unconfigured_availability_ambiguous_message_and_links():
    report = _week_report()
    report.days[0].workouts = [WeekWorkout(1, None, "Plan", "running", "uncertain", None, "ambiguous", [])]
    with _week_client(report) as client:
        week_response = client.get("/week")
        today_response = client.get("/")
    assert "Brak zadeklarowanej dostępności" in week_response.text
    assert "Nie można jednoznacznie przypisać wykonania." in week_response.text
    assert 'href="/"' in week_response.text
    assert 'href="/week"' in today_response.text
