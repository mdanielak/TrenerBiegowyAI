from __future__ import annotations

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




pytestmark = pytest.mark.usefixtures("testclient_sockets")


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
    from api.main import _app_version
    assert response.json() == {"status": "ok", "version": _app_version()}
    assert _app_version() != "unknown"


def test_first_run_without_a_profile_goes_to_connecting_the_watch():
    with _client(_report(status="profile_missing")) as client:
        response = client.get("/", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/setup/garmin"


@pytest.mark.parametrize(("status", "expected_status"), [("snapshot_missing", 404), ("snapshot_invalid", 503)])
def test_dashboard_offers_downloading_data_instead_of_a_terminal_command(status, expected_status):
    with _client(_report(status=status)) as client:
        response = client.get("/")
    assert response.status_code == expected_status
    assert "Pobierz dane z zegarka" in response.text and 'name="fresh" value="1"' in response.text
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
    # Pełna polska nazwa dnia jest dostępna dla czytników ekranu.
    for weekday in ("Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"):
        assert weekday in response.text
    # Widocznie, w wąskiej kolumnie, pokazujemy skrót.
    for short in ("pon", "wt", "śr", "czw", "pt", "sob", "ndz"):
        assert f">{short}</span>" in response.text
    assert response.text.count('role="group"') == 7


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


def test_week_shows_planned_duration_and_zone_in_the_day_block():
    report = _week_report()
    report.days[0].workouts = [WeekWorkout(1, None, "Latwy 40 min - Z2", "running", "planned",
                                            None, "unmatched", [],
                                            planned_duration_min=40, hr_zone="Z2")]
    with _week_client(report) as client:
        response = client.get("/week")
    assert "40 min" in response.text
    assert 'class="zone-chip z2"' in response.text


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
        store.mark_running(store.submit("unknown", {}).id)
        unknown = store.mark_abandoned_running_as_unknown()[0]
        unknown_response = client.get(f"/jobs/{unknown.id}")
    assert "Zadanie przyjęte, za chwilę się zacznie." in accepted.text and "w kolejce" in accepted.text
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
        client.post("/actions/sync", data={"csrf_token": token},
                    headers={"Origin": "http://testserver"}, follow_redirects=False)
        assert failed.wait(timeout=5)
        app.state.job_executor.shutdown(wait=True)
        job = JobStore(tmp_path / "jobs").list_jobs().jobs[0]
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


def _analysis_readiness(**overrides):
    values = _readiness()
    values["details"] = [
        {"metric": "RHR", "status": "OK", "message": "RHR 48 w normie"},
        {"metric": "HRV", "status": "WARN", "message": "HRV niezrównoważone"},
        {"metric": "Sleep", "status": "FAIL", "message": "Słaby sen 42"},
        {"metric": "Stress", "status": "UNKNOWN", "message": "Brak danych o stresie"},
    ]
    values.update(overrides)
    return values


def _analysis_client(readiness=None, **report_overrides):
    report = _report(readiness=readiness or _analysis_readiness(), **report_overrides)
    return TestClient(create_app(report_provider=lambda: report))


def test_analysis_renders_every_metric_with_status_and_message():
    with _analysis_client() as client:
        response = client.get("/analysis")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    for label in ("Tętno spoczynkowe", "Zmienność tętna", "Sen", "Stres"):
        assert label in response.text
    for message in ("RHR 48 w normie", "HRV niezrównoważone", "Słaby sen 42", "Brak danych o stresie"):
        assert message in response.text
    assert 'class="pill ok"' in response.text
    assert 'class="pill warn"' in response.text
    assert 'class="pill bad"' in response.text


def test_analysis_maps_unknown_status_to_neutral_pill():
    with _analysis_client() as client:
        response = client.get("/analysis")
    assert 'class="pill neutral"' in response.text
    assert "brak danych" in response.text


def test_analysis_shows_coverage_and_confidence():
    readiness = _analysis_readiness(
        available_metrics=["sleep", "rhr"], missing_metrics=["hrv", "stress"],
        confidence="medium", raw_score=5.0, available_max_score=6.0,
    )
    with _analysis_client(readiness) as client:
        response = client.get("/analysis")
    assert "z 4" in response.text
    assert "Średnia" in response.text
    assert "z 6" in response.text


def test_analysis_shows_dash_for_missing_measurements_without_leaking_none():
    readiness = _analysis_readiness(
        rhr=None, hrv_last=None, hrv_baseline="None-None", hrv_status=None,
        sleep_score_val=None, sleep_total=None, stress=None,
    )
    with _analysis_client(readiness) as client:
        response = client.get("/analysis")
    assert response.status_code == 200
    assert "—" in response.text
    assert "None" not in response.text


def test_analysis_escapes_metric_message():
    readiness = _analysis_readiness(details=[
        {"metric": "RHR", "status": "OK", "message": "<script>alert(1)</script>"},
    ])
    with _analysis_client(readiness) as client:
        response = client.get("/analysis")
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;" in response.text


def test_analysis_marks_navigation_entry_as_current():
    with _analysis_client() as client:
        response = client.get("/analysis")
    assert 'href="/analysis" aria-current="page"' in response.text


def test_analysis_reports_missing_snapshot_as_not_found():
    report = _report(status="snapshot_missing", readiness=None)
    with TestClient(create_app(report_provider=lambda: report)) as client:
        response = client.get("/analysis")
    assert response.status_code == 404
    assert response.headers["cache-control"] == "no-store"


def _profile(**overrides):
    values = {
        "name": "Michał",
        "age": 38,
        "weight_kg": 74,
        "height_cm": 180,
        "device": "Garmin Fenix 7S",
        "hr_max": 192,
        "hr_rest": 47,
        "lactate_threshold_hr": 170,
        "vo2max_running": 49,
        "hr_zones": "Z1 96-121, Z2 122-136, Z3 137-154, Z4 155-172, Z5 173-192",
        "hr_zones_source": "Garmin Connect — dane profilu",
        "hr_zone_floors": {"z1": 96, "z2": 122, "z3": 137, "z4": 155, "z5": 173},
        "target_race": "Półmaraton",
        "target_date": "2027-04-18",
        "target_time": "1:45:00",
        "target_hm": "1:45:00",
        "current_hm_record": "1:52:30",
        "training_frequency": 4,
    }
    values.update(overrides)
    return values


def _settings_client(profile=None, provider=None):
    return TestClient(create_app(report_provider=lambda: _report(),
                                 profile_provider=provider or (lambda: _profile() if profile is None else profile)))


def test_ai_settings_form_saves_file_without_exposing_key(tmp_path):
    path = tmp_path / ".env"
    path.write_text('AI_API_KEY=old-secret\nGARMIN_PASSWORD=untouched\n')
    app = create_app(profile_provider=lambda: {}, ai_env_path=path)
    with TestClient(app) as client:
        page = client.get('/settings/ai')
        assert 'old-secret' not in page.text
        assert 'untouched' not in page.text
        assert str(path.resolve()) in page.text
        assert page.headers['cache-control'] == 'no-store'
        token = re.search(r'name="csrf_token" value="([^"]+)"', page.text)[1]
        response = client.post('/settings/ai', data={
            'csrf_token': token, 'base_url': 'http://localhost:11434/v1',
            'model': 'local-model', 'api_key': 'new-secret', 'export_enabled': 'true',
        }, headers={'Origin': 'http://testserver'})
        assert response.status_code == 200
        assert 'Zapisano. Ustawienia działają od razu' in response.text
        assert 'new-secret' not in response.text
        from trainer.env_file import read_env_file
        values = read_env_file(path)
        assert values['AI_API_KEY'] == 'new-secret'
        assert values['AI_DATA_EXPORT_ENABLED'] == 'true'
        assert values['GARMIN_PASSWORD'] == 'untouched'


@pytest.mark.parametrize('origin,valid_token', [('', True), ('http://evil.example', True), ('http://testserver', False)])
def test_ai_settings_rejects_csrf(tmp_path, origin, valid_token):
    path = tmp_path / '.env'
    path.write_text('AI_API_KEY=secret\n')
    with TestClient(create_app(profile_provider=lambda: {}, ai_env_path=path)) as client:
        page = client.get('/settings/ai')
        token = re.search(r'name="csrf_token" value="([^"]+)"', page.text)[1]
        response = client.post('/settings/ai', data={
            'csrf_token': token if valid_token else 'bad', 'api_key': 'replacement',
        }, headers={'Origin': origin})
        assert response.status_code == 403
        assert path.read_text() == 'AI_API_KEY=secret\n'


def test_ai_settings_available_without_profile_and_invalid_input_is_safe(tmp_path):
    def missing():
        raise FileNotFoundError
    path = tmp_path / '.env'
    with TestClient(create_app(profile_provider=missing, ai_env_path=path)) as client:
        page = client.get('/settings/ai')
        assert 'action="/settings/ai"' in page.text
        token = re.search(r'name="csrf_token" value="([^"]+)"', page.text)[1]
        response = client.post('/settings/ai', data={
            'csrf_token': token, 'base_url': 'javascript:bad', 'model': 'test', 'api_key': 'secret-input',
        }, headers={'Origin': 'http://testserver'})
        assert response.status_code == 400
        assert 'secret-input' not in response.text
        assert not path.exists()


def test_settings_links_to_ai_subpage_without_form(tmp_path):
    with TestClient(create_app(profile_provider=lambda: {}, ai_env_path=tmp_path / '.env')) as client:
        page = client.get('/settings')
        assert 'href="/settings/ai"' in page.text
        assert 'name="api_key"' not in page.text
        assert 'AI_BASE_URL' not in page.text
        subpage = client.get('/settings/ai')
        assert subpage.status_code == 200
        assert 'Testuj połączenie' in subpage.text
        assert 'href="/settings"' in subpage.text


@pytest.mark.parametrize('key', ['', 'new-key'])
@pytest.mark.parametrize('base_url', ['https://api.example/v1', 'https://api.example/v2'])
def test_ai_connection_uses_form_and_never_saves(tmp_path, monkeypatch, key, base_url):
    path = tmp_path / '.env'
    original = 'AI_BASE_URL=https://api.example/v1\nAI_API_KEY=saved-key\nAI_MODEL=old\n'
    path.write_text(original)
    calls = []
    monkeypatch.setattr('api.main.check_connection', lambda **kw: calls.append(kw))
    with TestClient(create_app(ai_env_path=path, lock_directory=tmp_path)) as client:
        page = client.get('/settings/ai')
        token = re.search(r'name="csrf_token" value="([^"]+)"', page.text)[1]
        response = client.post('/settings/ai/test', data={
            'csrf_token': token, 'base_url': base_url,
            'model': 'unsaved-model', 'api_key': key,
        }, headers={'Origin': 'http://testserver'})
        assert response.status_code == 200
        assert 'Połączenie działa' in response.text
        assert 'value="unsaved-model"' in response.text
        assert 'saved-key' not in response.text
        assert 'new-key' not in response.text
        assert response.headers['cache-control'] == 'no-store'
    assert calls == [dict(base_url=base_url, api_key=key or 'saved-key', model='unsaved-model')]
    assert path.read_text() == original


@pytest.mark.parametrize('case,status', [('csrf', 403), ('url', 400), ('clear', 400), ('model', 400)])
def test_ai_connection_rejects_unsafe_requests_without_calling_provider(tmp_path, monkeypatch, case, status):
    path = tmp_path / '.env'
    path.write_text('AI_BASE_URL=https://api.example/v1\nAI_API_KEY=saved-key\n')
    calls = []
    monkeypatch.setattr('api.main.check_connection', lambda **kw: calls.append(kw))
    with TestClient(create_app(ai_env_path=path, lock_directory=tmp_path)) as client:
        page = client.get('/settings/ai')
        token = re.search(r'name="csrf_token" value="([^"]+)"', page.text)[1]
        data = dict(csrf_token=token, base_url='https://api.example/v1', model='model')
        if case == 'csrf':
            data['csrf_token'] = 'bad'
        elif case == 'url':
            data['base_url'] = 'https://different.example/v1'
        elif case == 'clear':
            data['clear_key'] = 'true'
        else:
            data['model'] = ''
        response = client.post('/settings/ai/test', data=data, headers={'Origin': 'http://testserver'})
        assert response.status_code == status
        assert 'saved-key' not in response.text
    assert not calls


def test_ai_connection_failure_preserves_nonsecret_form(tmp_path, monkeypatch):
    from ai.connection_test import AIConnectionTestError
    def fail(**kw):
        raise AIConnectionTestError('API odrzuciło klucz.')
    monkeypatch.setattr('api.main.check_connection', fail)
    path = tmp_path / '.env'
    with TestClient(create_app(ai_env_path=path, lock_directory=tmp_path)) as client:
        page = client.get('/settings/ai')
        token = re.search(r'name="csrf_token" value="([^"]+)"', page.text)[1]
        response = client.post('/settings/ai/test', data={
            'csrf_token': token, 'base_url': 'https://new.example/v1',
            'model': 'new-model', 'api_key': 'secret-new-key', 'export_enabled': 'true',
        }, headers={'Origin': 'http://testserver'})
        assert response.status_code == 502
        assert 'API odrzuciło klucz.' in response.text
        assert 'value="new-model"' in response.text
        assert 'secret-new-key' not in response.text
        assert 'Wpisz go ponownie' in response.text
    assert not path.exists()


def test_settings_renders_profile_values_and_zones():
    with _settings_client() as client:
        response = client.get("/settings")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "Michał" in response.text
    assert "Garmin Fenix 7S" in response.text
    assert "192" in response.text
    assert "Strefa Z1" in response.text
    assert "96–121" in response.text
    assert "Strefa Z5" in response.text
    assert "173–192" in response.text
    assert "Garmin Connect — dane profilu" in response.text


def test_settings_shows_dash_for_missing_fields():
    with _settings_client(profile={"name": "Michał"}) as client:
        response = client.get("/settings")
    assert response.status_code == 200
    assert "—" in response.text
    assert "Nie zapisano jeszcze stref tętna" in response.text


def test_settings_falls_back_to_zone_floors_when_summary_missing():
    with _settings_client(profile={"hr_zone_floors": {"z1": 96, "z2": 122}}) as client:
        response = client.get("/settings")
    assert "Strefa Z1" in response.text
    assert "od 96" in response.text
    assert "Strefa Z3" not in response.text


def test_settings_escapes_profile_values():
    with _settings_client(profile=_profile(name="<script>alert(1)</script>")) as client:
        response = client.get("/settings")
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;" in response.text


def test_settings_reports_missing_profile_with_setup_command():
    def missing():
        raise FileNotFoundError("Nie znaleziono lokalnego profilu")

    with _settings_client(provider=missing) as client:
        response = client.get("/settings")
    assert response.status_code == 404
    assert "python -m trainer setup" in response.text
    assert response.headers["cache-control"] == "no-store"


def test_settings_reports_unreadable_profile_as_unavailable():
    def broken():
        raise ValueError("uszkodzony plik")

    with _settings_client(provider=broken) as client:
        response = client.get("/settings")
    assert response.status_code == 503
    assert "Nie można odczytać lokalnego profilu biegacza." in response.text


def test_settings_marks_navigation_entry_as_current():
    with _settings_client() as client:
        response = client.get("/settings")
    assert 'href="/settings" aria-current="page"' in response.text


def test_settings_shows_integrations_card_below_the_page_title():
    with _settings_client() as client:
        response = client.get("/settings")
    assert response.text.index("<h1>Ustawienia</h1>") < response.text.index("<h2>Integracje</h2>")


def _execution(**overrides):
    values = {
        "happened": True,
        "match_method": "id",
        "certain": True,
        "activity_id": 42,
        "distance_km": 6.4,
        "duration_min": 40,
        "avg_hr": 128,
        "max_hr": 141,
        "pace": "6:15",
        "review_key": "2026-10-02:1716765035",
    }
    values.update(overrides)
    return values


_PLANNED = {"name": "6 min rozgrzewki + 34 min Z2",
            "spec": {"kind": "hr_zone_run", "duration_min": 40, "zone_number": 2}}


def _workout_client(execution=None, review=None, profile=None, planned=None):
    report = _report(planned=planned if planned is not None else _PLANNED, execution=execution)
    return TestClient(create_app(
        report_provider=lambda: report,
        profile_provider=(lambda: profile) if profile is not None else (lambda: _profile()),
        review_loader=lambda **kwargs: review,
    ))


def test_dashboard_workout_section_reports_execution_and_local_score():
    with _workout_client(execution=_execution()) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "Trening na dziś" in response.text
    assert "Znaleziono wykonanie" in response.text
    assert "40 min w planie" in response.text
    assert "cel Z2 (122–136 bpm)" in response.text
    assert "Zgodność z planem" in response.text
    assert "Dopasowanie do formy" in response.text
    assert "Pewność oceny: wysoka." in response.text
    assert "bez udziału AI" in response.text


def test_dashboard_workout_section_offers_review_when_comment_is_missing():
    with _workout_client(execution=_execution()) as client:
        response = client.get("/")
    assert "Oceń mój trening" in response.text
    assert 'action="/actions/review"' in response.text
    assert 'name="review_key" value="2026-10-02:1716765035"' in response.text


def test_dashboard_workout_section_shows_saved_comment_without_button():
    review = {"review_key": "2026-10-02:1716765035",
              "score": {"zgodnosc_z_planem": 10},
              "comment": "Bieg trzymał dolną część drugiej strefy. Utrzymaj ten spokój do niedzieli."}
    with _workout_client(execution=_execution(), review=review) as client:
        response = client.get("/")
    assert "Komentarz trenera" in response.text
    assert "Utrzymaj ten spokój do niedzieli." in response.text
    assert "Oceń mój trening" not in response.text


def test_dashboard_workout_section_escapes_saved_comment():
    review = {"comment": "<script>alert(1)</script>"}
    with _workout_client(execution=_execution(), review=review) as client:
        response = client.get("/")
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;" in response.text


def test_dashboard_workout_section_waits_for_sync_before_the_training():
    with _workout_client(execution=_execution(happened=False, match_method="unmatched",
                                              certain=False, activity_id=None, distance_km=None,
                                              duration_min=None, avg_hr=None, max_hr=None)) as client:
        response = client.get("/")
    assert "Do zrobienia" in response.text
    assert "nie ma dziś aktywności" not in response.text
    assert "Brak wykonania" not in response.text
    assert "Zgodność z planem" not in response.text
    assert "Oceń mój trening" not in response.text


def test_dashboard_workout_section_warns_about_heuristic_match():
    with _workout_client(execution=_execution(match_method="heuristic", certain=False)) as client:
        response = client.get("/")
    assert "Wykonanie dopasowano po czasie i dystansie" in response.text


def test_dashboard_workout_section_without_plan_is_empty():
    with _workout_client(execution=None, planned=None) as client:
        response = client.get("/")
    assert "Na dziś nie ma zapisanego treningu." in response.text
    assert "Oceń mój trening" not in response.text


def test_dashboard_workout_section_skips_score_without_profile():
    def broken():
        raise FileNotFoundError("brak profilu")

    report = _report(planned=_PLANNED, execution=_execution())
    app = create_app(report_provider=lambda: report, profile_provider=broken,
                     review_loader=lambda **kwargs: None)
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "Nie można policzyć punktów bez lokalnego profilu biegacza." in response.text
    assert "Zgodność z planem" not in response.text


def _review_app(tmp_path, operation):
    report = _report(planned=_PLANNED, execution=_execution())
    return create_app(report_provider=lambda: report, profile_provider=lambda: _profile(),
                      review_loader=lambda **kwargs: None, review_operation=operation,
                      job_store=JobStore(tmp_path / "jobs"), lock_directory=tmp_path / "locks")


def test_review_action_uses_csrf_and_runs_operation(tmp_path):
    seen = []
    with TestClient(_review_app(tmp_path, lambda *, review_key: seen.append(review_key))) as client:
        token = _csrf(client)
        response = client.post("/actions/review", data={"csrf_token": token,
                                                       "review_key": "2026-10-02:1716765035"},
                               headers={"Origin": "http://testserver"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert seen == ["2026-10-02:1716765035"]


def test_review_action_rejects_invalid_csrf_without_running_operation(tmp_path):
    seen = []
    with TestClient(_review_app(tmp_path, lambda *, review_key: seen.append(review_key))) as client:
        _csrf(client)
        response = client.post("/actions/review", data={"csrf_token": "podrobiony",
                                                       "review_key": "2026-10-02:1716765035"},
                               headers={"Origin": "http://testserver"}, follow_redirects=False)
    assert response.status_code == 403
    assert seen == []


def test_review_action_rejects_missing_review_key(tmp_path):
    seen = []
    with TestClient(_review_app(tmp_path, lambda *, review_key: seen.append(review_key))) as client:
        token = _csrf(client)
        response = client.post("/actions/review", data={"csrf_token": token, "review_key": ""},
                               headers={"Origin": "http://testserver"}, follow_redirects=False)
    assert response.status_code == 403
    assert seen == []


def test_review_action_failure_does_not_render_exception_text(tmp_path):
    def boom(*, review_key):
        raise RuntimeError("klucz-api-w-tresci-bledu")

    store = JobStore(tmp_path / "jobs")
    report = _report(planned=_PLANNED, execution=_execution())
    app = create_app(report_provider=lambda: report, profile_provider=lambda: _profile(),
                     review_loader=lambda **kwargs: None, review_operation=boom,
                     job_store=store, lock_directory=tmp_path / "locks")
    with TestClient(app) as client:
        token = _csrf(client)
        client.post("/actions/review", data={"csrf_token": token,
                                             "review_key": "2026-10-02:1716765035"},
                    headers={"Origin": "http://testserver"}, follow_redirects=False)
        page = client.get("/")
    assert "klucz-api-w-tresci-bledu" not in page.text


def test_asset_route_serves_allowed_png_with_cache_header():
    with _client(_report()) as client:
        response = client.get("/assets/01_navigation/home.png")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "public, max-age=86400"
    assert len(response.content) > 0
    assert response.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_asset_route_rejects_category_outside_whitelist():
    with _client(_report()) as client:
        response = client.get("/assets/05_ui_charts/readiness_ring.png")
    assert response.status_code == 404


def test_asset_route_rejects_unknown_file():
    with _client(_report()) as client:
        response = client.get("/assets/01_navigation/nie-ma-takiego.png")
    assert response.status_code == 404


def test_asset_route_is_case_sensitive():
    with _client(_report()) as client:
        response = client.get("/assets/01_navigation/HOME.PNG")
    assert response.status_code == 404


def test_asset_route_rejects_encoded_path_traversal():
    with _client(_report()) as client:
        response = client.get("/assets/01_navigation/%2e%2e%2f%2e%2e%2fapi%2fmain.py")
    assert response.status_code == 404


def test_asset_route_does_not_leak_absolute_paths_in_error():
    with _client(_report()) as client:
        response = client.get("/assets/01_navigation/brak.png")
    assert response.status_code == 404
    assert "I:" not in response.text
    assert "trener_biegowy_ai_assets" not in response.text


def test_every_asset_referenced_by_templates_is_served():
    import pathlib

    refs = set()
    for template in pathlib.Path("templates").glob("*.html"):
        refs |= set(re.findall(r"/assets/([^\"']+)", template.read_text(encoding="utf-8")))
    literal = sorted(reference for reference in refs if "{{" not in reference)
    assert literal, "szablony nie odwoluja sie do zadnego obrazka"
    with _client(_report()) as client:
        missing = [r for r in literal if client.get(f"/assets/{r}").status_code != 200]
    assert missing == []


def test_static_css_is_served():
    with _client(_report()) as client:
        response = client.get("/static/css/styles.css")
    assert response.status_code == 200
    assert "color-scheme" in response.text


def test_dashboard_lists_the_training_steps_and_other_watch_workouts_before_training():
    report = _report(planned={"name": "Łatwy 40 min – Z2", "spec": {
        "kind": "hr_zone_run", "duration_min": 40, "zone_number": 2, "warmup_min": 6,
        "warmup_pace_faster": "7:00", "warmup_pace_slower": "8:30"}},
        execution=_execution(happened=False, match_method="unmatched", certain=False, activity_id=None,
                             distance_km=None, duration_min=None, avg_hr=None, max_hr=None),
        other_planned=["Tempo 40 min – 3×6 min"],
        plan_workout={"name": "Łatwy 40 min – Z2", "type": "easy", "description": "Spokojnie, bez akcentu.",
                      "notes": "Zostaw rezerwę.", "distance_km": 5.3})
    with TestClient(create_app(report_provider=lambda: report, profile_provider=lambda: _profile(),
                               review_loader=lambda **kwargs: None)) as client:
        page = client.get("/").text

    assert "Rozgrzewka" in page and "6 min" in page and "tempo 7:00–8:30 /km · bez alarmu tętna" in page
    assert "Bieg w strefie" in page and "34 min" in page
    assert "Jak biec:</span> Spokojnie, bez akcentu." in page and "Uwagi trenera:</span> Zostaw rezerwę." in page
    assert "Na zegarku na dziś jest też: Tempo 40 min – 3×6 min" in page


def test_dashboard_hides_the_steps_after_the_training():
    with _workout_client(execution=_execution()) as client:
        page = client.get("/").text
    assert 'class="workout-steps"' not in page
