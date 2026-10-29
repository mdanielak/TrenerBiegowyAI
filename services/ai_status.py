# -*- coding: utf-8 -*-
"""Stan połączenia z AI: konfiguracja z .env i wynik ostatniego sprawdzenia.

Plik ``local/ai_status.json`` zawiera wyłącznie host, model, wynik, czas i krótki,
bezpieczny komunikat błędu — nigdy klucza ani treści odpowiedzi modelu.
„Połączone” znaczy: ostatnie sprawdzenie (test albo udane wywołanie AI z aplikacji)
dla tej samej pary host + model się udało i nie jest starsze niż STALE_DAYS.
"""
from __future__ import annotations

import json

from trainer.files import write_atomic
from datetime import datetime
from urllib.parse import urlsplit

from trainer.config import SETTINGS

AI_STATUS_PATH = SETTINGS.local_dir / "ai_status.json"
STALE_DAYS = 7
ERROR_LIMIT = 160

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


def record_test(*, ok: bool, base_url, model, error=None, source="test", path=None, now=None) -> dict:
    """Zapisz atomowo wynik sprawdzenia (bez sekretów)."""
    target = path or AI_STATUS_PATH
    record = {
        "ok": bool(ok),
        "host": _host(base_url),
        "model": str(model or ""),
        "tested_at": (now or datetime.now()).replace(microsecond=0).isoformat(),
        "source": source,
        "error": None if ok else " ".join(str(error or "").split())[:ERROR_LIMIT] or None,
    }
    write_atomic(target, json.dumps(record, ensure_ascii=False))
    return record


def load_status(path=None) -> dict | None:
    try:
        data = json.loads((path or AI_STATUS_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _when(tested_at, now) -> tuple[str, int] | None:
    """('dziś 23:40' | 'wczoraj 08:10' | '3 dni temu', liczba dni) albo None."""
    try:
        moment = datetime.fromisoformat(str(tested_at))
    except (TypeError, ValueError):
        return None
    days = (now.date() - moment.date()).days
    if days <= 0:
        return f"dziś {moment:%H:%M}", 0
    if days == 1:
        return f"wczoraj {moment:%H:%M}", 1
    return f"{days} dni temu", days


def ai_status_view(settings: dict | None, status: dict | None, *, now=None) -> dict:
    """Stan plakietki i strony API AI.

    state: 'missing' (brak klucza), 'no_consent', 'failed', 'untested', 'stale', 'connected'.
    tone: 'bad' (czerwony), 'warn' (pomarańczowy), 'ok' (zielony) — zawsze z opisem słownym.
    hint: co zrobić, żeby dojść do „połączone”.
    """
    now = now or datetime.now()
    settings = settings or {}
    provider = provider_name(settings.get("base_url"))
    model = str(settings.get("model") or "")
    base = {"provider": provider, "model": model, "can_check": False, "when": None, "error": None}

    if not settings.get("key_present"):
        return {**base, "state": "missing", "tone": "bad", "label": "AI niepodłączone",
                "detail": "brak klucza API", "provider": None,
                "hint": "Wpisz adres API, model i klucz w formularzu poniżej, zapisz, a potem sprawdź połączenie."}
    if not settings.get("export_enabled"):
        return {**base, "state": "no_consent", "tone": "bad", "label": "AI wyłączone",
                "detail": "brak zgody na wysyłanie danych", "can_check": True,
                "hint": "Zaznacz zgodę na wysyłanie danych do AI i zapisz ustawienia. Połączenie możesz sprawdzić już teraz."}

    status = status or {}
    same = status.get("host") == _host(settings.get("base_url")) and status.get("model") == model
    when = _when(status.get("tested_at"), now) if same else None
    checked = {**base, "can_check": True, "when": when[0] if when else None}
    if same and not status.get("ok"):
        return {**checked, "state": "failed", "tone": "bad", "label": "Połączenie z AI nie działa",
                "detail": f"{provider} · sprawdzone {checked['when']}" if checked["when"] else provider,
                "error": status.get("error"),
                "hint": "Popraw adres, model albo klucz zgodnie z komunikatem i sprawdź ponownie."}
    if same and when and when[1] > STALE_DAYS:
        return {**checked, "state": "stale", "tone": "warn", "label": f"AI gotowe · {provider}",
                "detail": f"ostatnio sprawdzone {when[0]}",
                "hint": "Sprawdź połączenie ponownie, żeby potwierdzić, że klucz nadal działa."}
    if same and status.get("ok"):
        return {**checked, "state": "connected", "tone": "ok", "label": f"AI połączone · {provider}",
                "detail": f"{model} · sprawdzone {checked['when']}" if checked["when"] else model,
                "hint": "Wszystko działa. Stan odświeża się też przy każdym udanym użyciu AI w aplikacji."}
    return {**checked, "state": "untested", "tone": "warn", "label": f"AI gotowe · {provider}",
            "detail": f"{model} · nie sprawdzono połączenia",
            "hint": "Kliknij „Sprawdź połączenie” — wyślę krótkie zapytanie testowe bez Twoich danych."}
