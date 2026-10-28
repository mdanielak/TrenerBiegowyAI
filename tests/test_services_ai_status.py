# -*- coding: utf-8 -*-
"""Stan AI: plakietka, zapis wyniku testu połączenia i blokada rekomendacji bez AI."""
import json
import re
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from services.ai_status import ai_status_view, load_status, provider_name, record_test
from services.jobs import JobStore
from tests.test_api import _report

pytestmark = pytest.mark.usefixtures("testclient_sockets")

SETTINGS = {"base_url": "https://api.deepseek.com", "model": "deepseek-flash", "key_present": True,
            "export_enabled": True}


def test_provider_names():
    assert provider_name("https://api.deepseek.com/v1") == "DeepSeek"
    assert provider_name("http://localhost:11434/v1") == "lokalny serwer"
    assert provider_name("https://ai.example.org/v1") == "ai.example.org"


def test_states_follow_configuration_and_the_last_test(tmp_path):
    path = tmp_path / "ai_status.json"

    assert ai_status_view({**SETTINGS, "key_present": False}, None)["state"] == "off"
    assert ai_status_view({**SETTINGS, "export_enabled": False}, None)["detail"] == "brak zgody na wysyłanie danych"
    assert ai_status_view(SETTINGS, None)["label"] == "AI gotowe · DeepSeek"

    record_test(ok=True, base_url="https://api.deepseek.com", model="deepseek-flash", path=path,
                now=datetime(2026, 10, 28, 21, 40))
    connected = ai_status_view(SETTINGS, load_status(path))
    assert connected["state"] == "connected" and connected["label"] == "AI połączone · DeepSeek"

    assert ai_status_view({**SETTINGS, "model": "inny"}, load_status(path))["state"] == "ready"
    record_test(ok=False, base_url="https://api.deepseek.com", model="deepseek-flash", path=path)
    assert "nie udał" in ai_status_view(SETTINGS, load_status(path))["detail"]


def test_status_file_holds_no_secrets(tmp_path):
    path = tmp_path / "ai_status.json"
    record_test(ok=True, base_url="https://user:sekret@api.deepseek.com/v1?key=abc", model="m", path=path)

    stored = json.loads(path.read_text(encoding="utf-8"))
    assert set(stored) == {"ok", "host", "model", "tested_at"}
    assert "sekret" not in path.read_text(encoding="utf-8") and "abc" not in path.read_text(encoding="utf-8")


def _client(tmp_path, settings, store=None):
    return TestClient(create_app(
        report_provider=lambda: _report(),
        ai_settings_provider=lambda: settings,
        job_store=store or JobStore(tmp_path / "jobs"),
        lock_directory=tmp_path / "locks",
        recommendation_operation=lambda: None,
    ))


def test_home_shows_the_badge(tmp_path):
    page = _client(tmp_path, SETTINGS).get("/").text
    assert "AI gotowe · DeepSeek" in page and 'href="/settings/ai"' in page

    off = _client(tmp_path, {**SETTINGS, "key_present": False}).get("/").text
    assert "AI wyłączone" in off and "brak klucza API" in off
    assert re.search(r'<button type="submit" class="btn-secondary" disabled>\s*\S*\s*.*Zapytaj AI', off, re.S)


def test_recommendation_without_ai_explains_instead_of_failing(tmp_path):
    store = JobStore(tmp_path / "jobs")
    client = _client(tmp_path, {**SETTINGS, "export_enabled": False}, store)
    token = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/").text).group(1)

    response = client.post("/actions/recommendation", data={"csrf_token": token},
                           headers={"Origin": "http://testserver"}, follow_redirects=False)

    assert response.status_code == 303 and response.headers["location"] == "/?ai=off"
    assert store.list_jobs().jobs == []
    assert "Rekomendacja AI wymaga połączenia z AI." in client.get("/?ai=off").text


def test_connection_test_result_feeds_the_badge(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("AI_BASE_URL=https://api.deepseek.com\nAI_MODEL=deepseek-flash\nAI_API_KEY=k\n"
                   "AI_DATA_EXPORT_ENABLED=true\n", encoding="utf-8")
    monkeypatch.setattr("api.main.check_connection", lambda **kwargs: None)
    status = tmp_path / "ai_status.json"
    client = TestClient(create_app(report_provider=lambda: _report(), ai_env_path=env, ai_status_path=status,
                                   lock_directory=tmp_path / "locks", job_store=JobStore(tmp_path / "jobs")))
    token = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/settings/ai").text).group(1)

    client.post("/settings/ai/test", data={"csrf_token": token, "base_url": "https://api.deepseek.com",
                                           "model": "deepseek-flash", "export_enabled": "true"},
                headers={"Origin": "http://testserver"})

    assert load_status(status)["ok"] is True
    assert "AI połączone · DeepSeek" in client.get("/").text
