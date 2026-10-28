# -*- coding: utf-8 -*-
"""Stan połączenia z AI: konfiguracja z .env i wynik ostatniego testu połączenia.

Plik ``local/ai_status.json`` zawiera wyłącznie host, model, wynik i czas testu —
nigdy klucza ani treści odpowiedzi modelu. „Połączone” oznacza tylko tyle, że
ostatni test dla tej samej pary host + model się udał.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from urllib.parse import urlsplit

from trainer.config import SETTINGS

AI_STATUS_PATH = SETTINGS.local_dir / "ai_status.json"

_PROVIDERS = {
    "api.deepseek.com": "DeepSeek",
    "api.openai.com": "OpenAI",
    "openrouter.ai": "OpenRouter",
    "api.anthropic.com": "Anthropic",
    "generativelanguage.googleapis.com": "Google",
    "api.mistral.ai": "Mistral",
    "api.groq.com": "Groq",
    "localhost": "lokalny serwer",
    "127.0.0.1": "lokalny serwer",
}


def _host(base_url) -> str:
    try:
        return (urlsplit(str(base_url or "")).hostname or "").lower()
    except ValueError:
        return ""


def provider_name(base_url) -> str:
    """Czytelna nazwa dostawcy z adresu API; nieznany host pokazujemy wprost."""
    host = _host(base_url)
    return _PROVIDERS.get(host) or host or "nieznany dostawca"


def record_test(*, ok: bool, base_url, model, path=None, now=None) -> dict:
    """Zapisz atomowo wynik testu połączenia (bez sekretów)."""
    target = path or AI_STATUS_PATH
    record = {
        "ok": bool(ok),
        "host": _host(base_url),
        "model": str(model or ""),
        "tested_at": (now or datetime.now()).replace(microsecond=0).isoformat(),
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".ai_status.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False)
        os.replace(temporary, target)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return record


def load_status(path=None) -> dict | None:
    try:
        data = json.loads((path or AI_STATUS_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def ai_status_view(settings: dict | None, status: dict | None) -> dict:
    """Stan dla plakietki: 'connected', 'ready' albo 'off', zawsze z opisem słownym."""
    settings = settings or {}
    provider = provider_name(settings.get("base_url"))
    model = str(settings.get("model") or "")
    if not settings.get("key_present"):
        return {"state": "off", "label": "AI wyłączone", "detail": "brak klucza API", "provider": None, "model": None}
    if not settings.get("export_enabled"):
        return {"state": "off", "label": "AI wyłączone", "detail": "brak zgody na wysyłanie danych",
                "provider": provider, "model": model}
    status = status or {}
    same_target = status.get("host") == _host(settings.get("base_url")) and status.get("model") == model
    tested_at = status.get("tested_at") if same_target else None
    if same_target and status.get("ok"):
        return {"state": "connected", "label": f"AI połączone · {provider}", "detail": model,
                "provider": provider, "model": model, "tested_at": tested_at}
    detail = "ostatni test się nie udał" if same_target else "nie testowano połączenia"
    return {"state": "ready", "label": f"AI gotowe · {provider}", "detail": f"{model}, {detail}",
            "provider": provider, "model": model, "tested_at": tested_at}
