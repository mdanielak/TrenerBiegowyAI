# -*- coding: utf-8 -*-
"""Kreator celu i tygodnia."""
import re
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from services import wizard
from tests.test_api import _report

pytestmark = pytest.mark.usefixtures("testclient_sockets")

TODAY = date(2026, 10, 29)
FUTURE = (date.today() + timedelta(days=200)).isoformat()


def test_onboarding_only_without_any_goal_or_decision():
    assert wizard.needs_onboarding({}) is True
    assert wizard.needs_onboarding({"target_race": "półmaraton"}) is False
    assert wizard.needs_onboarding({"onboarding_skipped_at": "2026-10-29T10:00:00"}) is False


def test_prefill_reads_the_existing_profile_and_days():
    values = wizard.prefill({"target_race": "półmaraton", "target_date": "2027-10-17 (robocza)",
                             "target_time": "1:49:00", "current_hm_record": "1:58:30",
                             "training_frequency": "5x/week"},
                            {"sun": {"available": True, "min_minutes": 60, "max_minutes": 90}})

    assert (values["distance"], values["event_date"], values["frequency"]) == ("hm", "2027-10-17", "5")
    assert (values["day_sun"], values["min_sun"], values["max_sun"]) == ("on", "60", "90")
    assert values["day_mon"] == ""


@pytest.mark.parametrize("step, fields, message", [
    ("goal", {"distance": "hm", "event_date": ""}, "Podaj datę"),
    ("goal", {"distance": "hm", "event_date": "2026-01-01"}, "przeszłości"),
    ("goal", {"distance": "other", "event_date": "2027-05-01"}, "jaki to dystans"),
    ("times", {"target_time": "1h49"}, "G:MM:SS"),
    ("week", {"frequency": "5", "day_mon": "on", "min_mon": "30", "max_mon": "60"}, "co najmniej 5 dni"),
    ("week", {"frequency": "1", "day_mon": "on", "min_mon": "90", "max_mon": "60"}, "poniedziałek"),
])
def test_step_validation_messages(step, fields, message):
    with pytest.raises(ValueError, match=message):
        wizard.validate_step(step, fields, today=TODAY)


def test_fitness_goal_needs_no_date_and_times_are_normalised():
    assert wizard.validate_step("goal", {"distance": "fitness"}, today=TODAY)["event_date"] == ""
    assert wizard.validate_step("times", {"target_time": "1:49:00", "record": "49:30"}, today=TODAY) == {
        "target_time": "1:49:00", "record": "49:30"}


def _client(tmp_path, profile, saved, days):
    app = create_app(
        report_provider=lambda: _report(),
        profile_provider=lambda: profile,
        availability_provider=lambda: {},
        profile_updater=lambda **fields: saved.update(fields) or saved,
        availability_setter=lambda day, available, low, high: days.update({day: (available, low, high)}),
        journal_path=tmp_path / "journal.jsonl",
    )
    return TestClient(app)


def _token(page):
    return re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)


def _post(client, token, **data):
    return client.post("/wizard", data={"csrf_token": token, **data}, headers={"Origin": "http://testserver"},
                       follow_redirects=False)


def test_wizard_validation_links_error_to_the_specific_field(tmp_path):
    client = _client(tmp_path, {"name": "Ala"}, {}, {})
    token = _token(client.get("/wizard").text)
    response = _post(client, token, step="goal", action="next", distance="other", event_date=FUTURE)
    assert response.status_code == 400
    assert 'href="#distance_other"' in response.text
    assert 'id="distance_other" aria-invalid="true" aria-describedby="wizard-field-error"' in response.text
    assert 'id="wizard-field-error">Wpisz, jaki to dystans.' in response.text


def test_first_run_redirects_home_to_the_wizard(tmp_path):
    client = _client(tmp_path, {"name": "Ala"}, {}, {})

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 303 and response.headers["location"] == "/wizard"
    page = client.get("/wizard").text
    assert "Witaj! Ustalmy Twój cel" in page and "Pomiń na razie" in page


def test_walk_through_all_steps_and_save(tmp_path):
    saved, days = {}, {}
    client = _client(tmp_path, {"name": "Ala"}, saved, days)
    token = _token(client.get("/wizard").text)
    week = {f"{p}_{d}": v for d in wizard.DAYS for p, v in (("min", "30"), ("max", "60"))}
    week.update(day_tue="on", day_thu="on", day_sun="on", min_sun="60", max_sun="100", frequency="3")
    goal = {"distance": "10k", "event_name": "Bieg Niepodległości", "event_date": FUTURE}

    step2 = _post(client, token, step="goal", action="next", **goal)
    assert "Jaki czas chcesz osiągnąć?" in step2.text
    step3 = _post(client, token, step="times", action="next", target_time="49:30", record="52:10", **goal)
    assert "Ty i bieganie" in step3.text
    missing = _post(client, token, step="you", action="next", target_time="49:30", record="52:10", **goal)
    assert missing.status_code == 400 and "Zaznacz, od jak dawna biegasz." in missing.text
    you = {"running_since": "under6", "health_notes": "  kontuzja   kolana  w 2024  "}
    step4 = _post(client, token, step="you", action="next", target_time="49:30", record="52:10", **goal, **you)
    assert "Jak wygląda Twój tydzień?" in step4.text
    summary = _post(client, token, step="week", action="next", target_time="49:30", record="52:10", **goal, **you, **week)
    assert "Sprawdź i zapisz" in summary.text and "Bieg Niepodległości" in summary.text and "Do 6 miesięcy" in summary.text
    done = _post(client, token, step="summary", action="save", target_time="49:30", record="52:10", **goal, **you, **week)

    assert done.status_code == 303 and done.headers["location"] == "/goal?wizard=done"
    assert saved["target_race"] == "10 km — Bieg Niepodległości" and saved["target_date"] == FUTURE
    assert saved["target_hm"] == "10 km — Bieg Niepodległości 49:30"
    assert saved["training_frequency"] == "3 treningi w tygodniu" and "onboarding_completed_at" in saved
    assert days["sun"] == (True, 60, 100) and days["mon"] == (False, 0, 0)
    assert saved["running_since"] == "under6" and saved["health_notes"] == "kontuzja kolana w 2024"


def test_back_keeps_values_and_errors_stay_on_the_step(tmp_path):
    client = _client(tmp_path, {"name": "Ala"}, {}, {})
    token = _token(client.get("/wizard").text)

    error = _post(client, token, step="goal", action="next", distance="hm", event_date="")
    assert error.status_code == 400 and "Podaj datę wydarzenia" in error.text
    back = _post(client, token, step="times", action="back", distance="marathon", event_date=FUTURE)
    assert "Do czego się przygotowujesz?" in back.text and 'value="marathon" checked' in back.text


def test_skip_marks_the_decision_and_forged_posts_are_rejected(tmp_path):
    saved = {}
    client = _client(tmp_path, {"name": "Ala"}, saved, {})
    token = _token(client.get("/wizard").text)

    assert _post(client, "zly", step="goal", action="skip").status_code == 403
    skipped = _post(client, token, step="goal", action="skip")

    assert skipped.headers["location"] == "/" and "onboarding_skipped_at" in saved
