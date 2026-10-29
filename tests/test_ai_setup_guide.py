# -*- coding: utf-8 -*-
"""Samouczek podłączania AI, gotowe ustawienia i zgodność z dostawcami typu Gemini."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from ai.openai_compatible import AIProviderError, OpenAICompatibleProvider, _strip_code_fence
from api.main import create_app
from tests.test_api import _report

pytestmark = pytest.mark.usefixtures("testclient_sockets")


class _Answer(BaseModel):
    ok: bool


class _Rejected(Exception):
    status_code = 400


def _provider(responses):
    provider = OpenAICompatibleProvider.__new__(OpenAICompatibleProvider)
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=result))])

    provider.model = "m"
    provider.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return provider, calls


def test_json_mode_and_seed_are_dropped_once_when_the_provider_rejects_them():
    provider, calls = _provider([_Rejected("Invalid JSON payload: unknown field response_format"), '```json\n{"ok": true}\n```'])

    answer = provider.chat("system", "user", response_model=_Answer, seed=7, temperature=0.0)

    assert answer.ok is True
    assert "response_format" in calls[0] and "seed" in calls[0]
    assert "response_format" not in calls[1] and "seed" not in calls[1] and calls[1]["temperature"] == 0.0


def test_other_errors_are_not_retried():
    class _Unauthorized(Exception):
        status_code = 401

    provider, calls = _provider([_Unauthorized("bad key")])
    with pytest.raises(AIProviderError):
        provider.chat("system", "user", response_model=_Answer)
    assert len(calls) == 1


def test_code_fences_are_stripped():
    assert _strip_code_fence('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert _strip_code_fence('{"a": 1}') == '{"a": 1}'


def test_guide_and_presets_fill_the_form_without_a_key(tmp_path):
    env = tmp_path / ".env"
    env.write_text("AI_BASE_URL=https://api.deepseek.com\nAI_MODEL=deepseek-flash\nAI_API_KEY=sekret\n", encoding="utf-8")
    client = TestClient(create_app(report_provider=lambda: _report(), ai_env_path=env))

    page = client.get("/settings/ai").text
    assert "Jak podłączyć AI — krok po kroku" in page and "aistudio.google.com/apikey" in page
    gemini = client.get("/settings/ai?preset=gemini").text
    assert 'value="https://generativelanguage.googleapis.com/v1beta/openai/"' in gemini
    assert 'value="gemini-3.8-flash"' in gemini and "sekret" not in gemini
    ollama = client.get("/settings/ai?guide=ollama").text
    assert "ollama.com/download" in ollama and "<code>local</code>" in ollama


def test_saved_settings_apply_to_the_running_app_without_restart(tmp_path, monkeypatch):
    from trainer import ai_settings, config

    for name in ("AI_BASE_URL", "AI_MODEL", "AI_API_KEY", "AI_DATA_EXPORT_ENABLED"):
        monkeypatch.setattr(config, name, getattr(config, name))
        monkeypatch.setenv(name, "przed-testem")  # setenv zapamiętuje stan, więc po teście go przywróci
    env = tmp_path / ".env"
    env.write_text('AI_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai/"\nAI_MODEL="gemini-3.8-flash"\n'
                   'AI_API_KEY="k"\nAI_DATA_EXPORT_ENABLED="true"\n', encoding="utf-8")

    ai_settings.apply_to_running_app(env)

    assert config.AI_MODEL == "gemini-3.8-flash" and config.AI_API_KEY == "k"
    assert config.AI_DATA_EXPORT_ENABLED is True
