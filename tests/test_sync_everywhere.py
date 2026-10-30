# -*- coding: utf-8 -*-
"""Trwające pobieranie danych widać na każdej stronie, a strony bez danych nie proponują startu od nowa."""
import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from services.data_extract import SnapshotReadResult, SnapshotStatus
from services.jobs import JobStore
from services.sync_progress import SyncProgress
from tests.test_api import _report

pytestmark = pytest.mark.usefixtures("testclient_sockets")
START_BUTTON = 'action="/actions/sync"'


def _app(tmp_path, store):
    return create_app(report_provider=lambda: _report(status="snapshot_missing"), job_store=store,
                      ai_env_path=tmp_path / "ai.env", garmin_token_check=lambda: True,
                      snapshot_provider=lambda: SnapshotReadResult(status=SnapshotStatus.MISSING, data=None))


def test_a_running_first_download_is_visible_everywhere_and_never_offered_again(tmp_path):
    store = JobStore(tmp_path / "jobs")
    with TestClient(_app(tmp_path, store)) as client:
        job = store.submit("sync", {"fresh": True})  # po starcie: start porzuca zadania z poprzedniego uruchomienia
        store.mark_running(job.id)
        SyncProgress(store.directory, job.id, fresh=True).stage("history")

        other = client.get("/settings/ai").text
        assert "Pobieranie danych z zegarka…" in other and f'href="/jobs/{job.id}"' in other

        home = client.get("/").text
        assert "<h1>Pobieranie danych z zegarka</h1>" in home and "Brakuje lokalnego snapshotu" not in home
        assert START_BUTTON not in home

        setup = client.get("/setup/garmin").text
        assert "trwa pobieranie danych z zegarka" in setup and START_BUTTON not in setup

        store.mark_succeeded(job.id)
        after = client.get("/settings/ai").text
        setup_after = client.get("/setup/garmin").text
    assert "Pobieranie danych z zegarka…" not in after
    assert START_BUTTON in setup_after  # nic nie trwa, a danych brak: przycisk wraca
