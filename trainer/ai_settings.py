"""Konfiguracja AI w .env; zmiany obowiązują po restarcie procesu."""
from __future__ import annotations

import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit

from trainer import config
from trainer.env_file import read_env_file

ENV_PATH = config.PROJECT_ROOT / ".env"
_ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


def read_ai_settings(path: Path) -> dict:
    """Publiczny widok konfiguracji zapisanej; nigdy nie zwraca klucza."""
    values = read_env_file(path)
    return {
        "base_url": values.get("AI_BASE_URL", config.AI_BASE_URL),
        "model": values.get("AI_MODEL", config.AI_MODEL),
        "key_present": bool(values.get("AI_API_KEY", config.AI_API_KEY)),
        "export_enabled": values.get(
            "AI_DATA_EXPORT_ENABLED", str(config.AI_DATA_EXPORT_ENABLED)
        ).strip().lower() in {"true", "1", "yes", "on"},
    }


def validate_ai_settings(*, base_url: str, model: str, api_key: str,
                         clear_key: bool = False) -> tuple[str, str]:
    """Wspólna walidacja zapisu i testu; komunikaty nie zawierają sekretów."""
    base_url, model = base_url.strip(), model.strip()
    for value in (base_url, model, api_key):
        if len(value) > 4096 or any(ord(char) < 32 or ord(char) == 127 or char in '\u0085\u2028\u2029' for char in value):
            raise ValueError("Pola nie mogą zawierać znaków sterujących ani przekraczać 4096 znaków.")
    try:
        url = urlsplit(base_url)
        valid = (url.scheme in {"http", "https"} and url.hostname and
                 not url.username and not url.password and not url.query and not url.fragment)
        url.port
    except ValueError:
        valid = False
    if not valid or any(char.isspace() for char in base_url):
        raise ValueError("Podaj adres API http(s) bez danych logowania, parametrów i fragmentu.")
    if not model:
        raise ValueError("Podaj nazwę modelu AI.")
    if clear_key and api_key:
        raise ValueError("Nie można jednocześnie ustawić i usunąć klucza.")
    return base_url, model


def same_api_provider(first: str, second: str) -> bool:
    """Ta sama domena, protokół i efektywny port; ścieżka nie wiąże klucza.

    Nie używaj startswith: api.example.evil nie jest dostawcą api.example.
    """
    def origin(value):
        url = urlsplit(value.strip())
        if (url.scheme not in {"http", "https"} or not url.hostname
                or url.username is not None or url.password is not None
                or any(char.isspace() for char in value) or "\\" in value):
            raise ValueError("Nieprawidłowy adres API.")
        port = url.port if url.port is not None else (443 if url.scheme == "https" else 80)
        return url.scheme, url.hostname.lower(), port

    try:
        return origin(first) == origin(second)
    except ValueError:
        return False


def resolve_test_key(path: Path, *, base_url: str, api_key: str, clear_key: bool) -> str:
    """Używaj zapisanego klucza także po zmianie ścieżki u tego samego dostawcy."""
    if clear_key:
        raise ValueError("Odznacz usuwanie klucza przed testem połączenia.")
    if api_key:
        return api_key
    values = read_env_file(path)
    saved_url = values.get("AI_BASE_URL", config.AI_BASE_URL)
    if not same_api_provider(base_url, saved_url):
        raise ValueError("Zmieniono serwer API (domenę, protokół lub port). Wpisz klucz dla nowego dostawcy przed testem.")
    key = values.get("AI_API_KEY", config.AI_API_KEY)
    if not key:
        raise ValueError("Wpisz klucz API. Dla lokalnego serwera bez uwierzytelniania możesz wpisać local.")
    return key


def save_ai_settings(path: Path, *, base_url: str, model: str, api_key: str,
                     export_enabled: bool, clear_key: bool = False) -> None:
    """Atomowo zmień wyłącznie wpisy AI. Wywołujący zapewnia blokadę."""
    base_url, model = validate_ai_settings(
        base_url=base_url, model=model, api_key=api_key, clear_key=clear_key)
    saved = read_env_file(path)
    saved_url = saved.get("AI_BASE_URL", config.AI_BASE_URL)
    saved_key = saved.get("AI_API_KEY", config.AI_API_KEY)
    if (not api_key and not clear_key and saved_key
            and not same_api_provider(base_url, saved_url)):
        raise ValueError("Zmieniono serwer API. Wpisz nowy klucz lub zaznacz usunięcie dotychczasowego klucza.")
    values = {
        "AI_BASE_URL": base_url,
        "AI_MODEL": model,
        "AI_DATA_EXPORT_ENABLED": "true" if export_enabled else "false",
    }
    if clear_key or api_key:
        values["AI_API_KEY"] = "" if clear_key else api_key

    def assignment(key):
        value = values[key].replace("\\", "\\\\").replace('"', '\\"')
        return f'{key}="{value}"'

    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except FileNotFoundError:
        lines = []
    output, seen = [], set()
    for line in lines:
        match = _ASSIGNMENT.match(line)
        key = match.group(1) if match else None
        if key in values:
            if key not in seen:
                output.append(assignment(key))
                seen.add(key)
        else:
            output.append(line)
    output.extend(assignment(key) for key in values if key not in seen)
    path.parent.mkdir(parents=True, exist_ok=True)
    # mkstemp creates a private (0600 on POSIX) file in the same filesystem.
    fd, temporary = tempfile.mkstemp(prefix=".env.tmp-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("\n".join(output) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
