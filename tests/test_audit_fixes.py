# -*- coding: utf-8 -*-
"""Poprawki z audytu: obce hosty, kod MFA, wspólna blokada planu, porzucone i stare zadania."""
import inspect
import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from services import actions, garmin_setup
from services.jobs import JobStore
from tests.test_api import _report
from tests.test_garmin_setup import PASSWORD, _factory

pytestmark = pytest.mark.usefixtures("testclient_sockets")


@pytest.mark.parametrize(("host", "status"), [("127.0.0.1:8001", 200), ("localhost:8001", 200),
                                              ("zla.example:8001", 400), ("127.0.0.1.zla.example", 400)])
def test_only_this_computer_may_use_the_app(host, status):
    client = TestClient(create_app(report_provider=lambda: _report()))
    assert client.get("/health", headers={"host": host}).status_code == status


def test_a_typo_in_the_mfa_code_can_be_corrected():
    _, pending = garmin_setup.start_login("ala@example.com", PASSWORD, garmin_factory=_factory(mfa=True))
    with pytest.raises(garmin_setup.GarminSetupError) as typo:
        garmin_setup.complete_mfa(pending, "12345a")
    assert typo.value.restart is False
    assert garmin_setup.complete_mfa(pending, "123456") == "ala@example.com"


def test_a_rejected_mfa_code_sends_back_to_the_password_step(monkeypatch):
    _, pending = garmin_setup.start_login("ala@example.com", PASSWORD,
                                          garmin_factory=_factory(mfa=True, bad_code=True))
    with pytest.raises(garmin_setup.GarminSetupError) as rejected:
        garmin_setup.complete_mfa(pending, "000000")
    assert rejected.value.restart is True

    def reject(pending_id, code):
        raise garmin_setup.GarminSetupError("Kod odrzucony.", restart=True)

    monkeypatch.setattr("services.garmin_setup.complete_mfa", reject)
    client = TestClient(create_app(report_provider=lambda: _report(), garmin_token_check=lambda: False))
    page = client.get("/setup/garmin").text
    token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    response = client.post("/setup/garmin/mfa", data={"csrf_token": token, "pending": "p", "code": "000000"},
                           headers={"Origin": "http://testserver"})
    assert 'type="password"' in response.text  # krok z hasłem, nie bezużyteczne pole na kod


def test_plan_push_and_plan_generation_share_one_lock():
    push = inspect.getsource(actions.run_plan_push_job)
    generate = inspect.getsource(actions.run_plan_job)
    assert 'acquire_lock(name="plan"' in push and 'acquire_lock(name="plan"' in generate


def test_a_queued_job_left_by_a_closed_window_does_not_block_the_button(tmp_path):
    store = JobStore(tmp_path / "jobs")
    store.submit("sync", {})
    with TestClient(create_app(report_provider=lambda: _report(), job_store=store)) as client:
        page = client.get("/").text
    assert "Trwa synchronizacja" not in page and '<button type="submit" disabled>' not in page
    assert store.list_jobs().jobs[0].status == "unknown"


def test_old_finished_jobs_are_removed_at_start(tmp_path):
    store = JobStore(tmp_path / "jobs")
    long_ago = datetime.now(timezone.utc) - timedelta(days=45)
    old = store.submit("sync", {}, now=long_ago)
    store.mark_running(old.id, now=long_ago)
    store.mark_succeeded(old.id, now=long_ago)
    (store.directory / "progress").mkdir()
    (store.directory / "progress" / f"{old.id}.json").write_text("{}", encoding="utf-8")
    recent = store.submit("plan", {})
    store.mark_running(recent.id)
    store.mark_succeeded(recent.id)

    assert store.prune_finished() == 1
    assert [job.id for job in store.list_jobs().jobs] == [recent.id]
    assert not (store.directory / "progress" / f"{old.id}.json").exists()
