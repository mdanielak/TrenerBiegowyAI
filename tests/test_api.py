from __future__ import annotations

import socket

from fastapi.testclient import TestClient
import pytest

from api.main import create_app
from services.data_extract import SnapshotStatus
from services.today import TodayReport


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
