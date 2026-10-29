# -*- coding: utf-8 -*-
"""Pasek postępu synchronizacji: etapy, szacunek z poprzednich przebiegów i widok."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from services.actions import run_sync_job, synchronize_data
from services.jobs import JobStore
from services.sync_progress import SyncProgress, progress_view
from tests.test_api import _report

pytestmark = pytest.mark.usefixtures("testclient_sockets")

START = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)


class _Clock:
    def __init__(self):
        self.now = START

    def __call__(self):
        return self.now


def test_bar_follows_stages_and_stops_short_of_the_end_of_a_slow_stage(tmp_path):
    clock = _Clock()
    progress = SyncProgress(tmp_path, "job", clock=clock)

    assert progress_view(tmp_path, "job", START) is None
    progress.stage("garmin")
    clock.now += timedelta(seconds=3)
    progress.stage("today")
    view = progress_view(tmp_path, "job", clock.now + timedelta(seconds=10))
    assert (view["step"], view["steps"], view["label"]) == (2, 4, "Pobieranie dzisiejszych danych")
    assert view["percent"] == 5 + int(15 * 10 / 20) and view["elapsed"] == "10 s"

    progress.stage("history")
    late = progress_view(tmp_path, "job", clock.now + timedelta(hours=1))
    assert late["percent"] == 5 + 15 + int(70 * 0.9) and late["elapsed"] == "60 min 0 s"


def test_successful_runs_teach_the_estimate_and_clean_up(tmp_path):
    clock = _Clock()
    progress = SyncProgress(tmp_path, "first", clock=clock)
    progress.stage("history")
    clock.now += timedelta(seconds=30)
    progress.finish(succeeded=True)
    assert not (tmp_path / "progress" / "first.json").exists()

    second = SyncProgress(tmp_path, "second", clock=clock)
    second.stage("history")
    view = progress_view(tmp_path, "second", clock.now + timedelta(seconds=15))
    assert view["percent"] == 5 + 15 + 35  # połowa z poznanych 30 s, a nie z domyślnych 90 s


def test_full_sync_skips_todays_download_and_uses_a_longer_default(tmp_path):
    progress = SyncProgress(tmp_path, "job", fresh=True, clock=lambda: START)
    progress.stage("history")
    view = progress_view(tmp_path, "job", START + timedelta(minutes=10))
    assert view["step"] == 3 and view["percent"] == 20 + 35


def test_sync_reports_every_stage_in_order(monkeypatch, tmp_path):
    from services import data_extract

    stages = []
    monkeypatch.setattr(data_extract, "ensure_garmindb_config", lambda email: False)
    monkeypatch.setattr(data_extract, "ensure_token", lambda: object())
    monkeypatch.setattr(data_extract, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(data_extract, "_find_python", lambda: "python")
    monkeypatch.setattr(data_extract, "_find_garmindb_cli", lambda: "garmindb_cli.py")
    monkeypatch.setattr(data_extract, "download_today", lambda cwd=None: stages.append("download") or True)
    monkeypatch.setattr(data_extract.subprocess, "run", lambda *a, **k: stages.append("cli") or MagicMock(returncode=0))
    monkeypatch.setattr(data_extract, "extract", lambda: {"timestamp": "t"})
    monkeypatch.setattr(data_extract, "save_json", lambda data: None)

    data_extract.synchronize_and_save(progress=stages.append)

    assert stages == ["garmin", "today", "download", "history", "cli", "extract"]


def test_sync_job_passes_progress_and_removes_it_afterwards(tmp_path, monkeypatch):
    store = JobStore(tmp_path / "jobs")
    job = store.submit("sync", {})
    seen = []

    def fake(*, fresh=False, progress=None):
        progress("history")
        seen.append(progress_view(store.directory, job.id))

    monkeypatch.setattr("services.data_extract.synchronize_and_save", fake)
    run_sync_job(store=store, job_id=job.id, operation=synchronize_data, lock_directory=tmp_path)

    assert seen[0]["label"] == "Pobieranie i import aktywności i pomiarów"
    assert progress_view(store.directory, job.id) is None
    assert [j.id for j in store.list_jobs().jobs] == [job.id]  # pliki postępu nie udają zadań


def test_dashboard_and_job_page_show_the_bar(tmp_path):
    store = JobStore(tmp_path / "jobs")
    with TestClient(create_app(report_provider=lambda: _report(), job_store=store)) as client:
        # Po starcie, bo start aplikacji oznacza przerwane zadania jako nieznane.
        job = store.submit("sync", {})
        store.mark_running(job.id)
        SyncProgress(store.directory, job.id).stage("today")
        dashboard = client.get("/").text
        job_page = client.get(f"/jobs/{job.id}").text
    for page in (dashboard, job_page):
        assert '<progress max="100" value="' in page
        assert "Krok 2 z 4: Pobieranie dzisiejszych danych" in page


def test_bar_is_indeterminate_before_the_first_stage(tmp_path):
    store = JobStore(tmp_path / "jobs")
    with TestClient(create_app(report_provider=lambda: _report(), job_store=store)) as client:
        store.submit("sync", {})
        page = client.get("/").text
    assert '<progress aria-label="Postęp synchronizacji"></progress>' in page
    assert "Przygotowanie synchronizacji…" in page
