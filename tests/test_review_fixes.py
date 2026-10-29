# -*- coding: utf-8 -*-
"""Poprawki z przeglądu aplikacji: przerwa na stronie głównej, teksty bez terminala i po polsku."""
import re

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.views.profile import _display_value
from services.data_extract import SnapshotReadResult, SnapshotStatus
from services.readiness import compute_readiness_breakdown
from tests.test_api import _execution, _profile, _report

pytestmark = pytest.mark.usefixtures("testclient_sockets")

PAUSE = {"start_date": "2026-09-30", "end_date": "2026-10-06", "reason": "Choroba: przeziębienie", "type": "medical"}


def test_active_pause_wins_over_a_workout_planned_before_it():
    report = _report(active_pause=PAUSE, suggestion="medical_rest",
                     execution=_execution(happened=False, activity_id=None))
    page = TestClient(create_app(report_provider=lambda: report)).get("/").text

    assert "Dziś trwa przerwa: Choroba: przeziębienie" in page
    assert "pomiń go" in page and 'href="/plan?week=2026-09-28">Ułóż plan ponownie</a>' in page
    assert '<span class="pill warn">Przerwa</span>' in page and "Do zrobienia" not in page
    assert "Dziś bez treningu." in page


def test_workout_done_during_a_pause_is_still_shown_without_the_pause_notice():
    report = _report(active_pause=PAUSE, execution=_execution())
    page = TestClient(create_app(report_provider=lambda: report)).get("/").text
    assert "Dziś trwa przerwa" not in page and "Znaleziono wykonanie" in page


@pytest.mark.parametrize("path", ["/", "/plan", "/analysis"])
def test_footers_and_labels_are_gender_neutral(path):
    page = TestClient(create_app(report_provider=lambda: _report())).get(path).text
    assert "podejmujesz sam" not in page and "gotowy" not in page


def test_stale_data_points_to_the_sync_button_not_the_terminal():
    page = TestClient(create_app(report_provider=lambda: _report(snapshot_status=SnapshotStatus.STALE))).get("/").text
    assert "Kliknij „Zsynchronizuj dane” u góry strony." in page and "terminalu" not in page


def test_missing_profile_points_to_garmin_setup_first():
    def missing():
        raise FileNotFoundError

    page = TestClient(create_app(report_provider=lambda: _report(), profile_provider=missing)).get("/settings").text
    assert page.index('href="/setup/garmin"') < page.index("python -m trainer setup")


def test_settings_show_connection_state_and_explain_profile_refresh():
    client = TestClient(create_app(report_provider=lambda: _report(), profile_provider=lambda: _profile(),
                                   garmin_token_check=lambda: True))
    page = client.get("/settings").text
    assert "Połączony — profil, strefy tętna i treningi pobierają się z konta." in page
    assert "Odśwież profil i strefy tętna" in page and "python -m trainer profile" not in page


def test_profile_refresh_uses_the_saved_token_and_never_writes_the_email(monkeypatch):
    calls = []
    monkeypatch.setattr("services.garmin_setup.import_profile", lambda *, email: calls.append(email) or {})
    client = TestClient(create_app(report_provider=lambda: _report(), garmin_token_check=lambda: True,
                                   snapshot_provider=lambda: SnapshotReadResult(status=SnapshotStatus.FRESH, data={})))
    page = client.get("/setup/garmin").text
    token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)

    assert client.post("/setup/garmin/profile", data={"csrf_token": "x"},
                       headers={"Origin": "http://testserver"}).status_code == 403
    done = client.post("/setup/garmin/profile", data={"csrf_token": token},
                       headers={"Origin": "http://testserver"}, follow_redirects=False)

    assert calls == [None] and done.headers["location"] == "/setup/garmin?profile=refreshed"
    assert "Pobrano aktualny profil i strefy tętna z Garmina." in client.get(done.headers["location"]).text


def test_old_cli_profile_values_are_shown_in_polish():
    assert _display_value("training_frequency", "5x/week") == "5 razy w tygodniu"
    assert _display_value("training_frequency", "4 treningi w tygodniu") == "4 treningi w tygodniu"
    assert _display_value("target_date", "2027-10-17 (data robocza)") == "17 października 2027 (data robocza)"


def test_readiness_reasons_have_no_english_codes():
    data = {"daily_health": [{"rhr": 53, "stress_avg": 16}], "sleep": [{"score": 85, "total_h": 7}],
            "hrv": [{"status": "LOW", "last_night": 61, "baseline_low": 65, "baseline_high": 79}]}
    messages = " ".join(detail["message"] for detail in compute_readiness_breakdown(data)["details"])
    assert "Tętno spoczynkowe lekko podwyższone (53 bpm)" in messages and "HRV niskie — zwolnij" in messages
    assert "Sen w porządku (ocena 85/100)" in messages
    assert not re.search(r"\b(RHR|LOW|score|baseline)\b", messages)


def test_week_legend_is_gender_neutral():
    page = TestClient(create_app(report_provider=lambda: _report())).get("/week").text
    assert "nie jesteś gotowy" not in page
