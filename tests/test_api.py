from __future__ import annotations

import socket
import re
from datetime import datetime, timedelta, timezone
from threading import Event

from fastapi.testclient import TestClient
import pytest

from api.main import _format_sync_time, create_app
from services.data_extract import SnapshotStatus
from services.today import TodayReport
from services.week import DayAvailability, WeekActivity, WeekDayReport, WeekReport, WeekWorkout
from services.jobs import JobStore


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
        "snapshot_timestamp": None,
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


def _action_app(tmp_path, operation=lambda: None, now=None):
    return create_app(report_provider=lambda: _report(), job_store=JobStore(tmp_path / "jobs"),
                      lock_directory=tmp_path / "locks", sync_operation=operation,
                      now_provider=(lambda: now) if now else datetime.now)


def _csrf(client):
    page = client.get("/")
    match = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    if match is None:
        raise RuntimeError("Brak tokenu CSRF w formularzu testowym.")
    return match.group(1)


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
    assert "Piątek, 2 października 2026" in response.text
    for label in ("Sen", "Zmienność tętna", "Tętno spoczynkowe", "Stres"):
        assert label in response.text
    # Każdy brakujący sygnał pokazuje pauzę, a nie zero ani pustą wartość.
    assert response.text.count("—") >= 4
    # Bez wartości nie wolno pokazywać samej jednostki.
    assert "— bpm" not in response.text
    assert 'class="signal-unit"' not in response.text
    assert response.text.count("brak danych") >= 4
    assert response.headers["cache-control"] == "no-store"


def test_dashboard_translates_hrv_status_and_formats_polish_summary():
    report = _report(
        readiness=_readiness(),
        signals={"sleep_score": 85, "hrv_status": "UNBALANCED", "rhr": 48, "stress_avg": 22},
    )
    with _client(report) as client:
        response = client.get("/")
    assert "niezrównoważone" in response.text
    assert "48<span class=\"signal-unit\">bpm</span>" in response.text
    assert "<span class=\"ring-score\">8</span>" in response.text
    assert "<span class=\"ring-max\">z 10</span>" in response.text
    assert "Piątek, 2 października 2026" in response.text
    assert "Dane są aktualne." in response.text
    assert "Realizuj zaplanowany trening spokojnie." in response.text


def test_dashboard_keeps_unknown_hrv_status_raw():
    report = _report(signals={"sleep_score": 85, "hrv_status": "CUSTOM_STATUS", "rhr": 48, "stress_avg": 22})
    with _client(report) as client:
        response = client.get("/")
    assert "CUSTOM_STATUS" in response.text


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


def test_sync_action_uses_csrf_and_redirects_to_dashboard(tmp_path):
    with TestClient(_action_app(tmp_path)) as client:
        token = _csrf(client)
        response = client.post("/actions/sync", data={"csrf_token": token},
                               headers={"Origin": "http://testserver"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"


@pytest.mark.parametrize("token,headers", [
    ("", {"Origin": "http://testserver"}),
    ("wrong", {"Origin": "http://testserver"}),
    ("wrong", {"Origin": "http://evil.example"}),
])
def test_sync_action_rejects_invalid_csrf_without_creating_job(tmp_path, token, headers):
    with TestClient(_action_app(tmp_path)) as client:
        _csrf(client)
        response = client.post("/actions/sync", data={"csrf_token": token}, headers=headers)
    assert response.status_code == 403
    assert response.headers["content-type"].startswith("text/html")
    assert "Nie można potwierdzić, że żądanie pochodzi z tej strony." in response.text
    assert 'href="/">Wróć do widoku dnia</a>' in response.text
    assert '"detail"' not in response.text
    assert JobStore(tmp_path / "jobs").list_jobs().jobs == []


def test_job_page_states_and_refresh_policy(tmp_path):
    store = JobStore(tmp_path / "jobs")
    with TestClient(create_app(report_provider=lambda: _report(), job_store=store,
                               lock_directory=tmp_path / "locks", sync_operation=lambda: None)) as client:
        job = store.submit("sync", {})
        accepted = client.get(f"/jobs/{job.id}")
        running = store.mark_running(job.id)
        running_response = client.get(f"/jobs/{running.id}")
        succeeded = store.mark_succeeded(job.id)
        succeeded_response = client.get(f"/jobs/{succeeded.id}")
        failed_job = store.mark_running(store.submit("other", {}).id)
        failed = store.mark_failed(failed_job.id)
        failed_response = client.get(f"/jobs/{failed.id}")
        unknown_job = store.mark_running(store.submit("unknown", {}).id)
        unknown = store.mark_abandoned_running_as_unknown()[0]
        unknown_response = client.get(f"/jobs/{unknown.id}")
    assert "Zadanie przyjęte, czeka na rozpoczęcie." in accepted.text
    assert 'http-equiv="refresh" content="15"' in accepted.text and 'http-equiv="refresh" content="15"' in running_response.text
    assert "Gotowe. Dane są zaktualizowane." in succeeded_response.text
    assert 'http-equiv="refresh"' not in succeeded_response.text
    assert "Nie udało się. Spróbuj ponownie." in failed_response.text
    assert "Nie wiemy, czy operacja się dokończyła." in unknown_response.text
    assert 'http-equiv="refresh"' not in failed_response.text
    assert 'http-equiv="refresh"' not in unknown_response.text


def test_job_unknown_identifier_is_not_a_file_path(tmp_path):
    with TestClient(_action_app(tmp_path)) as client:
        response = client.get("/jobs/../../outside")
    assert response.status_code == 404


@pytest.mark.parametrize("job_id", ["%2E%2E", "x" * 19, "a" * 20 + "/../x"])
def test_job_rejects_forged_identifiers(tmp_path, job_id):
    with TestClient(_action_app(tmp_path)) as client:
        response = client.get(f"/jobs/{job_id}")
    assert response.status_code == 404


def test_sync_cooldown_is_shown_without_second_job(tmp_path):
    now = datetime.now(timezone.utc)
    store = JobStore(tmp_path / "jobs")
    job = store.mark_running(store.submit("sync", {"fresh": False}, now=now).id, now=now)
    store.mark_succeeded(job.id, now=now)
    with TestClient(create_app(report_provider=lambda: _report(), job_store=store,
                               lock_directory=tmp_path / "locks", sync_operation=lambda: None,
                               now_provider=lambda: now)) as client:
        token = _csrf(client)
        response = client.post("/actions/sync", data={"csrf_token": token},
                               headers={"Origin": "http://testserver"}, follow_redirects=False)
        page = client.get(response.headers["location"])
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert '"detail"' not in response.text
    assert "Dane zsynchronizowano niedawno" in page.text
    assert len(store.list_jobs().jobs) == 1


def test_sync_failure_does_not_render_exception_text(tmp_path):
    failed = Event()

    def fail():
        try:
            raise RuntimeError("ROZPOZNAWALNY_SEKRET")
        finally:
            failed.set()

    app = _action_app(tmp_path, fail)
    with TestClient(app) as client:
        token = _csrf(client)
        response = client.post("/actions/sync", data={"csrf_token": token},
                               headers={"Origin": "http://testserver"}, follow_redirects=False)
        assert failed.wait(timeout=5)
        app.state.job_executor.shutdown(wait=True)
        job = store = JobStore(tmp_path / "jobs").list_jobs().jobs[0]
        page = client.get(f"/jobs/{job.id}")
    assert "Nie udało się. Spróbuj ponownie." in page.text
    assert "ROZPOZNAWALNY_SEKRET" not in page.text


def _sync_job(store, status, now):
    """Zapisz zadanie synchronizacji w zadanym stanie i czasie testowym."""
    job = store.submit("sync", {"fresh": False}, now=now)
    if status == "accepted":
        return job
    job = store.mark_running(job.id, now=now)
    if status == "running":
        return job
    if status == "succeeded":
        return store.mark_succeeded(job.id, now=now)
    if status == "failed":
        return store.mark_failed(job.id, now=now)
    return store.mark_abandoned_running_as_unknown(now=now)[0]


def test_dashboard_shows_running_sync_banner_refresh_and_disabled_button(tmp_path):
    now = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
    store = JobStore(tmp_path / "jobs")
    _sync_job(store, "accepted", now)
    with TestClient(create_app(report_provider=lambda: _report(), job_store=store,
                               now_provider=lambda: now)) as client:
        response = client.get("/")
    assert "Trwa synchronizacja danych. Może potrwać około dwóch minut. Strona odświeży się sama." in response.text
    assert '<meta http-equiv="refresh" content="15">' in response.text
    assert '<button type="submit" disabled>' in response.text


def test_dashboard_quiet_state_has_no_banner_or_refresh(tmp_path):
    with TestClient(_action_app(tmp_path)) as client:
        response = client.get("/")
    assert "Trwa synchronizacja danych" not in response.text
    assert 'http-equiv="refresh"' not in response.text


@pytest.mark.parametrize(
    ("status", "message"),
    [("failed", "Ostatnia synchronizacja się nie udała."),
     ("unknown", "Nie wiemy, czy ostatnia synchronizacja się dokończyła.")],
)
def test_dashboard_shows_recent_problem_with_details_without_refresh(tmp_path, status, message):
    now = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
    store = JobStore(tmp_path / "jobs")
    job = _sync_job(store, status, now - timedelta(minutes=9))
    with TestClient(create_app(report_provider=lambda: _report(), job_store=store,
                               now_provider=lambda: now)) as client:
        response = client.get("/")
    assert message in response.text
    assert f'href="/jobs/{job.id}">Szczegóły</a>' in response.text
    assert 'http-equiv="refresh"' not in response.text


def test_dashboard_hides_old_failed_sync_banner(tmp_path):
    now = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
    store = JobStore(tmp_path / "jobs")
    _sync_job(store, "failed", now - timedelta(minutes=11))
    with TestClient(create_app(report_provider=lambda: _report(), job_store=store,
                               now_provider=lambda: now)) as client:
        response = client.get("/")
    assert "Ostatnia synchronizacja się nie udała." not in response.text


def test_dashboard_shows_cooldown_from_recent_success(tmp_path):
    now = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
    store = JobStore(tmp_path / "jobs")
    _sync_job(store, "succeeded", now - timedelta(seconds=30))
    with TestClient(create_app(report_provider=lambda: _report(), job_store=store,
                               now_provider=lambda: now)) as client:
        response = client.get("/")
    assert "Dane zsynchronizowano niedawno. Odczekaj chwilę przed kolejną próbą." in response.text


@pytest.mark.parametrize(
    ("status", "age", "message"),
    [
        ("succeeded", timedelta(seconds=30), "Dane zsynchronizowano niedawno. Odczekaj chwilę przed kolejną próbą."),
        ("failed", timedelta(minutes=9), "Ostatnia synchronizacja się nie udała."),
        ("unknown", timedelta(minutes=9), "Nie wiemy, czy ostatnia synchronizacja się dokończyła."),
    ],
)
def test_dashboard_uses_utc_jobs_with_naive_local_clock(tmp_path, status, age, message):
    """Rekord UTC musi być świeży dla zegara lokalnego bez informacji o strefie."""
    local_now = datetime(2026, 10, 2, 14, 34)
    job_time_utc = datetime(2026, 10, 2, 12, 34, tzinfo=timezone.utc) - age
    store = JobStore(tmp_path / "jobs")
    _sync_job(store, status, job_time_utc)
    with TestClient(create_app(report_provider=lambda: _report(), job_store=store,
                               now_provider=lambda: local_now)) as client:
        response = client.get("/")
    assert message in response.text


@pytest.mark.parametrize(
    ("status", "age", "message"),
    [
        ("failed", timedelta(minutes=11), "Ostatnia synchronizacja się nie udała."),
        ("succeeded", timedelta(seconds=61), "Dane zsynchronizowano niedawno. Odczekaj chwilę przed kolejną próbą."),
    ],
)
def test_dashboard_respects_utc_job_age_with_naive_local_clock(tmp_path, status, age, message):
    """Granice świeżości zadań pozostają poprawne dla lokalnego zegara naive."""
    local_now = datetime(2026, 10, 2, 14, 34)
    job_time_utc = datetime(2026, 10, 2, 12, 34, tzinfo=timezone.utc) - age
    store = JobStore(tmp_path / "jobs")
    _sync_job(store, status, job_time_utc)
    with TestClient(create_app(report_provider=lambda: _report(), job_store=store,
                               now_provider=lambda: local_now)) as client:
        response = client.get("/")
    assert message not in response.text


def test_sync_conflict_redirects_to_dashboard_banner_without_json(tmp_path):
    started = Event()
    release = Event()

    def operation():
        started.set()
        release.wait(timeout=5)

    with TestClient(_action_app(tmp_path, operation)) as client:
        token = _csrf(client)
        first = client.post("/actions/sync", data={"csrf_token": token},
                            headers={"Origin": "http://testserver"}, follow_redirects=False)
        assert started.wait(timeout=5)
        conflict = client.post("/actions/sync", data={"csrf_token": token},
                               headers={"Origin": "http://testserver"}, follow_redirects=False)
        page = client.get(conflict.headers["location"])
        release.set()
    assert first.status_code == 303
    assert conflict.status_code == 303
    assert conflict.headers["location"] == "/"
    assert '"detail"' not in conflict.text
    assert "Trwa synchronizacja danych. Może potrwać około dwóch minut. Strona odświeży się sama." in page.text


def test_cooldown_redirect_keeps_last_sync_time(tmp_path):
    store = JobStore(tmp_path / "jobs")
    job = store.mark_running(store.submit("sync", {"fresh": False}).id)
    store.mark_succeeded(job.id)
    report = _report(snapshot_timestamp="2026-10-02T09:14:00+00:00")
    with TestClient(create_app(report_provider=lambda: report, job_store=store,
                               lock_directory=tmp_path / "locks", sync_operation=lambda: None)) as client:
        token = _csrf(client)
        response = client.post("/actions/sync", data={"csrf_token": token},
                               headers={"Origin": "http://testserver"}, follow_redirects=False)
        page = client.get(response.headers["location"])
    assert response.status_code == 303
    assert "Zsynchronizowano" in page.text


@pytest.mark.parametrize(
    ("timestamp", "now", "expected"),
    [
        ("2026-10-02T09:14:00+00:00", datetime(2026, 10, 2, 12, tzinfo=timezone.utc), "Zsynchronizowano dziś o"),
        ("2026-10-01T14:15:00+00:00", datetime(2026, 10, 2, 12, tzinfo=timezone.utc), "Zsynchronizowano wczoraj o"),
        ("2026-09-30T14:15:00+00:00", datetime(2026, 10, 2, 12, tzinfo=timezone.utc), "Zsynchronizowano 2 dni temu o"),
        ("2026-09-24T14:15:00+00:00", datetime(2026, 10, 2, 12, tzinfo=timezone.utc), "Zsynchronizowano 24 września o"),
        ("nie-data", datetime(2026, 10, 2, 12, tzinfo=timezone.utc), "Nie wiadomo, kiedy ostatnio synchronizowano dane."),
        (None, datetime(2026, 10, 2, 12, tzinfo=timezone.utc), "Nie wiadomo, kiedy ostatnio synchronizowano dane."),
    ],
)
def test_format_sync_time_uses_human_rules(timestamp, now, expected):
    assert _format_sync_time(timestamp, now).startswith(expected)


def test_format_sync_time_uses_local_calendar_and_timezone():
    local_now = datetime(2026, 10, 3, 0, 10).astimezone()
    timestamp = (local_now - timedelta(minutes=20)).astimezone(timezone.utc).isoformat()
    displayed = _format_sync_time(timestamp, local_now)
    expected_clock = f"{(local_now - timedelta(minutes=20)).hour}:{(local_now - timedelta(minutes=20)).minute:02d}"
    assert displayed == f"Zsynchronizowano wczoraj o {expected_clock}"
    assert not displayed.endswith(f"0{(local_now - timedelta(minutes=20)).hour}:{(local_now - timedelta(minutes=20)).minute:02d}")


def test_get_sync_action_is_not_available(tmp_path):
    store = JobStore(tmp_path / "jobs")
    with TestClient(create_app(report_provider=lambda: _report(), job_store=store,
                               lock_directory=tmp_path / "locks", sync_operation=lambda: None)) as client:
        response = client.get("/actions/sync")
    assert response.status_code == 405
    assert store.list_jobs().jobs == []


def test_running_job_becomes_unknown_at_startup_without_execution(tmp_path):
    store = JobStore(tmp_path / "jobs")
    job = store.mark_running(store.submit("sync", {"fresh": False}).id)
    called = []
    with TestClient(create_app(report_provider=lambda: _report(), job_store=store,
                               lock_directory=tmp_path / "locks", sync_operation=lambda: called.append(True))):
        pass
    assert store.get(job.id).status == "unknown"
    assert called == []


def test_executor_is_shutdown_with_application(tmp_path):
    app = _action_app(tmp_path)
    with TestClient(app):
        executor = app.state.job_executor
    assert executor._shutdown is True


def test_double_submission_reuses_one_job_and_one_execution(tmp_path):
    called = []
    started = Event()
    release = Event()

    def operation():
        called.append(True)
        started.set()
        release.wait(timeout=5)

    with TestClient(_action_app(tmp_path, operation)) as client:
        token = _csrf(client)
        first = client.post("/actions/sync", data={"csrf_token": token},
                            headers={"Origin": "http://testserver"}, follow_redirects=False)
        assert started.wait(timeout=5)
        second = client.post("/actions/sync", data={"csrf_token": token},
                             headers={"Origin": "http://testserver"}, follow_redirects=False)
        release.set()
    assert first.headers["location"] == second.headers["location"]
    assert called == [True]


@pytest.mark.parametrize(
    ("status", "message"),
    [("missing", "Nie znaleziono lokalnego rejestru treningów"),
     ("invalid", "Lokalny rejestr treningów jest nieczytelny")],
)
def test_week_shows_registry_problem_warning(tmp_path, status, message):
    report = _week_report()
    report.registry_status = status
    with _week_client(report) as client:
        response = client.get("/week")
    assert message in response.text


def test_week_hides_registry_problem_warning_when_registry_is_ok():
    with _week_client(_week_report()) as client:
        response = client.get("/week")
    assert "Nie znaleziono lokalnego rejestru treningów" not in response.text
    assert "Lokalny rejestr treningów jest nieczytelny" not in response.text
