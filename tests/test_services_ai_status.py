# -*- coding: utf-8 -*-
"""Stan AI: plakietka w menu, sprawdzanie połączenia i blokada rekomendacji bez AI."""
import json
import re
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from ai.connection_test import AIConnectionTestError
from api.main import create_app
from services.ai_status import ai_status_view, load_status, provider_name, record_test
from services.jobs import JobStore
from tests.test_api import _report

pytestmark = pytest.mark.usefixtures("testclient_sockets")

SETTINGS = {"base_url": "https://api.deepseek.com", "model": "deepseek-flash", "key_present": True,
            "export_enabled": True}
NOW = datetime(2026, 10, 28, 23, 40)


def test_provider_names():
    assert provider_name("https://api.deepseek.com/v1") == "DeepSeek"
    assert provider_name("http://localhost:11434/v1") == "lokalny serwer"
    assert provider_name("https://ai.example.org/v1") == "ai.example.org"


def test_missing_key_and_consent_are_red(tmp_path):
    missing = ai_status_view({**SETTINGS, "key_present": False}, None, now=NOW)
    assert (missing["state"], missing["tone"], missing["label"]) == ("missing", "bad", "AI niepodłączone")
    assert missing["can_check"] is False

    no_consent = ai_status_view({**SETTINGS, "export_enabled": False}, None, now=NOW)
    assert no_consent["tone"] == "bad" and no_consent["can_check"] is True


def test_green_only_after_a_passing_check_for_the_saved_target(tmp_path):
    path = tmp_path / "ai_status.json"
    assert ai_status_view(SETTINGS, None, now=NOW)["state"] == "untested"

    record_test(ok=True, base_url="https://api.deepseek.com", model="deepseek-flash", path=path, now=NOW)
    connected = ai_status_view(SETTINGS, load_status(path), now=NOW)
    assert (connected["tone"], connected["label"]) == ("ok", "AI połączone · DeepSeek")
    assert connected["when"] == "dziś 23:40"

    assert ai_status_view({**SETTINGS, "model": "inny"}, load_status(path), now=NOW)["state"] == "untested"
    stale = ai_status_view(SETTINGS, load_status(path), now=datetime(2026, 11, 10, 9))
    assert stale["state"] == "stale" and stale["tone"] == "warn"


def test_failed_check_is_red_with_the_reason(tmp_path):
    path = tmp_path / "ai_status.json"
    record_test(ok=False, base_url="https://api.deepseek.com", model="deepseek-flash",
                error="Klucz API jest nieprawidłowy.", path=path, now=NOW)

    failed = ai_status_view(SETTINGS, load_status(path), now=NOW)

    assert (failed["state"], failed["tone"]) == ("failed", "bad")
    assert failed["error"] == "Klucz API jest nieprawidłowy."


def test_status_file_holds_no_secrets(tmp_path):
    path = tmp_path / "ai_status.json"
    record_test(ok=True, base_url="https://user:sekret@api.deepseek.com/v1?key=abc", model="m", path=path)

    text = path.read_text(encoding="utf-8")
    assert set(json.loads(text)) == {"ok", "host", "model", "tested_at", "source", "error"}
    assert "sekret" not in text and "abc" not in text


def _client(tmp_path, settings, store=None):
    return TestClient(create_app(
        report_provider=lambda: _report(),
        ai_settings_provider=lambda: settings,
        job_store=store or JobStore(tmp_path / "jobs"),
        lock_directory=tmp_path / "locks",
        recommendation_operation=lambda: None,
    ))


@pytest.mark.parametrize("path", ["/", "/stats", "/journal", "/settings"])
def test_every_page_has_the_badge_in_the_sidebar(tmp_path, path):
    page = _client(tmp_path, SETTINGS).get(path).text
    sidebar = page[page.index('class="sidebar"'):page.index('class="nav"')]

    assert "AI gotowe · DeepSeek" in sidebar and "Sprawdź połączenie →" in sidebar


def test_home_without_a_key_is_red_and_disables_the_ask_button(tmp_path):
    page = _client(tmp_path, {**SETTINGS, "key_present": False}).get("/").text

    assert 'class="ai-badge bad"' in page and "AI niepodłączone" in page and "Podłącz AI →" in page
    assert re.search(r'<button type="submit" class="btn-secondary" disabled>', page)


def test_recommendation_without_ai_explains_instead_of_failing(tmp_path):
    store = JobStore(tmp_path / "jobs")
    client = _client(tmp_path, {**SETTINGS, "export_enabled": False}, store)
    token = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/").text).group(1)

    response = client.post("/actions/recommendation", data={"csrf_token": token},
                           headers={"Origin": "http://testserver"}, follow_redirects=False)

    assert response.status_code == 303 and response.headers["location"] == "/?ai=off"
    assert store.list_jobs().jobs == []
    assert "Rekomendacja AI wymaga połączenia z AI." in client.get("/?ai=off").text


def _settings_client(tmp_path, monkeypatch, outcome):
    env = tmp_path / ".env"
    env.write_text("AI_BASE_URL=https://api.deepseek.com\nAI_MODEL=deepseek-flash\nAI_API_KEY=k\n"
                   "AI_DATA_EXPORT_ENABLED=true\n", encoding="utf-8")
    calls = []

    def check(**kwargs):
        calls.append(kwargs)
        if outcome is not None:
            raise AIConnectionTestError(outcome)

    monkeypatch.setattr("api.main.check_connection", check)
    status = tmp_path / "ai_status.json"
    client = TestClient(create_app(report_provider=lambda: _report(), ai_env_path=env, ai_status_path=status,
                                   lock_directory=tmp_path / "locks", job_store=JobStore(tmp_path / "jobs")))
    return client, status, calls


def test_one_click_check_uses_the_saved_configuration_and_turns_green(tmp_path, monkeypatch):
    client, status, calls = _settings_client(tmp_path, monkeypatch, None)
    token = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/settings/ai").text).group(1)

    response = client.post("/settings/ai/check", data={"csrf_token": token},
                           headers={"Origin": "http://testserver"}, follow_redirects=False)

    assert response.headers["location"] == "/settings/ai?check=ok#polaczenie"
    assert calls == [{"base_url": "https://api.deepseek.com", "model": "deepseek-flash", "api_key": "k"}]
    assert load_status(status)["ok"] is True
    page = client.get("/settings/ai?check=ok").text
    assert "Połączenie działa — model odpowiedział." in page and 'class="ai-badge ok"' in page


def test_failed_one_click_check_shows_why(tmp_path, monkeypatch):
    client, status, _ = _settings_client(tmp_path, monkeypatch, "Klucz API jest nieprawidłowy.")
    token = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/settings/ai").text).group(1)

    client.post("/settings/ai/check", data={"csrf_token": token}, headers={"Origin": "http://testserver"})

    assert load_status(status)["error"] == "Klucz API jest nieprawidłowy."
    page = client.get("/settings/ai?check=fail").text
    assert "Połączenie nie działa." in page and "Klucz API jest nieprawidłowy." in page
    assert 'class="ai-badge bad"' in page


def test_successful_ai_use_confirms_the_connection(monkeypatch):
    from services.actions import _remember_ai_success
    from trainer import config

    monkeypatch.setattr(config, "AI_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setattr(config, "AI_MODEL", "deepseek-flash")
    _remember_ai_success()

    stored = load_status()
    assert stored["ok"] is True and stored["source"] == "use"
    assert ai_status_view(SETTINGS, stored)["state"] == "connected"
