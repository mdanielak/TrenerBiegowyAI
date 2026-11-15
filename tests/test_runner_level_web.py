# -*- coding: utf-8 -*-
"""Poziom biegacza na Stronie głównej i w Ustawieniach."""
import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from services.data_extract import SnapshotReadResult, SnapshotStatus
from services.runner_level import current_runner
from tests.test_api import _report

pytestmark = pytest.mark.usefixtures("testclient_sockets")

REASON = "W ostatnich 4 tygodniach biegasz średnio 3,5 razy w tygodniu, a najdłuższy bieg trwał 55 min."
PROMOTED = {"level": "regularny", "level_auto": "regularny", "level_changed": "up", "level_override": None,
            "level_since": "2026-09-28", "level_reason": REASON, "returning": False}


def _client(runner, saved=None, tmp_path=None):
    saved = {} if saved is None else saved
    app = create_app(report_provider=lambda: _report(), profile_provider=lambda: {"name": "Ala", "target_race": "10 km"},
                     profile_updater=lambda **fields: saved.update(fields) or saved,
                     availability_provider=lambda: {}, runner_provider=lambda: runner,
                     journal_path=(tmp_path / "journal.jsonl") if tmp_path else None)
    return TestClient(app)


def _token(page):
    return re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)


def test_home_shows_the_level_change_only_when_there_is_one(tmp_path):
    page = _client(PROMOTED, tmp_path=tmp_path).get("/")
    assert "Trener zmienił Twój poziom" in page.text and REASON in page.text
    quiet = _client(dict(PROMOTED, level_changed=None), tmp_path=tmp_path).get("/")
    assert "Trener zmienił Twój poziom" not in quiet.text
    missing = _client(None, tmp_path=tmp_path).get("/")
    assert missing.status_code == 200 and "Trener zmienił Twój poziom" not in missing.text


def test_settings_show_the_level_and_save_a_manual_choice(tmp_path):
    saved = {}
    client = _client(PROMOTED, saved, tmp_path)
    page = client.get("/settings")
    assert 'id="level"' in page.text and "regularny" in page.text and REASON in page.text
    assert "28 września" in page.text
    token = _token(page.text)

    chosen = client.post("/settings/level", headers={"Origin": "http://testserver"}, data={"csrf_token": token, "level_override": "zaawansowany"},
                         follow_redirects=False)
    assert chosen.status_code == 303 and chosen.headers["location"] == "/settings#level"
    assert saved["level_override"] == "zaawansowany"
    auto = client.post("/settings/level", headers={"Origin": "http://testserver"}, data={"csrf_token": token, "level_override": ""}, follow_redirects=False)
    assert auto.status_code == 303 and saved["level_override"] == ""
    wrong = client.post("/settings/level", headers={"Origin": "http://testserver"}, data={"csrf_token": token, "level_override": "xyz"})
    assert wrong.status_code == 400 and "Wybierz jeden z poziomów." in wrong.text
    forged = client.post("/settings/level", headers={"Origin": "http://testserver"}, data={"csrf_token": "zly", "level_override": "regularny"},
                         follow_redirects=False)
    assert forged.status_code in (400, 403) and saved["level_override"] == ""


def test_settings_work_without_watch_data(tmp_path):
    page = _client(None, tmp_path=tmp_path).get("/settings")
    assert page.status_code == 200 and "Trener zmienił Twój poziom" not in page.text


def test_current_runner_is_none_without_watch_data():
    empty = lambda: SnapshotReadResult(SnapshotStatus.MISSING, None)  # noqa: E731
    assert current_runner(snapshot_provider=empty, profile_provider=lambda: {}, today=date(2026, 11, 4)) is None
    broken = lambda: (_ for _ in ()).throw(OSError("dysk"))  # noqa: E731
    assert current_runner(snapshot_provider=broken, profile_provider=lambda: {}, today=date(2026, 11, 4)) is None
    data = lambda: SnapshotReadResult(SnapshotStatus.FRESH, {"activities": []})  # noqa: E731
    runner = current_runner(snapshot_provider=data, profile_provider=lambda: {}, today=date(2026, 11, 4))
    assert runner["level"] == "poczatkujacy"


def test_settings_explain_a_capped_manual_level(tmp_path):
    capped = dict(PROMOTED, level="regularny", level_auto="poczatkujacy", level_override="zaawansowany")
    page = _client(capped, tmp_path=tmp_path).get("/settings")
    assert "najwyżej o jeden stopień" in page.text and "(ustawiony ręcznie)" in page.text
